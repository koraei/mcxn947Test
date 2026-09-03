#!/usr/bin/env python3
"""Thin host CLI for FRDM-MCXN947 secure Ethernet OTA prototype."""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

ROOT = Path(__file__).resolve().parents[1]


def load_cfg() -> dict:
    path = ROOT / "mcxn.toml"
    with path.open("rb") as f:
        return tomllib.load(f)


def env_for_build(cfg: dict) -> dict:
    env = os.environ.copy()
    arm = cfg["armgcc_dir"]
    ls = str(Path(cfg["linkserver"]).parent)
    env["ARMGCC_DIR"] = arm
    env["PATH"] = str(Path(arm) / "bin") + os.pathsep + ls + os.pathsep + env.get("PATH", "")
    return env


def run(cmd: list[str], cfg: dict, cwd: Path | None = None) -> int:
    print("+", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=cwd or cfg["sdk_root"], env=env_for_build(cfg))


def cmd_doctor(cfg: dict) -> int:
    print("SDK root:", cfg["sdk_root"])
    print("Board:", cfg["board"], "core:", cfg["core_id"])
    print("Board IP:", cfg["board_ip"], "hello:", cfg["hello_port"], "update:", cfg["update_port"])
    print("COM:", cfg["com_port"], "@", cfg["baud"])
    print("Probe:", cfg.get("probe_serial"))
    gcc = Path(cfg["armgcc_dir"]) / "bin" / "arm-none-eabi-gcc.exe"
    print("armgcc:", gcc, "exists" if gcc.exists() else "MISSING")
    print("LinkServer:", cfg["linkserver"], "exists" if Path(cfg["linkserver"]).exists() else "MISSING")
    rc = run([sys.executable, "-m", "west", "topdir"], cfg)
    # Probe
    run([cfg["linkserver"], "probes"], cfg)
    # Ping board
    print("Ping board IP...")
    ping = ["ping", "-n", "2", cfg["board_ip"]] if os.name == "nt" else ["ping", "-c", "2", cfg["board_ip"]]
    subprocess.call(ping)
    # Hello try
    try:
        with socket.create_connection((cfg["board_ip"], cfg["hello_port"]), timeout=2) as s:
            s.sendall(b"STATUS\n")
            data = s.recv(256)
            print("STATUS reply:", data.decode("utf-8", "replace").strip())
    except OSError as e:
        print("Hello/STATUS not reachable yet:", e)
    return rc


def variant_defs_path(cfg: dict, variant: str) -> Path:
    build_root = Path(cfg["build_root"])
    build_root.mkdir(parents=True, exist_ok=True)
    path = build_root / f"app_{variant}_defs.h"
    if variant == "v2":
        body = """#define APP_VARIANT \"V2\"
#define APP_VERSION_STRING \"2.0.0\"
#define APP_VARIANT_IS_V2 1
#define APP_LED_ON_MS 125
#define APP_LED_OFF_MS 125
#define IP_ADDR \"192.168.2.90\"
#define IP_MASK \"255.255.255.0\"
#define GW_ADDR \"192.168.2.24\"
"""
    else:
        body = """#define APP_VARIANT \"V1\"
#define APP_VERSION_STRING \"1.0.0\"
#define APP_LED_ON_MS 500
#define APP_LED_OFF_MS 500
#define IP_ADDR \"192.168.2.90\"
#define IP_MASK \"255.255.255.0\"
#define GW_ADDR \"192.168.2.24\"
"""
    path.write_text(body, encoding="ascii")
    return path


def cmd_build(cfg: dict, target: str) -> int:
    sdk = Path(cfg["sdk_root"])
    build_root = Path(cfg["build_root"])
    build_root.mkdir(parents=True, exist_ok=True)
    board = cfg["board"]
    core = cfg["core_id"]

    if target in ("v1", "v2"):
        app = ROOT / cfg["paths"]["app"]
        bdir = build_root / f"app_{target}"
        defs = variant_defs_path(cfg, target)
        # PowerShell-safe: pass EXTRA_CFLAGS as -include <defs>
        extra = f"-include {defs.as_posix()}"
        cmd = [
            sys.executable,
            "-m",
            "west",
            "build",
            "-b",
            board,
            "-d",
            str(bdir),
            str(app),
            f"-Dcore_id={core}",
            "--toolchain",
            "armgcc",
            "--config",
            "debug",
            "-p",
            "auto",
            f"--cmake-opt=-DEXTRA_CFLAGS={extra}",
        ]
        return run(cmd, cfg, cwd=sdk)

    if target == "mcuboot":
        src = cfg["paths"]["mcuboot_example"]
        bdir = build_root / "mcuboot_opensource"
        cmd = [
            sys.executable,
            "-m",
            "west",
            "build",
            "-b",
            board,
            "-d",
            str(bdir),
            src,
            f"-Dcore_id={core}",
            "--toolchain",
            "armgcc",
            "--config",
            "debug",
            "-p",
            "auto",
        ]
        return run(cmd, cfg, cwd=sdk)

    print("Unknown target", target, file=sys.stderr)
    return 2


