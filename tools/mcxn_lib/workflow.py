"""P6 doctor / build / package / update / release helpers."""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import (
    ROOT,
    env_for_build,
    fetch_hello,
    fetch_status,
    find_app_bin,
    git_commit,
    imgtool_path,
    load_manifest,
    load_unit,
    mcuboot_sign_key,
    parse_uuid_hex,
    read_cust_mk_sk_hex,
    run,
    run_capture,
    secrets_dir,
    sha256_file,
    tool_versions,
    uuid_hex_str,
    variant_for_version,
    verify_cust_mk_sk_fingerprint,
    write_json,
)


def cmd_doctor(cfg: dict) -> int:
    fails: list[str] = []
    print("=== mcxn doctor ===")
    print("repo:", ROOT)
    print("SDK root:", cfg["sdk_root"], "OK" if Path(cfg["sdk_root"]).exists() else "MISSING")
    if not Path(cfg["sdk_root"]).exists():
        fails.append("sdk_root")

    gcc = Path(cfg["armgcc_dir"]) / "bin" / "arm-none-eabi-gcc.exe"
    print("armgcc:", gcc, "OK" if gcc.exists() else "MISSING")
    if not gcc.exists():
        fails.append("armgcc")

    ls = Path(cfg["linkserver"])
    print("LinkServer:", ls, "OK" if ls.exists() else "MISSING")
    if not ls.exists():
        fails.append("linkserver")

    sec = Path(cfg.get("securep", "C:/nxp/SEC_Provi_26.06/bin/securep.exe"))
    print("SEC securep:", sec, "OK" if sec.exists() else "MISSING")
    if not sec.exists():
        fails.append("securep")

    vers = tool_versions(cfg)
    for k, v in vers.items():
        print(f"  {k}: {v}")
        if v == "MISSING" and k in ("spsdk", "securep", "armgcc"):
            if k not in fails:
                fails.append(k)

    rc, _ = run_capture([sys.executable, "-m", "west", "topdir"], cfg)
    print("west topdir:", "OK" if rc == 0 else "FAIL")
    if rc != 0:
        fails.append("west")

    print("Board:", cfg["board"], "core:", cfg["core_id"], "probe:", cfg.get("probe_serial"))
    if ls.exists():
        prc, pout = run_capture([str(ls), "probes"], cfg)
        print(pout.strip() or f"(probes rc={prc})")
        if cfg.get("probe_serial") and cfg["probe_serial"] not in pout:
            print("WARN: probe serial not seen in LinkServer probes output")

    secrets = Path(cfg["secrets_root"]) / cfg.get("unit_name", "DEV-UNIT-01")
    print("secrets:", secrets, "OK" if secrets.exists() else "MISSING")
    if not secrets.exists():
        fails.append("secrets")

    unit_path = ROOT / "units" / f"{cfg.get('unit_name', 'DEV-UNIT-01')}.json"
    print("unit registry:", unit_path, "OK" if unit_path.exists() else "MISSING")

    print("Ping board IP...")
    ping = ["ping", "-n", "2", cfg["board_ip"]] if sys.platform == "win32" else ["ping", "-c", "2", cfg["board_ip"]]
    prc = subprocess.call(ping)
    if prc != 0:
        fails.append("ping")

    try:
        st = fetch_status(cfg, timeout=3)
        print("STATUS:", st.raw)
        hello = fetch_hello(cfg, timeout=3)
        print("Hello:", hello)
        if "Hello PC!" not in hello:
            fails.append("hello")
    except OSError as e:
        print("Hello/STATUS not reachable:", e)
        fails.append("network_services")

    if fails:
        print("DOCTOR FAIL:", ", ".join(fails))
        return 1
    print("DOCTOR PASS")
    return 0


