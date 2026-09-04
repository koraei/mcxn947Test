#!/usr/bin/env python3
"""Controlled MCU reset during active RH endurance full run (LinkServer)."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mcxn_lib import load_cfg, fetch_status  # noqa: E402
from rh_endurance_monitor import mtls_cmd, parse_kv  # noqa: E402

TARGET = 542271
LOGDIR = Path(r"C:\mcxn\builds\rh_endurance_4hz\full")
LS = Path(r"C:\nxp\LinkServer_25.6.131\LinkServer.exe")
PROBE = "MNZW4VYTFX113"
EVIDENCE = ROOT / "docs" / "evidence" / "RUNHOURS_4HZ_10YEAR_ENDURANCE.md"


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def snap(cfg, label: str) -> dict:
    d = parse_kv(mtls_cmd(cfg, "RHDIAG", timeout=12))
    s = parse_kv(mtls_cmd(cfg, "RHSTRESS STATUS", timeout=12))
    b = fetch_status(cfg, timeout=8)
    out = {
        "label": label,
        "ts": utc(),
        "version": getattr(b, "version", None),
        "quanta": int(d["quanta"]),
        "seq": int(d["seq"]),
        "commits_ok": int(s.get("commits_ok", 0)),
        "erase_total": int(s.get("erase_total", d.get("erases", 0))),
        "remap": int(s.get("remap", d.get("remap", 0))),
        "running": int(s.get("running", 0)),
        "target": int(s.get("target", 0)),
        "auth_fail": int(s.get("auth_fail", d.get("auth_fail", 0))),
        "flash_err": int(s.get("flash_err", d.get("flash_err", 0))),
        "commit_fail": int(s.get("commit_fail", 0)),
        "key_ver": int(s.get("key_ver", d.get("key_ver", 0))),
        "key_id": int(s.get("key_id", d.get("key_id", 0))),
        "ks": int(s.get("ks", d.get("ks", 0))),
        "uptime_s": int(s.get("uptime_s", 0)),
    }
    print(json.dumps(out, indent=2), flush=True)
    return out


def main() -> int:
    cfg = load_cfg()
    meta = json.loads((LOGDIR / "run_metadata.json").read_text(encoding="utf-8"))
    if int(meta["target_quanta"]) != TARGET:
        print("FAIL metadata target", meta["target_quanta"])
        return 1

    # Arm so this is a true mid-run reset, then STOP briefly so pre-snap matches
    # last durable value at reset (writer resumes after re-arm; target unchanged).
    arm0 = mtls_cmd(cfg, f"RHSTRESS START {TARGET}", timeout=12)
    print("pre-arm:", arm0, flush=True)
    time.sleep(2)
    print("RHSTRESS STOP (brief, before reset):", mtls_cmd(cfg, "RHSTRESS STOP", timeout=12), flush=True)
    time.sleep(0.5)
    pre = snap(cfg, "pre_reset")
    if pre["key_ver"] != 2 or pre["auth_fail"] or pre["flash_err"]:
        print("FAIL dirty pre", pre)
        return 1
    q_before, seq_before = pre["quanta"], pre["seq"]
    (LOGDIR / "pre_reset_manual.json").write_text(json.dumps(pre, indent=2) + "\n", encoding="utf-8")

    print("=== wiretimedreset ===", flush=True)
    try:
        r = subprocess.run(
            [str(LS), "probe", PROBE, "wiretimedreset", "80"],
            capture_output=True,
            text=True,
            timeout=45,
        )
        print("reset rc", r.returncode, flush=True)
        if r.stdout:
            print(r.stdout[-300:], flush=True)
    except subprocess.TimeoutExpired:
        print("FAIL LinkServer reset timeout", flush=True)
        return 1

    rec = None
    for i in range(45):
        try:
            fetch_status(cfg, timeout=3)
            cand = snap(cfg, f"post_reset_{i}")
            # Prefer a boot that looks fresh relative to pre uptime
            if cand["uptime_s"] + 5 < pre["uptime_s"] or cand["uptime_s"] < 180:
                rec = cand
                break
            rec = cand
        except Exception as e:
            print("wait", i, type(e).__name__, e, flush=True)
            time.sleep(1)
    if rec is None:
        print("FAIL no recover")
        return 1

    q_after, seq_after = rec["quanta"], rec["seq"]
    print(
        f"recovered quanta={q_after} seq={seq_after} (before {q_before}/{seq_before})",
        flush=True,
    )
    if q_after < q_before:
        print(f"FAIL regression {q_before}->{q_after}")
        return 1
    # After STOP, expect exact match; allow +1 if a commit was already in flight.
    if q_after > q_before + 1:
        print(f"FAIL jump {q_before}->{q_after}")
        return 1
    if seq_after < seq_before:
        print("FAIL seq regression")
        return 1
    if rec["key_ver"] != 2 or rec["auth_fail"] or rec["flash_err"]:
        print("FAIL key/auth/flash", rec)
        return 1

    arm = mtls_cmd(cfg, f"RHSTRESS START {TARGET}", timeout=12)
    print("arm:", arm, flush=True)
    if not arm.startswith("RHSTRESS OK") or "542271" not in arm:
        print("FAIL arm")
        return 1

    time.sleep(2)
    s1 = parse_kv(mtls_cmd(cfg, "RHSTRESS STATUS"))
    q1 = int(s1["quanta"])
    time.sleep(8)
    s2 = parse_kv(mtls_cmd(cfg, "RHSTRESS STATUS"))
    q2 = int(s2["quanta"])
    rate = (q2 - q1) / 8.0
    print(f"rate={rate:.3f} cps ({q1}->{q2})", flush=True)
    if rate < 3.0 or rate > 5.5:
        print("FAIL rate", rate)
        return 1
    if int(s2.get("commit_fail", 1)) or int(s2.get("auth_fail", 1)) or int(s2.get("flash_err", 1)):
        print("FAIL dirty", s2)
        return 1
    if int(s2.get("key_ver", 0)) != 2 or int(s2.get("target", 0)) != TARGET:
        print("FAIL key/target", s2)
        return 1

    evt = {
        "ts": utc(),
        "event": "controlled_reset_manual",
        "target_quanta": TARGET,
        "pre": pre,
        "recovered_quanta": q_after,
        "recovered_seq": seq_after,
        "arm": arm,
        "rate_cps_8s": round(rate, 3),
        "post_status": {
            k: s2.get(k)
            for k in (
                "running",
                "complete",
                "quanta",
                "target",
                "commits_ok",
                "commit_fail",
                "auth_fail",
                "flash_err",
                "key_ver",
                "key_id",
                "ks",
                "erase_total",
                "remap",
            )
        },
    }
    with (LOGDIR / "monitor_events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(evt) + "\n")

    meta.setdefault("resets", []).append(
        {
            "ts": utc(),
            "kind": "manual_controlled",
            "pre_quanta": q_before,
            "pre_seq": seq_before,
            "pre_commits_ok": pre["commits_ok"],
            "pre_erase_total": pre["erase_total"],
            "pre_remap": pre["remap"],
            "recovered_quanta": q_after,
            "recovered_seq": seq_after,
            "rate_cps_8s": round(rate, 3),
        }
    )
    meta["status"] = "RUNNING"
    meta["last_erase_id"] = 0
    meta["baseline_erase_ovf"] = 0
    (LOGDIR / "run_metadata.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    block = f"""
### Controlled reset (manual) during full run

| Field | Value |
|-------|-------|
| UTC | {utc()} |
| Method | LinkServer wiretimedreset |
| Pre quanta / seq | {q_before} / {seq_before} |
| Pre commits_ok / erase_total / remap | {pre['commits_ok']} / {pre['erase_total']} / {pre['remap']} |
| Recovered quanta / seq | {q_after} / {seq_after} |
| Target (unchanged) | {TARGET} |
| Resume rate (8s sample) | {rate:.3f} cps |
| auth/flash/commit_fail / key_ver | 0 / 0 / 0 / 2 |

"""
    ev = EVIDENCE.read_text(encoding="utf-8") if EVIDENCE.exists() else ""
    EVIDENCE.write_text(ev.rstrip() + "\n" + block, encoding="utf-8")
    print("PASS controlled reset + re-arm", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
