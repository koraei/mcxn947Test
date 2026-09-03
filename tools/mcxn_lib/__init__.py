# Host-side helpers for tools/mcxn.py (P6). Firmware protocol remains OTAS/TCP:5555.
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

ROOT = Path(__file__).resolve().parents[2]


def load_cfg(path: Path | None = None) -> dict:
    cfg_path = path or (ROOT / "mcxn.toml")
    with cfg_path.open("rb") as f:
        return tomllib.load(f)


def env_for_build(cfg: dict) -> dict:
    env = os.environ.copy()
    arm = cfg["armgcc_dir"]
    ls = str(Path(cfg["linkserver"]).parent)
    dist = str(Path(cfg["linkserver"]).parent / "dist")
    env["ARMGCC_DIR"] = arm
    extra = os.pathsep.join(
        [
            str(Path(arm) / "bin"),
            ls,
            dist,
            str(Path(sys.executable).parent),
            str(Path(sys.executable).parent / "Scripts"),
        ]
    )
    env["PATH"] = extra + os.pathsep + env.get("PATH", "")
    return env


def run(cmd: list[str], cfg: dict, cwd: Path | None = None, check: bool = False) -> int:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    rc = subprocess.call([str(c) for c in cmd], cwd=str(cwd or cfg["sdk_root"]), env=env_for_build(cfg))
    if check and rc != 0:
        raise RuntimeError(f"command failed ({rc}): {' '.join(str(c) for c in cmd)}")
    return rc


def run_capture(cmd: list[str], cfg: dict, cwd: Path | None = None) -> tuple[int, str]:
    p = subprocess.run(
        [str(c) for c in cmd],
        cwd=str(cwd or cfg["sdk_root"]),
        env=env_for_build(cfg),
        capture_output=True,
        text=True,
        errors="replace",
    )
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_commit(repo: Path = ROOT) -> str:
    try:
        p = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
        )
        if p.returncode == 0:
            return p.stdout.strip()
    except OSError:
        pass
    return "unknown"


def tool_versions(cfg: dict) -> dict[str, str]:
    vers: dict[str, str] = {
        "python": sys.version.split()[0],
        "git_commit": git_commit(),
    }
    # west
    rc, out = run_capture([sys.executable, "-m", "west", "--version"], cfg)
    vers["west"] = out.strip().splitlines()[-1] if out.strip() else f"rc={rc}"
    # gcc
    gcc = Path(cfg["armgcc_dir"]) / "bin" / "arm-none-eabi-gcc.exe"
    if gcc.exists():
        rc, out = run_capture([str(gcc), "--version"], cfg)
        vers["armgcc"] = out.splitlines()[0] if out else "unknown"
    else:
        vers["armgcc"] = "MISSING"
    # spsdk / nxpimage
    try:
        import spsdk  # type: ignore

        vers["spsdk"] = getattr(spsdk, "__version__", "unknown")
    except Exception:
        vers["spsdk"] = "MISSING"
    rc, out = run_capture(["nxpimage", "--version"], cfg)
    vers["nxpimage"] = out.strip().splitlines()[0] if out.strip() else f"rc={rc}"
    # securep
    sec = Path(cfg.get("securep", "C:/nxp/SEC_Provi_26.06/bin/securep.exe"))
    if sec.exists():
        rc, out = run_capture([str(sec), "--version"], cfg)
        line = next((ln for ln in out.splitlines() if "Version" in ln or "Secure" in ln), out.strip()[:80])
        vers["securep"] = line.strip() or "present"
    else:
        vers["securep"] = "MISSING"
    vers["linkserver"] = str(cfg.get("linkserver", ""))
    vers["sdk_root"] = str(cfg.get("sdk_root", ""))
    return vers