def variant_defs_path(cfg: dict, variant: str, version: str | None = None) -> Path:
    build_root = Path(cfg["build_root"])
    build_root.mkdir(parents=True, exist_ok=True)
    path = build_root / f"app_{variant.lower()}_defs.h"
    ver = version or ("2.0.0" if variant.upper() == "V2" else "1.0.0")
    ip = cfg["board_ip"]
    mask = cfg.get("board_netmask", "255.255.255.0")
    gw = cfg.get("board_gateway", "192.168.2.24")
    if variant.upper() == "V2":
        body = f"""#define APP_VARIANT \"V2\"
#define APP_VERSION_STRING \"{ver}\"
#define APP_VARIANT_IS_V2 1
#define APP_LED_ON_MS 125
#define APP_LED_OFF_MS 125
#define IP_ADDR \"{ip}\"
#define IP_MASK \"{mask}\"
#define GW_ADDR \"{gw}\"
"""
    else:
        body = f"""#define APP_VARIANT \"V1\"
#define APP_VERSION_STRING \"{ver}\"
#define APP_LED_ON_MS 500
#define APP_LED_OFF_MS 500
#define IP_ADDR \"{ip}\"
#define IP_MASK \"{mask}\"
#define GW_ADDR \"{gw}\"
"""
    path.write_text(body, encoding="ascii")
    return path


def cmd_build(cfg: dict, target: str, version: str | None = None) -> int:
    sdk = Path(cfg["sdk_root"])
    build_root = Path(cfg["build_root"])
    build_root.mkdir(parents=True, exist_ok=True)
    board = cfg["board"]
    core = cfg["core_id"]

    if target in ("v1", "v2"):
        app = ROOT / cfg["paths"]["app"]
        bdir = build_root / f"app_{target}"
        defs = variant_defs_path(cfg, target.upper(), version)
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


def sign_image(cfg: dict, raw_bin: Path, out_bin: Path, version: str, *, pad: bool, confirm: bool) -> None:
    imgtool = imgtool_path(cfg)
    key = mcuboot_sign_key(cfg)
    cmd = [
        sys.executable,
        str(imgtool),
        "sign",
        "--key",
        str(key),
        "--align",
        "16",
        "--version",
        version,
        "--slot-size",
        "0x100000",
        "--header-size",
        "0x400",
        "--pad-header",
    ]
    if pad:
        cmd.append("--pad")
    if confirm:
        cmd.append("--confirm")
    cmd.extend([str(raw_bin), str(out_bin)])
    run(cmd, cfg, cwd=ROOT, check=True)


def _sb3_yaml(cfg: dict, unit: dict, signed_bin: Path, out_sb: Path) -> str:
    key_hex = read_cust_mk_sk_hex(cfg, unit)
    sec = secrets_dir(cfg, unit)
    signer = sec / unit["img_signer_relpath"]
    cert = sec / unit["cert_block_relpath"]
    # Paths as forward slashes for SPSDK on Windows
    return (
        f"family: mcxn947\n"
        f"firmwareVersion: 1\n"
        f"containerOutputFile: {out_sb.as_posix()}\n"
        f"signer: type=file;file_path={signer.as_posix()}\n"
        f"certBlock: {cert.as_posix()}\n"
        f"containerKeyBlobEncryptionKey: {key_hex}\n"
        f"isNxpContainer: false\n"
        f"description: MCXN SB3\n"
        f"commands:\n"
        f"  - erase:\n"
        f"      address: 0x00100000\n"
        f"      size: 0x00100000\n"
        f"  - load:\n"
        f"      address: 0x00100000\n"
        f"      file: {signed_bin.as_posix()}\n"
    )


