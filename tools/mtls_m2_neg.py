"""On-target M2 mTLS positive/negative checks."""
from __future__ import annotations

import datetime
import ssl
import socket
import sys
import tempfile
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from mcxn_lib import load_cfg, load_unit  # noqa: E402
from mcxn_lib.mtls import connect_mtls, FingerprintError  # noqa: E402


def main() -> int:
    cfg = load_cfg()
    unit = load_unit(cfg["unit_name"])
    host = cfg["board_ip"]
    port = int(cfg["hello_port"])
    mt = cfg["mtls"]

    print("--- valid reconnect x5 ---")
    for i in range(5):
        s = connect_mtls(cfg, port, unit=unit)
        s.sendall(b"Hello MCXN\n")
        r = s.recv(256)
        print(i, r.decode().strip())
        s.close()

    print("--- no client cert ---")
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_verify_locations(cafile=mt["ca_cert"])
    try:
        raw = socket.create_connection((host, port), timeout=5)
        raw.settimeout(5)
        with ctx.wrap_socket(raw, server_hostname=None) as ss:
            print("UNEXPECTED", ss.recv(64))
            return 1
    except Exception as e:
        print("FAIL_AS_DESIGNED", type(e).__name__, e)

    print("--- wrong CA ---")
    k = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "wrong-ca")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(k.public_key())
        .serial_number(1)
        .not_valid_before(datetime.datetime.utcnow() - datetime.timedelta(days=1))
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=1))
        .sign(k, hashes.SHA256())
    )
    td = Path(tempfile.mkdtemp())
    wrong = td / "wrong.crt"
    wrong.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    ctx2 = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx2.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx2.check_hostname = False
    ctx2.verify_mode = ssl.CERT_REQUIRED
    ctx2.load_verify_locations(cafile=str(wrong))
    ctx2.load_cert_chain(mt["client_cert"], mt["client_key"])
    try:
        raw = socket.create_connection((host, port), timeout=5)
        raw.settimeout(5)
        with ctx2.wrap_socket(raw, server_hostname=None) as ss:
            print("UNEXPECTED", ss.recv(64))
            return 1
    except Exception as e:
        print("FAIL_AS_DESIGNED", type(e).__name__, e)

    print("--- wrong fingerprint ---")
    bad_unit = dict(unit)
    bad_unit["mtls_server_cert_sha256"] = "00" * 32
    try:
        s = connect_mtls(cfg, port, unit=bad_unit)
        print("UNEXPECTED ok")
        s.close()
        return 1
    except FingerprintError as e:
        print("FAIL_AS_DESIGNED", type(e).__name__, e)
    except Exception as e:
        print("FAIL_AS_DESIGNED", type(e).__name__, e)

    print("--- post-negative hello still works ---")
    s = connect_mtls(cfg, port, unit=unit)
    s.sendall(b"Hello MCXN\n")
    print(s.recv(256).decode().strip())
    s.close()
    print("M2_NEG_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
