#!/usr/bin/env python3
"""Authoritative host CLI for FRDM-MCXN947 secure Ethernet OTA (P6).

Firmware protocol is frozen: OTAS header + raw SB3 on TCP :5555.
Secrets stay under secrets_root; dist/ never receives keys.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow `python tools/mcxn.py` without installing a package.
_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from mcxn_lib import fetch_echo, fetch_hello, fetch_status, load_cfg  # noqa: E402
from mcxn_lib.mtls import FingerprintError  # noqa: E402
from mcxn_lib.workflow import (  # noqa: E402
    cmd_build,
    cmd_doctor,
    cmd_package,
    cmd_release,
    cmd_reset,
    cmd_update,
    run,
)


def cmd_flash(cfg: dict, target: str) -> int:
    build_root = Path(cfg["build_root"])
    mapping = {
        "v1": build_root / "app_v1",
        "v2": build_root / "app_v2",
        "v3": build_root / "app_v3",
        "mcuboot": build_root / "mcuboot_opensource",
    }
    bdir = mapping.get(target)
    if not bdir or not bdir.exists():
        print("Build dir missing for", target, bdir, file=sys.stderr)
        return 2
    return run(
        [sys.executable, "-m", "west", "flash", "-d", str(bdir), "-r", "linkserver"],
        cfg,
        cwd=Path(cfg["sdk_root"]),
    )


def cmd_serial(cfg: dict, seconds: float) -> int:
    try:
        import serial
    except ImportError:
        print("pyserial required", file=sys.stderr)
        return 1
    import time

    ser = serial.Serial(cfg["com_port"], cfg["baud"], timeout=0.2)
    t0 = time.time()
    try:
        while time.time() - t0 < seconds:
            data = ser.read(256)
            if data:
                sys.stdout.write(data.decode("utf-8", "replace"))
                sys.stdout.flush()
    finally:
        ser.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    cfg = load_cfg()
    p = argparse.ArgumentParser(prog="mcxn", description="FRDM-MCXN947 secure OTA host CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="Verify toolchain, board, ping, Hello/STATUS")

    b = sub.add_parser("build", help="Build V1/V2/V3/MCUboot reproducibly")
    b.add_argument("target", choices=["v1", "v2", "v3", "mcuboot"])
    b.add_argument("--version", default=None, help="APP_VERSION_STRING override (v1/v2/v3)")
    b.add_argument(
        "--qa",
        action="store_true",
        help="Build with APP_QA_STREAM=1 into app_<target>_qa (M4 soak only; not for release)",
    )
    b.add_argument(
        "--lean",
        action="store_true",
        help="LEAN_PROD_TEST: mbedtls allow-list USER_CONFIG + -Os into app_<target>_lean",
    )
    b.add_argument(
        "--layout512",
        action="store_true",
        help="Build-only APP_FLASH_LAYOUT_512K (no CMPA write); use with --lean",
    )
    b.add_argument(
        "--rh-endurance",
        action="store_true",
        help="QA APP_RH_ENDURANCE_TEST=1 (4Hz journal); requires --layout512; not for release",
    )

    f = sub.add_parser("flash", help="west flash via LinkServer")
    f.add_argument("target", choices=["v1", "v2", "v3", "mcuboot"])

    s = sub.add_parser("serial", help="Read VCOM (RX); TX may fail on this probe")
    s.add_argument("--seconds", type=float, default=10.0)

    sub.add_parser("hello")
    sub.add_parser("status")
    sub.add_parser("reset", help="MCU-Link reset via LinkServer")
    e = sub.add_parser("echo", help="Send ECHO on Hello TCP :5000")
    e.add_argument("payload", nargs="?", default="ping")

    rhmon = sub.add_parser("rh-stress-monitor", help="QA 4Hz run-hours endurance host monitor")
    rhmon.add_argument("--logdir", type=Path, default=Path(r"C:\mcxn\builds\rh_endurance_4hz"))
    rhmon.add_argument("--new-run", action="store_true", help="Force new baseline (refuse if unfinished without this)")
    rhmon.add_argument("--target-delta", type=int, default=525600)
    rhmon.add_argument("--poll-s", type=float, default=60.0)
    rhmon.add_argument("--smoke-delta", type=int, default=0, help="If >0, use as target_delta (smoke/pilot)")
    rhmon.add_argument("--auto-reset-at", type=str, default="", help="Comma percent milestones e.g. 5,25,50,75")
    rhmon.add_argument("--max-hours", type=float, default=0.0, help="Optional wall-clock abort (0=none)")

    pkg = sub.add_parser("package", help="Sign + unit SB3 + sidecar manifest (no secrets in dist)")
    pkg.add_argument("--unit", default=cfg.get("unit_name", "DEV-UNIT-01"))
    pkg.add_argument("--version", required=True)
    pkg.add_argument("--build", action="store_true", help="Build variant before packaging")
    pkg.add_argument(
        "--lean",
        action="store_true",
        help="Use lean build dir (app_*_lean); required with --layout512 for fit",
    )
    pkg.add_argument(
        "--layout512",
        action="store_true",
        help="Sign/package for 512 KiB slots (imgtool+SB3 erase 0x80000); no CMPA write",
    )

    rel = sub.add_parser("release", help="build + package into dist/<unit>/<version>/")
    rel.add_argument("--unit", default=cfg.get("unit_name", "DEV-UNIT-01"))
    rel.add_argument("--version", required=True)

    u = sub.add_parser("update", help="OTAS/TCP:5555 update with preflight + verify")
    u.add_argument("--sb3", required=True, type=Path)
    u.add_argument("--manifest", type=Path, default=None)
    u.add_argument("--uuid", default=None, help="Override wire UUID (rare)")
    u.add_argument("--allow-no-manifest", action="store_true")
    u.add_argument(
        "--bypass-uuid-check",
        action="store_true",
        help="Test-only: skip host UUID mismatch refuse (device SB3 remains the security boundary)",
    )
    u.add_argument("--expect-version", default=None)
    u.add_argument("--expect-variant", default=None)
    u.add_argument("--transfer-timeout", type=float, default=120.0)
    u.add_argument("--reboot-timeout", type=float, default=60.0)

    args = p.parse_args(argv)

    if args.cmd == "doctor":
        return cmd_doctor(cfg)
    if args.cmd == "build":
        return cmd_build(
            cfg,
            args.target,
            version=args.version,
            qa=bool(getattr(args, "qa", False)),
            lean=bool(getattr(args, "lean", False)),
            layout512=bool(getattr(args, "layout512", False)),
            rh_endurance=bool(getattr(args, "rh_endurance", False)),
        )
    if args.cmd == "flash":
        return cmd_flash(cfg, args.target)
    if args.cmd == "serial":
        return cmd_serial(cfg, args.seconds)
    if args.cmd == "hello":
        try:
            print(fetch_hello(cfg))
            return 0
        except OSError as e:
            print(e, file=sys.stderr)
            return 1
    if args.cmd == "status":
        try:
            print(fetch_status(cfg).raw)
            return 0
        except OSError as e:
            print(e, file=sys.stderr)
            return 1
    if args.cmd == "echo":
        try:
            print(fetch_echo(cfg, args.payload))
            return 0
        except OSError as e:
            print(e, file=sys.stderr)
            return 1
    if args.cmd == "reset":
        return cmd_reset(cfg)
    if args.cmd == "rh-stress-monitor":
        from rh_endurance_monitor import main as rh_mon_main  # noqa: WPS433

        delta = int(args.smoke_delta) if int(args.smoke_delta) > 0 else int(args.target_delta)
        return rh_mon_main(
            cfg,
            logdir=args.logdir,
            new_run=bool(args.new_run),
            target_delta=delta,
            poll_s=float(args.poll_s),
            auto_reset_at=args.auto_reset_at,
            max_hours=float(args.max_hours),
        )
    if args.cmd == "package":
        return cmd_package(
            cfg,
            args.unit,
            args.version,
            build_first=args.build,
            lean=bool(getattr(args, "lean", False)),
            layout512=bool(getattr(args, "layout512", False)),
        )
    if args.cmd == "release":
        return cmd_release(cfg, args.unit, args.version)
    if args.cmd == "update":
        return cmd_update(
            cfg,
            args.sb3,
            uuid_hex=args.uuid,
            manifest_path=args.manifest,
            allow_no_manifest=args.allow_no_manifest,
            bypass_uuid_check=args.bypass_uuid_check,
            expect_version=args.expect_version,
            expect_variant=args.expect_variant,
            transfer_timeout=args.transfer_timeout,
            reboot_timeout=args.reboot_timeout,
        )
    return 2


if __name__ == "__main__":
    sys.exit(main())