def package_unit(
    cfg: dict,
    unit_name: str,
    version: str,
    *,
    out_dir: Path | None = None,
    build_first: bool = False,
) -> Path:
    """Build (optional), sign padded candidate, SB3 via nxpimage, write sidecar. Returns manifest path."""
    unit = load_unit(unit_name)
    verify_cust_mk_sk_fingerprint(cfg, unit)
    variant = variant_for_version(version)
    target = variant.lower()  # v1 / v2

    if build_first:
        rc = cmd_build(cfg, target, version=version)
        if rc != 0:
            raise RuntimeError(f"build {target} failed: {rc}")

    build_dir = Path(cfg["build_root"]) / f"app_{target}"
    raw = find_app_bin(build_dir)
    signed = build_dir / f"app_{target}_SIGNED_PAD.bin"
    sign_image(cfg, raw, signed, version, pad=True, confirm=False)

    dist = out_dir or (ROOT / "dist" / unit_name / version)
    dist.mkdir(parents=True, exist_ok=True)
    sb3_name = f"{unit_name}_{version}_{variant}.sb3"
    sb3_path = dist / sb3_name

    # Work under secrets ota_images (keys stay there); copy only SB3+manifest to dist
    sec = secrets_dir(cfg, unit)
    work = sec / "sec-workspace"
    src_images = work / "source_images"
    ota_images = work / "ota_images"
    configs = work / "configs"
    src_images.mkdir(parents=True, exist_ok=True)
    ota_images.mkdir(parents=True, exist_ok=True)
    configs.mkdir(parents=True, exist_ok=True)

    signed_in_ws = src_images / f"signed__product_{target}_pad.bin"
    shutil.copy2(signed, signed_in_ws)
    ws_sb = ota_images / f"ota_sb_product_{target}_pad.sb"
    yaml_path = configs / f"mcxn_sb3_product_{target}_pad_gen.yaml"
    yaml_path.write_text(_sb3_yaml(cfg, unit, signed_in_ws, ws_sb), encoding="ascii")

    # Ensure key material is never under dist/
    for p in dist.rglob("*"):
        if p.suffix.lower() in {".pem", ".hex", ".key"} or "cust_mk" in p.name.lower():
            raise RuntimeError(f"refusing to proceed; secret-like file in dist: {p}")

    rc, out = run_capture(["nxpimage", "sb31", "export", "-c", str(yaml_path)], cfg)
    print(out)
    if rc != 0 or not ws_sb.exists():
        raise RuntimeError(f"nxpimage sb31 export failed rc={rc}")

    shutil.copy2(ws_sb, sb3_path)
    if not sb3_path.read_bytes()[:4] == b"sbv3":
        raise RuntimeError("SB3 magic missing after export")

    # Scrub check: dist must not contain key files
    for p in dist.iterdir():
        if p.suffix.lower() in {".pem", ".hex", ".key", ".yaml"} and "manifest" not in p.name:
            p.unlink()
            print("WARN: removed non-technician file from dist:", p.name)

    manifest = {
        "unit_name": unit_name,
        "target_uuid": unit["mcu_uuid"].upper(),
        "firmware_version": version,
        "variant": variant,
        "sb3_file": sb3_name,
        "sb3_bytes": sb3_path.stat().st_size,
        "sb3_sha256": sha256_file(sb3_path),
        "signed_image_sha256": sha256_file(signed),
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_commit": git_commit(),
        "tool_versions": tool_versions(cfg),
        "sdk": unit.get("sdk", "26.06.00-LTS"),
        "protocol": "OTAS/TCP:5555",
        "cust_mk_sk_fingerprint": unit["cust_mk_sk_fingerprint"],
        "sec_workspace": str(work),
    }
    man_path = dist / f"{sb3_name}.manifest.json"
    write_json(man_path, manifest)

    # Evidence copy (hashes only in repo docs later)
    print("PACKAGE OK")
    print("  sb3:", sb3_path)
    print("  manifest:", man_path)
    print("  sb3_sha256:", manifest["sb3_sha256"])
    return man_path


def cmd_package(cfg: dict, unit_name: str, version: str, build_first: bool = False) -> int:
    try:
        package_unit(cfg, unit_name, version, build_first=build_first)
        return 0
    except Exception as e:
        print("PACKAGE FAIL:", e, file=sys.stderr)
        return 1


