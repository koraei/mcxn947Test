"""Host-side tests for P6 package/update preflight (no firmware changes)."""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path
from unittest import mock

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from mcxn_lib.workflow import cmd_update, send_otas  # noqa: E402
from mcxn_lib import sha256_file, write_json  # noqa: E402


def _cfg(tmp: Path) -> dict:
    return {
        "board_ip": "127.0.0.1",
        "hello_port": 9500,
        "update_port": 9555,
        "sdk_root": str(tmp),
        "armgcc_dir": str(tmp),
        "linkserver": str(tmp / "LinkServer.exe"),
        "secrets_root": str(tmp),
    }


def _fake_sb3(path: Path, n: int = 128) -> Path:
    # Minimal bytes with sbv3 magic; not a real container (transfer mocked).
    data = b"sbv3" + b"\x00" * (n - 4)
    path.write_bytes(data)
    return path


def _manifest(sb3: Path, **over) -> Path:
    man = {
        "unit_name": "DEV-UNIT-01",
        "target_uuid": "9DA8D48D0DDCD755903E8FBD3836C153",
        "firmware_version": "2.0.0",
        "variant": "V2",
        "sb3_file": sb3.name,
        "sb3_bytes": sb3.stat().st_size,
        "sb3_sha256": sha256_file(sb3),
    }
    man.update(over)
    p = Path(str(sb3) + ".manifest.json")
    write_json(p, man)
    return p


def test_wrong_uuid_refused(tmp_path: Path):
    sb3 = _fake_sb3(tmp_path / "pkg.sb3")
    _manifest(sb3)
    cfg = _cfg(tmp_path)

    with mock.patch(
        "mcxn_lib.workflow.fetch_status",
        return_value=mock.Mock(
            raw="STATUS version=1.0.0 variant=V1 uuid=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA uptime_s=1 update_window_s=100",
            version="1.0.0",
            variant="V1",
            uuid="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            update_window_s=100,
        ),
    ):
        rc = cmd_update(cfg, sb3)
    assert rc == 1


def test_missing_sidecar(tmp_path: Path):
    sb3 = _fake_sb3(tmp_path / "pkg.sb3")
    cfg = _cfg(tmp_path)
    rc = cmd_update(cfg, sb3)
    assert rc == 1


def test_corrupt_sidecar_json(tmp_path: Path):
    sb3 = _fake_sb3(tmp_path / "pkg.sb3")
    side = Path(str(sb3) + ".manifest.json")
    side.write_text("{not-json", encoding="utf-8")
    cfg = _cfg(tmp_path)
    rc = cmd_update(cfg, sb3)
    assert rc == 1


def test_package_hash_mismatch(tmp_path: Path):
    sb3 = _fake_sb3(tmp_path / "pkg.sb3")
    _manifest(sb3, sb3_sha256="0" * 64)
    cfg = _cfg(tmp_path)
    with mock.patch(
        "mcxn_lib.workflow.fetch_status",
        return_value=mock.Mock(
            raw="ok",
            version="1.0.0",
            variant="V1",
            uuid="9DA8D48D0DDCD755903E8FBD3836C153",
            update_window_s=100,
        ),
    ):
        rc = cmd_update(cfg, sb3)
    assert rc == 1


def test_unreachable_device(tmp_path: Path):
    sb3 = _fake_sb3(tmp_path / "pkg.sb3")
    _manifest(sb3)
    cfg = _cfg(tmp_path)
    with mock.patch("mcxn_lib.workflow.fetch_status", side_effect=OSError("down")):
        rc = cmd_update(cfg, sb3)
    assert rc == 1


def test_update_timeout(tmp_path: Path):
    sb3 = _fake_sb3(tmp_path / "pkg.sb3")
    _manifest(sb3)
    cfg = _cfg(tmp_path)

    with mock.patch(
        "mcxn_lib.workflow.fetch_status",
        return_value=mock.Mock(
            raw="ok",
            version="1.0.0",
            variant="V1",
            uuid="9DA8D48D0DDCD755903E8FBD3836C153",
            update_window_s=100,
        ),
    ), mock.patch("mcxn_lib.workflow.send_otas", side_effect=TimeoutError("timeout")):
        rc = cmd_update(cfg, sb3, transfer_timeout=1.0)
    assert rc == 1


def test_post_update_version_mismatch(tmp_path: Path):
    sb3 = _fake_sb3(tmp_path / "pkg.sb3")
    _manifest(sb3)
    cfg = _cfg(tmp_path)

    st_pre = mock.Mock(
        raw="pre",
        version="1.0.0",
        variant="V1",
        uuid="9DA8D48D0DDCD755903E8FBD3836C153",
        update_window_s=100,
    )
    st_post = mock.Mock(
        raw="STATUS version=1.0.0 variant=V1 uuid=9DA8D48D0DDCD755903E8FBD3836C153",
        version="1.0.0",
        variant="V1",
        uuid="9DA8D48D0DDCD755903E8FBD3836C153",
        update_window_s=100,
    )

    with mock.patch("mcxn_lib.workflow.fetch_status", side_effect=[st_pre, st_post, st_post, st_post]), mock.patch(
        "mcxn_lib.workflow.send_otas", return_value="OK"
    ), mock.patch("mcxn_lib.workflow.wait_for_status", return_value=(False, st_post.raw)):
        rc = cmd_update(cfg, sb3, reboot_timeout=1.0)
    assert rc == 1


def test_send_otas_header_shape():
    """Wire header remains OTAS (P5 frozen), not legacy plan MCXNUP1."""
    captured = {}

    class FakeSock:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def settimeout(self, t):
            pass

        def sendall(self, data):
            captured["data"] = data

        def recv(self, n):
            return b"OK\n"

    with mock.patch("socket.create_connection", return_value=FakeSock()):
        reply = send_otas(
            {"board_ip": "1.2.3.4", "update_port": 5555},
            b"sbv3" + b"\x00" * 60,
            bytes.fromhex("9DA8D48D0DDCD755903E8FBD3836C153"),
        )
    assert reply.startswith("OK")
    assert captured["data"][:4] == b"OTAS"
    assert captured["data"][4] == 1
