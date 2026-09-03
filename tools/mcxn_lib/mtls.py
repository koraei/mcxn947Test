"""Python ssl mTLS helper for tools/mcxn.py. Secrets stay under secrets_root."""
from __future__ import annotations

import hashlib
import ssl
import socket
from pathlib import Path


class FingerprintError(OSError):
    pass


def _mtls_cfg(cfg: dict) -> dict:
    return cfg.get("mtls") or {}


def load_client_ctx(cfg: dict, *, check_hostname: bool = False) -> ssl.SSLContext:
    mt = _mtls_cfg(cfg)
    ca = Path(mt["ca_cert"])
    cert = Path(mt["client_cert"])
    key = Path(mt["client_key"])
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = check_hostname
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_verify_locations(cafile=str(ca))
    ctx.load_cert_chain(str(cert), str(key))
    return ctx


def der_sha256(der: bytes) -> str:
    return hashlib.sha256(der).hexdigest()


def expected_server_fingerprint(cfg: dict, unit: dict | None = None) -> str:
    if unit and unit.get("mtls_server_cert_sha256"):
        return str(unit["mtls_server_cert_sha256"]).lower()
    mt = _mtls_cfg(cfg)
    server_crt = mt.get("server_cert")
    if server_crt:
        pem = Path(server_crt).read_bytes()
        import ssl as _ssl

        der = _ssl.PEM_cert_to_DER_cert(pem.decode("ascii"))
        return der_sha256(der)
    raise FingerprintError("no mtls_server_cert_sha256 in unit registry")


def wrap_client(sock: socket.socket, cfg: dict, unit: dict | None = None) -> ssl.SSLSocket:
    ctx = load_client_ctx(cfg)
    ssock = ctx.wrap_socket(sock, server_hostname=None)
    der = ssock.getpeercert(binary_form=True)
    got = der_sha256(der)
    exp = expected_server_fingerprint(cfg, unit)
    if got != exp.lower():
        ssock.close()
        raise FingerprintError(f"server cert fingerprint mismatch got={got} expected={exp}")
    return ssock


def connect_mtls(cfg: dict, port: int, timeout: float = 5.0, unit: dict | None = None) -> ssl.SSLSocket:
    ip = cfg["board_ip"]
    raw = socket.create_connection((ip, int(port)), timeout=timeout)
    raw.settimeout(timeout)
    try:
        return wrap_client(raw, cfg, unit)
    except Exception:
        raw.close()
        raise