def find_elf(build_dir: Path) -> Path | None:
    elves = list(build_dir.glob("*.elf"))
    return elves[0] if elves else None


def cmd_flash(cfg: dict, target: str) -> int:
    build_root = Path(cfg["build_root"])
    mapping = {
        "v1": build_root / "app_v1",
        "v2": build_root / "app_v2",
        "mcuboot": build_root / "mcuboot_opensource",
        "hello_world": build_root / "hello_world",
        "lwip_ping": build_root / "lwip_ping_freertos_static",
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


def cmd_hello(cfg: dict) -> int:
    with socket.create_connection((cfg["board_ip"], cfg["hello_port"]), timeout=5) as s:
        s.sendall(b"Hello MCXN\n")
        data = s.recv(128)
    text = data.decode("utf-8", "replace")
    print(text.strip())
    return 0 if "Hello PC!" in text else 1


def cmd_status(cfg: dict) -> int:
    with socket.create_connection((cfg["board_ip"], cfg["hello_port"]), timeout=5) as s:
        s.sendall(b"STATUS\n")
        data = s.recv(256)
    print(data.decode("utf-8", "replace").strip())
    return 0


def parse_uuid_hex(text: str) -> bytes:
    h = "".join(c for c in text.strip() if c not in " :-")
    if len(h) != 32:
        raise ValueError(f"UUID must be 32 hex chars, got {len(h)}")
    return bytes.fromhex(h)


def fetch_board_uuid(cfg: dict) -> bytes:
    with socket.create_connection((cfg["board_ip"], cfg["hello_port"]), timeout=5) as s:
        s.sendall(b"STATUS\n")
        data = s.recv(256).decode("utf-8", "replace")
    # STATUS ... uuid=HEX ...
    for part in data.replace("\n", " ").split():
        if part.startswith("uuid="):
            return parse_uuid_hex(part.split("=", 1)[1])
    raise RuntimeError(f"uuid= not found in STATUS: {data!r}")


def cmd_update(cfg: dict, sb3_path: Path, uuid_hex: str | None) -> int:
    """Send [28-byte OTAS header][raw SB3] to TCP update port."""
    path = Path(sb3_path)
    blob = path.read_bytes()
    if len(blob) < 64 or blob[:4] != b"sbv3":
        print("Not an SB3 file (missing sbv3 magic):", path, file=sys.stderr)
        return 2

    uuid_b = parse_uuid_hex(uuid_hex) if uuid_hex else fetch_board_uuid(cfg)
    hdr = bytearray(28)
    hdr[0:4] = b"OTAS"
    hdr[4] = 1
    hdr[8:24] = uuid_b
    hdr[24:28] = len(blob).to_bytes(4, "little")

    port = int(cfg["update_port"])
    print(f"Connecting {cfg['board_ip']}:{port} SB3={path.name} ({len(blob)} bytes)", flush=True)
    with socket.create_connection((cfg["board_ip"], port), timeout=10) as s:
        s.settimeout(120)
        s.sendall(bytes(hdr) + blob)
        try:
            resp = s.recv(128)
        except OSError as e:
            # Device may reset immediately after OK.
            print("recv after send:", e)
            resp = b""
    text = resp.decode("utf-8", "replace").strip() if resp else "(no reply — check reset/boot)"
    print("Update reply:", text)
    return 0 if text.startswith("OK") or resp == b"" else 1


def main() -> int:
    cfg = load_cfg()
    p = argparse.ArgumentParser(prog="mcxn")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor")
    b = sub.add_parser("build")
    b.add_argument("target", choices=["v1", "v2", "mcuboot"])
    f = sub.add_parser("flash")
    f.add_argument("target")
    s = sub.add_parser("serial")
    s.add_argument("--seconds", type=float, default=10.0)
    sub.add_parser("hello")
    sub.add_parser("status")
    u = sub.add_parser("update")
    u.add_argument("--sb3", required=True, type=Path, help="Path to SB3.1 container")
    u.add_argument("--uuid", default=None, help="32-hex UUID (default: from STATUS)")

    args = p.parse_args()
    if args.cmd == "doctor":
        return cmd_doctor(cfg)
    if args.cmd == "build":
        return cmd_build(cfg, args.target)
    if args.cmd == "flash":
        return cmd_flash(cfg, args.target)
    if args.cmd == "serial":
        return cmd_serial(cfg, args.seconds)
    if args.cmd == "hello":
        return cmd_hello(cfg)
    if args.cmd == "status":
        return cmd_status(cfg)
    if args.cmd == "update":
        return cmd_update(cfg, args.sb3, args.uuid)
    return 2


if __name__ == "__main__":
    sys.exit(main())
