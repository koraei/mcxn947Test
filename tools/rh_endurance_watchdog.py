#!/usr/bin/env python3
"""Watchdog for rh endurance full run: re-arm if writer idle; restart monitor if dead."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mcxn_lib import load_cfg  # noqa: E402
from rh_endurance_monitor import mtls_cmd, parse_kv  # noqa: E402

LOGDIR = Path(r"C:\mcxn\builds\rh_endurance_4hz\full")
META = LOGDIR / "run_metadata.json"
WATCH = LOGDIR / "watchdog.log"


def log(msg: str) -> None:
    line = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + " " + msg
    print(line, flush=True)
    WATCH.parent.mkdir(parents=True, exist_ok=True)
    with WATCH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def monitor_alive() -> bool:
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "Where-Object { $_.CommandLine -match 'rh-stress-monitor' } | "
             "Select-Object -ExpandProperty ProcessId"],
            text=True,
            timeout=30,
        )
        return bool(out.strip())
    except Exception:
        return False


def main() -> int:
    cfg = load_cfg()
    if not META.is_file():
        log("no metadata yet")
        return 0
    meta = json.loads(META.read_text(encoding="utf-8"))
    if meta.get("status") in ("COMPLETE", "FAILED"):
        log(f"terminal status={meta.get('status')}")
        return 0
    target = int(meta["target_quanta"])
    try:
        st = parse_kv(mtls_cmd(cfg, "RHSTRESS STATUS", timeout=15))
        diag = parse_kv(mtls_cmd(cfg, "RHDIAG", timeout=15))
    except Exception as e:
        log(f"mtls error: {e}")
        return 1
    q = int(st.get("quanta", diag.get("quanta", -1)))
    running = int(st.get("running", 0))
    complete = int(st.get("complete", 0))
    log(f"watch q={q} target={target} running={running} complete={complete} mon={monitor_alive()}")
    if q >= target or complete:
        log("device already complete")
        return 0
    if running == 0:
        arm = mtls_cmd(cfg, f"RHSTRESS START {target}")
        log(f"re-armed: {arm}")
    if not monitor_alive():
        log("restarting host monitor")
        subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "tools" / "mcxn.py"),
                "rh-stress-monitor",
                "--logdir",
                str(LOGDIR),
                "--target-delta",
                str(meta.get("target_delta", 525600)),
                "--poll-s",
                "60",
                "--auto-reset-at",
                "5,25,50,75",
                "--max-hours",
                "48",
            ],
            cwd=str(ROOT),
            stdout=open(LOGDIR / "tee_watchdog_restart.txt", "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
