"""Guard MCUboot application signing key (never ROM/MBI IMG1_1)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa


class ImgtoolKeyError(RuntimeError):
    pass


def pubkey_der_sha256(pem_path: Path) -> str:
    data = Path(pem_path).read_bytes()
    try:
        key = serialization.load_pem_private_key(data, password=None)
        pub = key.public_key()
    except ValueError:
        pub = serialization.load_pem_public_key(data)
    if not isinstance(pub, (ec.EllipticCurvePublicKey, rsa.RSAPublicKey)):
        raise ImgtoolKeyError(f"unsupported imgtool key type in {pem_path}")
    der = pub.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(der).hexdigest()


def mcuboot_imgtool_key_path(cfg: dict) -> Path:
    rel = cfg["paths"]["imgtool_key"]
    p = Path(rel)
    if p.is_absolute():
        return p
    return Path(cfg["sdk_root"]) / rel


def assert_mcuboot_imgtool_key(cfg: dict) -> str:
    """Refuse build/package/release if imgtool_key is not the frozen MCUboot app key.

    Also rejects the ROM/MBI IMG1_1 key even if the expected fingerprint were
    accidentally set to that key.
    """
    path = mcuboot_imgtool_key_path(cfg)
    if not path.exists():
        raise ImgtoolKeyError(f"imgtool_key missing: {path}")
    got = pubkey_der_sha256(path)
    mc = cfg.get("mcuboot") or {}
    forbidden = str(mc.get("forbidden_img1_1_key_sha256") or "").strip().lower()
    expected = str(mc.get("imgtool_key_sha256") or "").strip().lower()
    if not expected:
        raise ImgtoolKeyError("mcuboot.imgtool_key_sha256 missing from mcxn.toml")
    if forbidden and got == forbidden:
        raise ImgtoolKeyError(
            "IMG1_1 key is the ROM/MBI signer and must not be used for MCUboot "
            f"application images (got={got})"
        )
    if got != expected:
        raise ImgtoolKeyError(
            f"MCUboot imgtool_key fingerprint mismatch got={got} expected={expected} path={path}"
        )
    return got
