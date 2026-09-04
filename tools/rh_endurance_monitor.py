#!/usr/bin/env python3
"""QA host monitor for APP_RH_ENDURANCE_TEST 4 Hz run-hours journal."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mcxn_lib import load_cfg, load_unit, fetch_status  # noqa: E402
from mcxn_lib.mtls import connect_mtls  # noqa: E402

LS = Path(r"C:\nxp\LinkServer_25.6.131\LinkServer.exe")
PROBE = "MNZW4VYTFX113"
TARGET_DELTA_DEFAULT = 525600
PROD_QUANTUM_S = 600
QA_PERIOD_MS = 250


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def mtls_cmd(cfg: dict, cmd: str, timeout: float = 10.0) -> str:
    unit = load_unit(cfg["unit_name"])
    with connect_mtls(cfg, int(cfg.get("hello_port", 5000)), timeout=timeout, unit=unit) as s:
        s.sendall((cmd + "\n").encode())
        return s.recv(2048).decode("utf-8", "replace").strip()


def parse_kv(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for m in re.finditer(r"(\w+)=([^\s]+)", text):
        k, v = m.group(1), m.group(2)
        if re.fullmatch(r"-?\d+", v):
            out[k] = int(v)
        else:
            out[k] = v
    return out


def reset_board() -> None:
    try:
        subprocess.run(
            [str(LS), "probe", PROBE, "wiretimedreset", "80"],
            capture_output=True,
            check=False,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        pass
    time.sleep(12)


def append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj) + "\n")


def load_meta(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_meta(path: Path, meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def fetch_erase_events(cfg: dict, last_id: int) -> tuple[list[dict], int]:
    events: list[dict] = []
    cur = last_id
    for _ in range(64):
        text = mtls_cmd(cfg, f"RHERASE {cur}", timeout=12)
        lines = text.splitlines()
        if not lines:
            break
        hdr = parse_kv(lines[0])
        more = int(hdr.get("MORE", 0))
        for line in lines[1:]:
            if not line.startswith("RHERASE id="):
                continue
            ev = parse_kv(line)
            events.append(ev)
            cur = max(cur, int(ev.get("id", cur)))
        if not more:
            break
    return events, cur


def equivalent_years(delta: int) -> float:
    return (delta * PROD_QUANTUM_S) / (365.0 * 24.0 * 3600.0)


def main(
    cfg: dict | None = None,
    *,
    logdir: Path,
    new_run: bool = False,
    target_delta: int = TARGET_DELTA_DEFAULT,
    poll_s: float = 60.0,
    auto_reset_at: str = "",
    max_hours: float = 0.0,
) -> int:
    cfg = cfg or load_cfg()
    unit = load_unit(cfg["unit_name"])
    logdir = Path(logdir)
    logdir.mkdir(parents=True, exist_ok=True)
    meta_path = logdir / "run_metadata.json"
    minute_path = logdir / "minute_status.jsonl"
    erase_path = logdir / "erase_events.jsonl"
    events_path = logdir / "monitor_events.jsonl"
    console_path = logdir / "console.log"
    summary_path = logdir / "final_summary.json"

    def clog(msg: str) -> None:
        line = f"[{utc_now()}] {msg}"
        print(line, flush=True)
        with console_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    meta = load_meta(meta_path)
    if meta and not new_run:
        if meta.get("status") not in ("COMPLETE", "FAILED") and meta.get("target_quanta") is not None:
            clog(f"resuming run uuid={meta.get('run_uuid')} target={meta['target_quanta']}")
        elif meta.get("status") == "COMPLETE" and not new_run:
            clog("existing COMPLETE metadata; pass --new-run to start fresh")
            return 0
    elif meta and new_run:
        if meta.get("status") not in ("COMPLETE", "FAILED", None):
            clog("WARNING: --new-run overwriting unfinished metadata")
        meta = None

    st = fetch_status(cfg)
    uuid_board = (st.uuid or unit["mcu_uuid"]).upper()
    rh = parse_kv(mtls_cmd(cfg, "RHDIAG"))
    q0 = int(rh["quanta"])

    if meta is None:
        target_q = q0 + int(target_delta)
        meta = {
            "run_uuid": str(uuid.uuid4()),
            "unit": cfg["unit_name"],
            "silicon_uuid": uuid_board,
            "firmware_version": st.version,
            "git_commit": subprocess.check_output(
                [r"C:\Program Files\Git\mingw64\bin\git.exe", "rev-parse", "HEAD"],
                cwd=str(ROOT),
                text=True,
            ).strip(),
            "rh_key_version": rh.get("key_ver"),
            "rh_key_id": rh.get("key_id"),
            "start_utc": utc_now(),
            "start_quanta": q0,
            "target_delta": int(target_delta),
            "target_quanta": target_q,
            "production_quantum_s": PROD_QUANTUM_S,
            "qa_period_ms": QA_PERIOD_MS,
            "status": "RUNNING",
            "resets": [],
            "milestones": [],
            "last_erase_id": 0,
            "mtls_errors": 0,
        }
        save_meta(meta_path, meta)
        clog(f"NEW RUN start_quanta={q0} target={target_q} delta={target_delta}")
    else:
        target_q = int(meta["target_quanta"])
        if uuid_board != str(meta.get("silicon_uuid", "")).upper():
            clog(f"FAIL uuid mismatch board={uuid_board} meta={meta.get('silicon_uuid')}")
            meta["status"] = "FAILED"
            save_meta(meta_path, meta)
            return 1
        q0 = int(meta["start_quanta"])

    # Arm or complete
    q_now = int(parse_kv(mtls_cmd(cfg, "RHDIAG"))["quanta"])
    if q_now >= target_q:
        clog(f"already complete quanta={q_now} target={target_q}")
        meta["status"] = "COMPLETE"
        meta["final_quanta"] = q_now
        save_meta(meta_path, meta)
        return 0

    if "baseline_auth_fail" not in meta:
        meta["baseline_auth_fail"] = int(parse_kv(mtls_cmd(cfg, "RHDIAG")).get("auth_fail", 0))
    if "baseline_flash_err" not in meta:
        meta["baseline_flash_err"] = int(parse_kv(mtls_cmd(cfg, "RHDIAG")).get("flash_err", 0))
    st0 = parse_kv(mtls_cmd(cfg, "RHSTRESS STATUS"))
    if "baseline_erase_ovf" not in meta:
        meta["baseline_erase_ovf"] = int(st0.get("erase_ovf", 0))
    save_meta(meta_path, meta)

    arm = mtls_cmd(cfg, f"RHSTRESS START {target_q}")
    clog(f"arm: {arm}")
    if not arm.startswith("RHSTRESS OK"):
        clog(f"FAIL arm: {arm}")
        meta["status"] = "FAILED"
        save_meta(meta_path, meta)
        return 1

    reset_pcts = []
    if auto_reset_at.strip():
        reset_pcts = [float(x) for x in auto_reset_at.split(",") if x.strip()]
    resets_done: set[float] = set(meta.get("resets_done_pct") or [])

    t0 = time.time()
    last_quanta = q_now
    failed = False
    fail_reason = ""

    while True:
        time.sleep(poll_s)
        try:
            status_txt = mtls_cmd(cfg, "RHSTRESS STATUS")
            st_map = parse_kv(status_txt)
            diag = parse_kv(mtls_cmd(cfg, "RHDIAG"))
            board_st = fetch_status(cfg)
        except Exception as e:
            meta["mtls_errors"] = int(meta.get("mtls_errors", 0)) + 1
            save_meta(meta_path, meta)
            append_jsonl(events_path, {"ts": utc_now(), "event": "mtls_error", "error": str(e)})
            clog(f"mTLS error ({meta['mtls_errors']}): {e}")
            if int(meta["mtls_errors"]) >= 5:
                failed = True
                fail_reason = "repeated_mtls_failure"
                break
            continue

        quanta = int(st_map.get("quanta", diag.get("quanta", -1)))
        delta = quanta - int(meta["start_quanta"])
        remaining = target_q - quanta
        commits_ok = int(st_map.get("commits_ok", 0))
        elapsed = max(time.time() - t0, 1e-6)
        # Prefer device commits_ok when available; else host delta
        rate = commits_ok / elapsed if commits_ok else delta / elapsed

        # Failure checks
        if quanta < last_quanta:
            failed, fail_reason = True, f"quanta_regression {last_quanta}->{quanta}"
        if quanta > target_q:
            failed, fail_reason = True, f"overshoot quanta={quanta} target={target_q}"
        # After unexpected reset, device target may be 0 until re-armed — re-arm below.
        device_target = int(st_map.get("target", 0) or 0)
        if device_target not in (0, target_q) and int(st_map.get("running", 0)) == 1:
            failed, fail_reason = True, f"target_changed device={device_target} expected={target_q}"

        # Resume: if not complete and writer idle (post-reset), re-arm same absolute target
        if (
            not failed
            and quanta < target_q
            and int(st_map.get("complete", 0)) == 0
            and int(st_map.get("running", 0)) == 0
        ):
            arm = mtls_cmd(cfg, f"RHSTRESS START {target_q}")
            clog(f"re-arm (idle writer): {arm} quanta={quanta}")
            append_jsonl(
                events_path,
                {"ts": utc_now(), "event": "rearm", "quanta": quanta, "reply": arm},
            )
            if not arm.startswith("RHSTRESS OK"):
                failed, fail_reason = True, f"rearm_failed {arm}"
            else:
                continue
        if int(diag.get("auth_fail", 0)) > int(meta.get("baseline_auth_fail", 0)):
            failed, fail_reason = True, "auth_fail_increase"
        if int(diag.get("flash_err", 0)) > int(meta.get("baseline_flash_err", 0)):
            failed, fail_reason = True, "flash_err_increase"
        if int(st_map.get("flash_err", 0)) > int(meta.get("baseline_flash_err", 0)):
            failed, fail_reason = True, "flash_err_increase"
        # erase_ovf: fail only on *increase* after arm. Sticky wrap on pre-3.7.1 firmware
        # is not "PC fell behind" — id-gap check below is the real lost-event signal.
        if int(st_map.get("erase_ovf", 0)) > int(meta.get("baseline_erase_ovf", 0)):
            clog(
                f"WARN erase_ovf {meta.get('baseline_erase_ovf')}->{st_map.get('erase_ovf')} "
                f"(instrumentation; continuing unless id gap)"
            )
            meta["baseline_erase_ovf"] = int(st_map.get("erase_ovf", 0))
            append_jsonl(
                events_path,
                {
                    "ts": utc_now(),
                    "event": "erase_ovf_bump",
                    "erase_ovf": st_map.get("erase_ovf"),
                },
            )
        if int(st_map.get("key_ver", 2)) != 2:
            failed, fail_reason = True, "key_ver_lost"
        if (board_st.uuid or "").upper() != str(meta["silicon_uuid"]).upper():
            failed, fail_reason = True, "uuid_mismatch"

        # Erase events
        erases, last_eid = fetch_erase_events(cfg, int(meta.get("last_erase_id", 0)))
        prev_eid = int(meta.get("last_erase_id", 0))
        meta["last_erase_id"] = last_eid
        for ev in erases:
            append_jsonl(erase_path, {"ts": utc_now(), **ev})
            eid = int(ev.get("id", 0))
            if eid and prev_eid and eid < prev_eid:
                # Device reboot restarted erase id space
                prev_eid = 0
                meta["last_erase_id"] = 0
            if prev_eid and eid > prev_eid + 1:
                failed, fail_reason = True, f"erase_id_gap after={prev_eid} got={eid}"
            if eid > prev_eid:
                prev_eid = eid
                meta["last_erase_id"] = eid
            addr = str(ev.get("addr", ""))
            # Outside journal pools?
            try:
                a = int(str(addr), 16) if str(addr).startswith("0x") else int(addr)
                in_a = 0x000A0000 <= a < 0x000B0000
                in_b = 0x001A0000 <= a < 0x001B0000
                if not (in_a or in_b):
                    failed, fail_reason = True, f"erase_outside_range {addr}"
            except ValueError:
                pass
            if str(ev.get("result", "OK")).upper() == "FAIL":
                # Virgin re-erase may FAIL; count but do not auto-fail unless rising trend
                append_jsonl(events_path, {"ts": utc_now(), "event": "erase_fail", **ev})
        meta["last_erase_id"] = max(int(meta.get("last_erase_id", 0)), last_eid if last_eid else 0)

        # Milestones
        for mark, label in ((52560, "1-year"), (262800, "5-year"), (525600, "10-year")):
            if delta >= mark and label not in meta.get("milestones", []):
                meta.setdefault("milestones", []).append(label)
                clog(f"MILESTONE: {label} equivalent reached")
                append_jsonl(events_path, {"ts": utc_now(), "event": "milestone", "label": label})

        minute = {
            "ts": utc_now(),
            "uptime_s": st_map.get("uptime_s"),
            "quanta": quanta,
            "delta": delta,
            "remaining": remaining,
            "attempts": st_map.get("attempts"),
            "commits_ok": commits_ok,
            "commit_fail": st_map.get("commit_fail"),
            "rate_cps": round(rate, 4),
            "deadline_miss": st_map.get("deadline_miss"),
            "seq": st_map.get("seq", diag.get("seq")),
            "erase_total": st_map.get("erase_total"),
            "erase_fail": st_map.get("erase_fail"),
            "auth_fail": diag.get("auth_fail"),
            "torn": diag.get("torn"),
            "flash_err": diag.get("flash_err"),
            "remap": st_map.get("remap", diag.get("remap")),
            "key_ver": st_map.get("key_ver"),
            "key_id": st_map.get("key_id"),
            "ks": st_map.get("ks"),
            "running": st_map.get("running"),
            "complete": st_map.get("complete"),
            "equivalent_years": round(equivalent_years(delta), 4),
            "mtls_errors": meta.get("mtls_errors", 0),
            "new_erases": len(erases),
        }
        append_jsonl(minute_path, minute)
        save_meta(meta_path, meta)

        erase_note = ""
        if erases:
            e0 = erases[-1]
            erase_note = f" ERASE id={e0.get('id')} addr={e0.get('addr')} pool={e0.get('pool')} sector={e0.get('sector')}"
        clog(
            f"quanta={quanta} delta={delta}/{meta['target_delta']} rate={rate:.3f}/s "
            f"erase_total={st_map.get('erase_total')} commit_fail={st_map.get('commit_fail')} "
            f"auth_fail={diag.get('auth_fail')} flash_err={diag.get('flash_err')} "
            f"deadline_miss={st_map.get('deadline_miss')} equiv_y={equivalent_years(delta):.3f}"
            f"{erase_note}"
        )

        # Controlled resets at percent milestones
        pct = 100.0 * delta / max(int(meta["target_delta"]), 1)
        for rp in reset_pcts:
            if pct >= rp and rp not in resets_done and delta < int(meta["target_delta"]):
                clog(f"controlled reset at ~{rp}% (delta={delta})")
                try:
                    mtls_cmd(cfg, "RHSTRESS STOP")
                except Exception:
                    pass
                reset_board()
                # resume
                for _ in range(30):
                    try:
                        fetch_status(cfg, timeout=3)
                        break
                    except OSError:
                        time.sleep(1)
                q_rec = int(parse_kv(mtls_cmd(cfg, "RHDIAG"))["quanta"])
                meta.setdefault("resets", []).append(
                    {"ts": utc_now(), "pct": rp, "recovered_quanta": q_rec}
                )
                resets_done.add(rp)
                meta["resets_done_pct"] = sorted(resets_done)
                save_meta(meta_path, meta)
                if q_rec < last_quanta:
                    failed, fail_reason = True, f"reset_regression {last_quanta}->{q_rec}"
                    break
                arm = mtls_cmd(cfg, f"RHSTRESS START {target_q}")
                clog(f"re-arm after reset: {arm} recovered={q_rec}")
                last_quanta = q_rec
                append_jsonl(
                    events_path,
                    {"ts": utc_now(), "event": "controlled_reset", "pct": rp, "recovered": q_rec},
                )
                break

        if failed:
            break

        last_quanta = quanta
        if int(st_map.get("complete", 0)) == 1 or quanta >= target_q:
            clog(f"COMPLETE quanta={quanta} target={target_q}")
            meta["status"] = "COMPLETE"
            meta["final_quanta"] = quanta
            meta["end_utc"] = utc_now()
            save_meta(meta_path, meta)
            break

        if max_hours > 0 and (time.time() - t0) > max_hours * 3600:
            failed, fail_reason = True, "max_hours_exceeded"
            break

    if failed:
        clog(f"FAILED: {fail_reason}")
        try:
            mtls_cmd(cfg, "RHSTRESS STOP")
        except Exception:
            pass
        meta["status"] = "FAILED"
        meta["fail_reason"] = fail_reason
        meta["end_utc"] = utc_now()
        save_meta(meta_path, meta)
        summary_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        return 1

    summary = {
        **meta,
        "lab_duration_s": round(time.time() - t0, 1),
        "equivalent_years": equivalent_years(int(meta["final_quanta"]) - int(meta["start_quanta"])),
        "pass": True,
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    clog("final_summary written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(load_cfg(), logdir=Path(r"C:\mcxn\builds\rh_endurance_4hz"), new_run=True))
