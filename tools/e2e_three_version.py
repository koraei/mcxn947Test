#!/usr/bin/env python3
"""Live three-version SB3 OTA chain: V1 -> V2 -> V3 with Hello/ECHO + resets."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from mcxn_lib import fetch_echo, fetch_hello, fetch_status, find_app_bin, load_cfg, run  # noqa: E402
from mcxn_lib.workflow import cmd_package, cmd_reset, cmd_update, sign_image  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = [
    ("1.1.0", "V1", "Hello PC! V1-SLOW-GREEN"),
    ("2.0.0", "V2", "Hello PC! V2-FAST-BLUE"),
    ("3.0.0", "V3", "Hello PC! V3-PULSE-RED"),
]


def wait_alive(cfg: dict, timeout_s: float = 60.0) -> None:
    deadline = time.time() + timeout_s
    last = ""
    while time.time() < deadline:
        try:
            st = fetch_status(cfg, timeout=3)
            last = st.raw
            if st.version:
                return
        except OSError as e:
            last = str(e)
        time.sleep(2)
    raise RuntimeError(f"board did not come up: {last}")


def probe(cfg: dict, version: str, variant: str, hello_expect: str, tag: str) -> None:
    st = fetch_status(cfg, timeout=5)
    hello = fetch_hello(cfg, timeout=5)
    echo = fetch_echo(cfg, f"e2e-{variant}-{tag}", timeout=5)
    print(f"  STATUS: {st.raw}")
    print(f"  Hello:  {hello}")
    print(f"  Echo:   {echo}")
    if st.version != version or (st.variant or "").upper() != variant:
        raise RuntimeError(f"{tag}: STATUS mismatch want {version}/{variant} got {st.raw}")
    if hello_expect not in hello:
        raise RuntimeError(f"{tag}: Hello mismatch want {hello_expect!r} got {hello!r}")
    if not echo.startswith("ECHO") or variant not in echo:
        raise RuntimeError(f"{tag}: Echo mismatch want ECHO {variant} got {echo!r}")
    if f"e2e-{variant}-{tag}" not in echo:
        raise RuntimeError(f"{tag}: Echo payload missing: {echo!r}")


def reset_and_check(cfg: dict, version: str, variant: str, hello_expect: str, n: int) -> None:
    print(f"-- reset #{n} while {variant} {version} is running --")
    rc = cmd_reset(cfg)
    if rc != 0:
        print("LinkServer reset rc=", rc, "trying nxpdebugmbox")
        subprocess.check_call(
            ["nxpdebugmbox", "-i", "mcu-link", "-s", cfg["probe_serial"], "reset"]
        )
    wait_alive(cfg)
    probe(cfg, version, variant, hello_expect, f"after-reset-{n}")


def ensure_update_window(cfg: dict) -> None:
    try:
        st = fetch_status(cfg, timeout=5)
        if st.update_window_s is not None and st.update_window_s > 20:
            return
    except OSError:
        pass
    print("-- reset to reopen 180s update window --")
    rc = cmd_reset(cfg)
    if rc != 0:
        subprocess.check_call(
            ["nxpdebugmbox", "-i", "mcu-link", "-s", cfg["probe_serial"], "reset"]
        )
    wait_alive(cfg)


def flash_v1_seed(cfg: dict) -> None:
    """Load confirmed V1 into the primary slot so the OTA chain can start at 1.0.0."""
    raw = find_app_bin(Path(cfg["build_root"]) / "app_v1")
    signed = Path(cfg["build_root"]) / "app_v1" / "app_v1_SIGNED_CONFIRM.bin"
    sign_image(cfg, raw, signed, "1.1.0", pad=True, confirm=True)
    ls = str(Path(cfg["linkserver"]))
    probe = cfg["probe_serial"]
    cmd = [ls, "flash", "-p", probe, "MCXN947:FRDM", "load", str(signed), "--addr", "0x00080000"]
    rc = run(cmd, cfg)
    if rc != 0:
        print("load @0x80000 failed, trying --addr 0x0")
        cmd[-1] = "0x0"
        rc = run(cmd, cfg)
    if rc != 0:
        raise RuntimeError("failed to flash V1 seed")
    time.sleep(2)
    cmd_reset(cfg)
    wait_alive(cfg)
    probe(cfg, "1.1.0", "V1", "Hello PC! V1-SLOW-GREEN", "v1-seed")
    reset_and_check(cfg, "1.1.0", "V1", "Hello PC! V1-SLOW-GREEN", 1)
    reset_and_check(cfg, "1.1.0", "V1", "Hello PC! V1-SLOW-GREEN", 2)


def main() -> int:
    cfg = load_cfg()
    print("=== E2E three-version SB3 chain ===")
    print("board", cfg["board_ip"])

    for ver, var, _hello in VERSIONS:
        print(f"\n=== package {ver} {var} ===")
        rc = cmd_package(cfg, cfg.get("unit_name", "DEV-UNIT-01"), ver, build_first=True)
        if rc != 0:
            return rc

    wait_alive(cfg)
    print("Starting STATUS:", fetch_status(cfg).raw)

    first = True
    for ver, var, hello_expect in VERSIONS:
        sb3 = ROOT / "dist" / "DEV-UNIT-01" / ver / f"DEV-UNIT-01_{ver}_{var}.sb3"
        print(f"\n========== OTAS UPDATE TO {var} {ver} ==========")
        ensure_update_window(cfg)
        rc = cmd_update(cfg, sb3, reboot_timeout=90.0)
        if rc != 0 and first:
            print("OTA to V1 rejected (likely version downgrade). Seeding confirmed V1 via LinkServer, then continuing OTA chain.")
            flash_v1_seed(cfg)
            first = False
            continue
        if rc != 0:
            print("OTA failed")
            return rc
        first = False
        probe(cfg, ver, var, hello_expect, "post-update")
        reset_and_check(cfg, ver, var, hello_expect, 1)
        reset_and_check(cfg, ver, var, hello_expect, 2)

    print("\n=== E2E PASS: last image is V3 3.0.0, Hello/ECHO OK after two resets ===")
    print("FINAL Hello:", fetch_hello(cfg))
    print("FINAL Echo:", fetch_echo(cfg, "last"))
    print("FINAL STATUS:", fetch_status(cfg).raw)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("E2E FAIL:", e)
        sys.exit(1)