def cmd_release(cfg: dict, unit_name: str, version: str) -> int:
    """build + package into dist/<unit>/<version>/ with technician README."""
    try:
        unit = load_unit(unit_name)
        variant = variant_for_version(version)
        rc = cmd_build(cfg, variant.lower(), version=version)
        if rc != 0:
            return rc
        man_path = package_unit(cfg, unit_name, version, build_first=False)
        dist = man_path.parent
        readme = dist / "README_TECHNICIAN.txt"
        man = load_manifest(man_path)
        readme.write_text(
            "\n".join(
                [
                    f"Technician package: {unit_name} firmware {version} ({variant})",
                    f"Target UUID: {man['target_uuid']}",
                    f"SB3: {man['sb3_file']}",
                    f"SHA-256: {man['sb3_sha256']}",
                    f"Created (UTC): {man['created_utc']}",
                    f"Git commit: {man['git_commit']}",
                    "",
                    "Update (board on network, within 180s of app boot):",
                    f"  python tools/mcxn.py update --sb3 {man['sb3_file']}",
                    "  (run from this directory, or pass full path; sidecar .manifest.json must sit beside SB3)",
                    "",
                    "Do not redistribute unit secrets. This folder has no CUST_MK_SK.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        # Write evidence note under docs/evidence
        ev = ROOT / "docs" / "evidence" / "P6_RELEASE_LAST.json"
        write_json(
            ev,
            {
                "unit": unit_name,
                "version": version,
                "dist": str(dist),
                "sb3_sha256": man["sb3_sha256"],
                "manifest": str(man_path),
                "uuid": man["target_uuid"],
            },
        )
        print("RELEASE OK:", dist)
        return 0
    except Exception as e:
        print("RELEASE FAIL:", e, file=sys.stderr)
        return 1


def _resolve_sb3_and_manifest(sb3_path: Path, manifest_path: Path | None) -> tuple[Path, dict | None]:
    sb3_path = sb3_path.resolve()
    if manifest_path:
        return sb3_path, load_manifest(manifest_path)
    side = Path(str(sb3_path) + ".manifest.json")
    if not side.exists():
        side = sb3_path.with_suffix(sb3_path.suffix + ".manifest.json")
    if side.exists():
        return sb3_path, load_manifest(side)
    # also try sibling name.sb3.manifest.json pattern already covered
    alt = sb3_path.parent / (sb3_path.name + ".manifest.json")
    if alt.exists():
        return sb3_path, load_manifest(alt)
    return sb3_path, None


def send_otas(cfg: dict, sb3: bytes, uuid_b: bytes, host: str | None = None, port: int | None = None, timeout: float = 120.0) -> str:
    ip = host or cfg["board_ip"]
    p = int(port if port is not None else cfg["update_port"])
    hdr = bytearray(28)
    hdr[0:4] = b"OTAS"
    hdr[4] = 1
    hdr[8:24] = uuid_b
    hdr[24:28] = len(sb3).to_bytes(4, "little")
    try:
        with socket.create_connection((ip, p), timeout=10) as s:
            s.settimeout(timeout)
            s.sendall(bytes(hdr) + sb3)
            try:
                resp = s.recv(128)
            except (TimeoutError, socket.timeout):
                raise TimeoutError("recv timeout waiting for device OK")
            except OSError:
                resp = b""
    except (TimeoutError, socket.timeout) as e:
        raise TimeoutError(str(e) or "update socket timeout") from e
    return resp.decode("utf-8", "replace").strip() if resp else ""


def wait_for_status(
    cfg: dict,
    *,
    expect_version: str | None,
    expect_variant: str | None,
    timeout_s: float = 60.0,
    poll_s: float = 2.0,
) -> tuple[bool, str]:
    deadline = time.time() + timeout_s
    last = ""
    while time.time() < deadline:
        try:
            st = fetch_status(cfg, timeout=3)
            last = st.raw
            ok_v = expect_version is None or st.version == expect_version
            ok_var = expect_variant is None or (st.variant or "").upper() == expect_variant.upper()
            if ok_v and ok_var:
                return True, last
        except OSError as e:
            last = str(e)
        time.sleep(poll_s)
    return False, last


def cmd_update(
    cfg: dict,
    sb3_path: Path,
    *,
    uuid_hex: str | None = None,
    manifest_path: Path | None = None,
    allow_no_manifest: bool = False,
    bypass_uuid_check: bool = False,
    expect_version: str | None = None,
    expect_variant: str | None = None,
    transfer_timeout: float = 120.0,
    reboot_timeout: float = 60.0,
) -> int:
    print("=== mcxn update ===")
    try:
        sb3_path, man = _resolve_sb3_and_manifest(sb3_path, manifest_path)
    except Exception as e:
        print("UPDATE FAIL: manifest/sidecar error:", e)
        return 1

    if man is None and not allow_no_manifest:
        print("UPDATE FAIL: missing sidecar manifest (expected", f"{sb3_path.name}.manifest.json)")
        return 1

    if not sb3_path.exists():
        print("UPDATE FAIL: SB3 not found:", sb3_path)
        return 1

    blob = sb3_path.read_bytes()
    if len(blob) < 64 or blob[:4] != b"sbv3":
        print("UPDATE FAIL: not an SB3 file")
        return 1

    if man:
        if man.get("sb3_bytes") and int(man["sb3_bytes"]) != len(blob):
            print("UPDATE FAIL: package length mismatch vs manifest")
            return 1
        digest = sha256_file(sb3_path)
        if man.get("sb3_sha256") and digest.lower() != man["sb3_sha256"].lower():
            print("UPDATE FAIL: package hash mismatch")
            print("  file:", digest)
            print("  manifest:", man["sb3_sha256"])
            return 1
        expect_version = expect_version or man.get("firmware_version")
        expect_variant = expect_variant or man.get("variant")

    # Preflight STATUS
    try:
        st = fetch_status(cfg, timeout=5)
    except OSError as e:
        print("UPDATE FAIL: unreachable device (STATUS):", e)
        return 1
    print("Preflight STATUS:", st.raw)

    target_uuid = (uuid_hex or (man or {}).get("target_uuid") or st.uuid or "").upper()
    if not target_uuid:
        print("UPDATE FAIL: no target UUID")
        return 1
    if st.uuid and st.uuid.upper() != target_uuid.upper() and not bypass_uuid_check:
        print("UPDATE FAIL: wrong-unit UUID mismatch")
        print("  device:", st.uuid)
        print("  package:", target_uuid)
        return 1
    if man and man.get("target_uuid") and st.uuid and st.uuid.upper() != man["target_uuid"].upper() and not bypass_uuid_check:
        print("UPDATE FAIL: device UUID != package target_uuid")
        return 1

    if st.update_window_s is not None and st.update_window_s <= 0:
        print("UPDATE FAIL: update window closed (update_window_s=0)")
        return 1

    uuid_b = parse_uuid_hex(target_uuid if bypass_uuid_check and uuid_hex else (st.uuid or target_uuid))
    # When not bypassing, always use live device UUID for wire header (matches device check)
    if not bypass_uuid_check and st.uuid:
        uuid_b = parse_uuid_hex(st.uuid)

    print(f"Connecting {cfg['board_ip']}:{cfg['update_port']} SB3={sb3_path.name} ({len(blob)} bytes)")
    try:
        reply = send_otas(cfg, blob, uuid_b, timeout=transfer_timeout)
    except OSError as e:
        print("UPDATE FAIL: transfer/connect error:", e)
        return 1
    except TimeoutError as e:
        print("UPDATE FAIL: update timeout:", e)
        return 1

    print("Update reply:", reply or "(no reply — awaiting reboot)")
    if reply and not reply.startswith("OK"):
        print("UPDATE FAIL: device rejected package:", reply)
        return 1

    print("Waiting for reboot / new STATUS...")
    ok, last = wait_for_status(
        cfg,
        expect_version=expect_version,
        expect_variant=expect_variant,
        timeout_s=reboot_timeout,
    )
    if not ok:
        print("UPDATE FAIL: post-update version mismatch or timeout")
        print("  last:", last)
        print("  expected version/variant:", expect_version, expect_variant)
        return 1
    print("Post-update STATUS:", last)

    try:
        hello = fetch_hello(cfg, timeout=5)
    except OSError as e:
        print("UPDATE FAIL: Hello after update:", e)
        return 1
    print("Hello:", hello)
    if "Hello PC!" not in hello:
        print("UPDATE FAIL: Hello mismatch")
        return 1

    print("UPDATE PASS")
    return 0
