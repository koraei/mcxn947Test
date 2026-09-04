#!/usr/bin/env python3
"""Gate 10 HW campaign: journal recoverability via reset-at-stage + rollover + remap OTA."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mcxn_lib import load_cfg, load_unit, fetch_hello, fetch_status  # noqa: E402
from mcxn_lib.mtls import connect_mtls  # noqa: E402
from mcxn_lib.workflow import cmd_update  # noqa: E402

LS = Path(r"C:\nxp\LinkServer_25.6.131\LinkServer.exe")
PROBE = "MNZW4VYTFX113"


def mtls_cmd(cfg: dict, cmd: str, timeout: float = 8.0) -> str:
    unit = load_unit(cfg["unit_name"])
    with connect_mtls(cfg, int(cfg.get("hello_port", 5000)), timeout=timeout, unit=unit) as s:
        s.sendall((cmd + "\n").encode())
        return s.recv(512).decode("utf-8", "replace").strip()


def reset_board() -> None:
    subprocess.run(
        [str(LS), "probe", PROBE, "wiretimedreset", "80"],
        capture_output=True,
        check=False,
    )
    time.sleep(8)


def wait_hello(cfg: dict, tries: int = 20) -> None:
    for _ in range(tries):
        try:
            fetch_hello(cfg, timeout=3)
            return
        except OSError:
            time.sleep(1)
    raise RuntimeError("board not reachable after reset")


def parse_rhdiag(text: str) -> dict:
    # RHDIAG seq=.. quanta=.. ...
    out: dict = {}
    for m in re.finditer(r"(\w+)=(\d+)", text):
        out[m.group(1)] = int(m.group(2))
    return out


def case(results: dict, name: str, fn) -> None:  # noqa: ANN001
    try:
        fn()
        results["cases"].append({"name": name, "pass": True})
        print("PASS", name)
    except Exception as e:
        results["cases"].append({"name": name, "pass": False, "error": f"{type(e).__name__}: {e}"})
        results["pass"] = False
        print("FAIL", name, e)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--sb3-v2", type=Path, default=ROOT / "dist/DEV-UNIT-01/2.0.1/DEV-UNIT-01_2.0.1_V2.sb3")
    p.add_argument("--sb3-newer", type=Path, default=ROOT / "dist/DEV-UNIT-01/3.2.1/DEV-UNIT-01_3.2.1_V3.sb3")
    p.add_argument("--expect-v2", default="2.0.1")
    p.add_argument("--expect-newer", default="3.2.1")
    p.add_argument("--rollover-count", type=int, default=130, help="RHFORCE count to force sector recycle")
    p.add_argument("--skip-ota", action="store_true")
    args = p.parse_args()

    cfg = load_cfg()
    results: dict = {"cases": [], "pass": True, "diag": {}}

    def boot_diag() -> dict:
        wait_hello(cfg)
        d = parse_rhdiag(mtls_cmd(cfg, "RHDIAG"))
        if d.get("prov", 0) != 1:
            raise RuntimeError(f"not provisioned: {d}")
        return d

    def wipe_virgin() -> dict:
        wait_hello(cfg)
        wipe = mtls_cmd(cfg, "RHWIPE", timeout=120)
        if not wipe.startswith("RHWIPE 0"):
            raise RuntimeError(f"RHWIPE failed: {wipe}")
        return boot_diag()

    case(results, "wipe_virgin", lambda: results["diag"].__setitem__("boot", wipe_virgin()))

    def force_n(n: int) -> None:
        d0 = parse_rhdiag(mtls_cmd(cfg, "RHDIAG"))
        q0 = d0["quanta"]
        for i in range(n):
            r = mtls_cmd(cfg, "RHFORCE", timeout=30)
            if "OK" not in r:
                raise RuntimeError(f"RHFORCE failed @{i}: {r}")
        d1 = parse_rhdiag(mtls_cmd(cfg, "RHDIAG"))
        if d1["quanta"] != q0 + n:
            raise RuntimeError(f"quanta {d1['quanta']} != {q0}+{n}")

    case(results, "append_5", lambda: force_n(5))

    # Power-cut / reset at stages (flash-state equivalent of HW cut via wait-hook + reset)
    stages = [
        ("cut_before_record", 1),
        ("cut_during_phrase0", 2),
        ("cut_during_phrase1", 3),
        ("cut_before_commit", 5),
        ("cut_after_commit", 6),
    ]

    def fault_stage(name: str, stage: int) -> None:
        reset_board()
        wait_hello(cfg)
        d0 = parse_rhdiag(mtls_cmd(cfg, "RHDIAG"))
        if d0.get("prov", 0) != 1:
            wipe = mtls_cmd(cfg, "RHWIPE", timeout=180)
            if not wipe.startswith("RHWIPE 0"):
                raise RuntimeError(f"re-wipe failed: {wipe}")
            d0 = parse_rhdiag(mtls_cmd(cfg, "RHDIAG"))
        q0 = d0["quanta"]
        arm = mtls_cmd(cfg, f"RHFAULT {stage}")
        if f"armed={stage}" not in arm:
            raise RuntimeError(arm)
        try:
            mtls_cmd(cfg, "RHFORCE", timeout=2)
        except Exception:
            pass
        time.sleep(0.5)
        reset_board()
        wait_hello(cfg)
        mtls_cmd(cfg, "RHFAULT 0")
        d1 = parse_rhdiag(mtls_cmd(cfg, "RHDIAG"))
        q1 = d1["quanta"]
        if stage == 6:
            if q1 not in (q0, q0 + 1):
                raise RuntimeError(f"after_commit unexpected quanta {q1} vs {q0}")
        else:
            if q1 != q0:
                raise RuntimeError(f"{name}: quanta changed {q0}->{q1}")

    for name, st in stages:
        case(results, name, lambda n=name, s=st: fault_stage(n, s))

    case(results, "sector_rollover", lambda: force_n(args.rollover_count))

    d_roll = parse_rhdiag(mtls_cmd(cfg, "RHDIAG"))
    results["diag"]["after_rollover"] = d_roll
    if d_roll.get("erases", 0) < 1:
        results["cases"].append({"name": "rollover_erase_observed", "pass": False, "error": "no erase"})
        results["pass"] = False
        print("FAIL rollover_erase_observed")
    else:
        results["cases"].append({"name": "rollover_erase_observed", "pass": True})
        print("PASS rollover_erase_observed erases=", d_roll["erases"])

    quanta_before_ota = parse_rhdiag(mtls_cmd(cfg, "RHDIAG"))["quanta"]

    if not args.skip_ota:
        def ota_remap_and_back() -> None:
            # Ensure window
            reset_board()
            wait_hello(cfg)
            q0 = parse_rhdiag(mtls_cmd(cfg, "RHDIAG"))["quanta"]
            rc = cmd_update(
                cfg,
                args.sb3_v2,
                expect_version=args.expect_v2,
                expect_variant="V2",
                transfer_timeout=180.0,
                reboot_timeout=90.0,
            )
            if rc != 0:
                raise RuntimeError("OTA to V2 failed")
            wait_hello(cfg)
            d = parse_rhdiag(mtls_cmd(cfg, "RHDIAG"))
            if d["quanta"] != q0:
                raise RuntimeError(f"quanta changed across OTA V2: {q0}->{d['quanta']}")
            if d.get("remap", 0) != 1:
                raise RuntimeError(f"expected remap=1 after V2, got {d}")
            # Force one more quantum on remapped image
            r = mtls_cmd(cfg, "RHFORCE", timeout=30)
            if "OK" not in r:
                raise RuntimeError(r)
            q1 = parse_rhdiag(mtls_cmd(cfg, "RHDIAG"))["quanta"]
            reset_board()
            wait_hello(cfg)
            rc = cmd_update(
                cfg,
                args.sb3_newer,
                expect_version=args.expect_newer,
                expect_variant="V3",
                transfer_timeout=180.0,
                reboot_timeout=90.0,
            )
            if rc != 0:
                raise RuntimeError("OTA back to newer V3 failed")
            wait_hello(cfg)
            d2 = parse_rhdiag(mtls_cmd(cfg, "RHDIAG"))
            if d2["quanta"] != q1:
                raise RuntimeError(f"quanta changed across OTA V3: {q1}->{d2['quanta']}")
            if d2.get("remap", 0) != 0:
                raise RuntimeError(f"expected remap=0 after V3, got {d2}")
            results["diag"]["post_ota"] = d2

        case(results, "ota_remap_journal_survives", ota_remap_and_back)

    results["diag"]["quanta_before_ota_block"] = quanta_before_ota
    out = ROOT / "docs/evidence/RUNHOURS_HW_CAMPAIGN.json"
    out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"pass": results["pass"], "out": str(out)}, indent=2))
    return 0 if results["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
