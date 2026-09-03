"""Host guard: MCUboot application images must not be signed with IMG1_1."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from mcxn_lib.imgtool_key import (  # noqa: E402
    ImgtoolKeyError,
    assert_mcuboot_imgtool_key,
    pubkey_der_sha256,
)


def _write_p256_key(path: Path) -> Path:
    key = ec.generate_private_key(ec.SECP256R1())
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return path


def test_matching_fingerprint_ok(tmp_path: Path):
    key = _write_p256_key(tmp_path / "ok.pem")
    fp = pubkey_der_sha256(key)
    cfg = {
        "sdk_root": str(tmp_path),
        "paths": {"imgtool_key": key.name},
        "mcuboot": {
            "imgtool_key_sha256": fp,
            "forbidden_img1_1_key_sha256": "aa" * 32,
        },
    }
    assert assert_mcuboot_imgtool_key(cfg) == fp


def test_mismatch_refused(tmp_path: Path):
    key = _write_p256_key(tmp_path / "wrong.pem")
    cfg = {
        "sdk_root": str(tmp_path),
        "paths": {"imgtool_key": key.name},
        "mcuboot": {
            "imgtool_key_sha256": "bb" * 32,
            "forbidden_img1_1_key_sha256": "aa" * 32,
        },
    }
    with pytest.raises(ImgtoolKeyError, match="fingerprint mismatch"):
        assert_mcuboot_imgtool_key(cfg)


def test_img1_1_key_explicitly_rejected(tmp_path: Path):
    img1 = _write_p256_key(tmp_path / "IMG1_1_p256.pem")
    fp = pubkey_der_sha256(img1)
    cfg = {
        "sdk_root": str(tmp_path),
        "paths": {"imgtool_key": img1.name},
        "mcuboot": {
            "imgtool_key_sha256": fp,  # even if expected were set to IMG1_1
            "forbidden_img1_1_key_sha256": fp,
        },
    }
    with pytest.raises(ImgtoolKeyError, match="IMG1_1"):
        assert_mcuboot_imgtool_key(cfg)


def test_sign_image_refuses_bad_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from mcxn_lib import workflow

    cfg = {"sdk_root": str(tmp_path), "paths": {"imgtool": "imgtool.py", "imgtool_key": "x.pem"}}
    monkeypatch.setattr(
        workflow,
        "assert_mcuboot_imgtool_key",
        lambda _cfg: (_ for _ in ()).throw(ImgtoolKeyError("IMG1_1")),
    )
    with pytest.raises(ImgtoolKeyError, match="IMG1_1"):
        workflow.sign_image(cfg, tmp_path / "in.bin", tmp_path / "out.bin", "1.0.0", pad=True, confirm=False)
