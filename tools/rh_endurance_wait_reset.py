#!/usr/bin/env python3
"""Wait for MCU reset (uptime drop), verify journal, re-arm RHSTRESS to 542271."""
from __future__ import annotations

import json
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
PRE_PATH = LOGDIR / "pre_reset_manual.json"
EVENTS = LOGDIR / "monitor_events.jsonl"
META = LOGDIR / "run_metadata.json"
EVIDENCE = ROOT / "docs" / "evidence" / "RUNHOURS_4HZ_10YEAR_ENDURANCE.md"


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    cfg = load_cfg()
    pre = json.loads(PRE_PATH.read_text(encoding="utf-8"))
    q_before = int(pre["quanta"])
    seq_before = int(pre["seq"])
    up_before = int(pre["uptime_s"])
    print(f"waiting for reset; pre quanta={q_before} seq={seq_before} uptime={up_before}", flush=True)

    # Detect reset: connection loss or uptime much lower than before
    saw_down = False
    deadline = time.time() + 1800  # 30 min for operator / USB recovery
    while time.time() < deadline:
        try:
            st = parse_kv(mtls_cmd(cfg, "RHSTRESS STATUS", timeout=5))
            up = int(st.get("uptime_s", 10**9))
            if up + 30 < up_before or up < 120:
                print(f"detected reboot uptime={up}", flush=True)
                break
            if not saw_down:
                print(f"still up uptime={up} (press FRDM RESET or reseat MCU-Link USB)", flush=True)
            time.sleep(2)
        except Exception as e:
            saw_down = True
            print(f"link down ({e}); waiting recover...", flush=True)
            time.sleep(2)
    else:
        print("TIMEOUT waiting for reset")
        return 1

    # Recover
    rec = None
    for i in range(40):
        try:
            fetch_status(cfg, timeout=4)
            diag = parse_kv(mtls_cmd(cfg, "RHDIAG", timeout=10))
            st = parse_kv(mtls_cmd(cfg, "RHSTRESS STATUS", timeout=10))
            rec = {**diag, **{"commits_ok": st.get("commits_ok"), "running": st.get("running"),
                              "target": st.get("target"), "uptime_s": st.get("uptime_s"),
                              "commit_fail": st.get("commit_fail"), "erase_total": st.get("erase_total")}}
            break
        except Exception as e:
            print("recover wait", i, e, flush=True)
            time.sleep(1)
    if rec is None:
        print("FAIL no recover")
        return 1

    q_after = int(rec["quanta"])
    seq_after = int(rec["seq"])
    print(f"recovered quanta={q_after} seq={seq_after}", flush=True)

    if q_after == 0 and q_before > 0:
        print("FAIL zero reset")
        return 1
    if q_after < q_before:
        print(f"FAIL regression {q_before}->{q_after}")
        return 1
    if q_after > q_before + 2:
        # allow +1 if commit landed during reset window; +2 extreme
        print(f"FAIL jump {q_before}->{q_after}")
        return 1
    if seq_after < seq_before:
        print("FAIL seq regression")
        return 1
    if int(rec.get("auth_fail", 1)) != 0 or int(rec.get("flash_err", 1)) != 0:
        print("FAIL auth/flash", rec)
        return 1
    if int(rec.get("key_ver", 0)) != 2:
        print("FAIL key", rec)
        return 1

    arm = mtls_cmd(cfg, f"RHSTRESS START {TARGET}", timeout=12)
    print("arm:", arm, flush=True)
    if not arm.startswith("RHSTRESS OK") or f"target={TARGET}" not in arm.replace(" ", ""):
        # accept "target=542271" with spaces in parse
        if "542271" not in arm:
            print("FAIL arm")
            return 1

    time.sleep(2)
    s1 = parse_kv(mtls_cmd(cfg, "RHSTRESS STATUS"))
    q1 = int(s1["quanta"])
    time.sleep(8)
    s2 = parse_kv(mtls_cmd(cfg, "RHSTRESS STATUS"))
    q2 = int(s2["quanta"])
    rate = (q2 - q1) / 8.0
    print(f"rate={rate:.3f} cps", flush=True)
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
        "note": "physical/USB reset (LinkServer DAP wedged)",
        "target_quanta": TARGET,
        "pre": pre,
        "recovered_quanta": q_after,
        "recovered_seq": seq_after,
        "arm": arm,
        "rate_cps_8s": round(rate, 3),
        "post_status": {k: s2.get(k) for k in (
            "running", "complete", "quanta", "target", "commits_ok", "commit_fail",
            "auth_fail", "flash_err", "key_ver", "key_id", "ks", "erase_total", "remap")},
    }
    with EVENTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(evt) + "\n")

    meta = json.loads(META.read_text(encoding="utf-8"))
    meta.setdefault("resets", []).append({
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
    })
    meta["status"] = "RUNNING"
    meta["last_erase_id"] = 0
    meta["baseline_erase_ovf"] = 0
    META.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    block = f"""
### Controlled reset (manual) during full run

| Field | Value |
|-------|-------|
| UTC | {utc()} |
| Method | Board RESET / USB reseat (MCU-Link DAP was wedged; LinkServer hung) |
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