def load_unit(unit_name: str) -> dict:
    path = ROOT / "units" / f"{unit_name}.json"
    if not path.exists():
        raise FileNotFoundError(f"unit registry missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def secrets_dir(cfg: dict, unit: dict) -> Path:
    return Path(cfg["secrets_root"]) / unit["secrets_dirname"]


def read_cust_mk_sk_hex(cfg: dict, unit: dict) -> str:
    path = secrets_dir(cfg, unit) / unit["cust_mk_sk_file"]
    raw = path.read_text(encoding="ascii").strip()
    # allow comment lines / KEY=value
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            line = line.split("=", 1)[1].strip()
        h = "".join(c for c in line if c not in " :-")
        if len(h) == 64:
            return h.upper()
    raise ValueError(f"CUST_MK_SK hex not found in {path}")


def verify_cust_mk_sk_fingerprint(cfg: dict, unit: dict) -> None:
    key_hex = read_cust_mk_sk_hex(cfg, unit)
    fp = sha256_bytes(bytes.fromhex(key_hex))
    expected = unit.get("cust_mk_sk_fingerprint", "").lower()
    if expected and fp != expected.lower():
        raise RuntimeError(
            f"CUST_MK_SK fingerprint mismatch for {unit['unit_name']}: got {fp}, expected {expected}"
        )


def parse_uuid_hex(text: str) -> bytes:
    h = "".join(c for c in text.strip() if c not in " :-")
    if len(h) != 32:
        raise ValueError(f"UUID must be 32 hex chars, got {len(h)}")
    return bytes.fromhex(h)


def uuid_hex_str(b: bytes) -> str:
    return b.hex().upper()


@dataclass
class StatusInfo:
    raw: str
    version: str | None = None
    variant: str | None = None
    uuid: str | None = None
    uptime_s: int | None = None
    update_window_s: int | None = None


def parse_status(text: str) -> StatusInfo:
    info = StatusInfo(raw=text.strip())
    for part in text.replace("\n", " ").split():
        if part.startswith("version="):
            info.version = part.split("=", 1)[1]
        elif part.startswith("variant="):
            info.variant = part.split("=", 1)[1]
        elif part.startswith("uuid="):
            info.uuid = part.split("=", 1)[1].upper()
        elif part.startswith("uptime_s="):
            info.uptime_s = int(part.split("=", 1)[1])
        elif part.startswith("update_window_s="):
            info.update_window_s = int(part.split("=", 1)[1])
    return info


def fetch_status(cfg: dict, timeout: float = 5.0, host: str | None = None, port: int | None = None) -> StatusInfo:
    ip = host or cfg["board_ip"]
    p = int(port if port is not None else cfg["hello_port"])
    with socket.create_connection((ip, p), timeout=timeout) as s:
        s.sendall(b"STATUS\n")
        data = s.recv(256).decode("utf-8", "replace")
    return parse_status(data)


def fetch_hello(cfg: dict, timeout: float = 5.0, host: str | None = None, port: int | None = None) -> str:
    ip = host or cfg["board_ip"]
    p = int(port if port is not None else cfg["hello_port"])
    with socket.create_connection((ip, p), timeout=timeout) as s:
        s.sendall(b"Hello MCXN\n")
        return s.recv(128).decode("utf-8", "replace").strip()


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def variant_for_version(version: str) -> str:
    """Map semver major to V1/V2 product variants used by firmware defs."""
    major = int(version.split(".")[0])
    if major <= 1:
        return "V1"
    return "V2"


def find_app_bin(build_dir: Path) -> Path:
    bins = sorted(build_dir.glob("mcxn947_secure_ota*.bin"))
    if not bins:
        raise FileNotFoundError(f"no app .bin in {build_dir}")
    return bins[0]


def imgtool_path(cfg: dict) -> Path:
    return Path(cfg["sdk_root"]) / cfg["paths"]["imgtool"]


def mcuboot_sign_key(cfg: dict) -> Path:
    return Path(cfg["sdk_root"]) / cfg["paths"]["imgtool_key"]
