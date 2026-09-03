#!/usr/bin/env python3
"""Generate development mTLS PKI under C:\\mcxn-secrets\\mtls (never under Git)."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_key(path: Path, key: ec.EllipticCurvePrivateKey) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


def write_cert(path: Path, cert: x509.Certificate) -> None:
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def load_or_make_key(path: Path) -> ec.EllipticCurvePrivateKey:
    if path.exists():
        return serialization.load_pem_private_key(path.read_bytes(), password=None)  # type: ignore[return-value]
    key = ec.generate_private_key(ec.SECP256R1())
    write_key(path, key)
    return key


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=r"C:\mcxn-secrets\mtls", type=Path)
    p.add_argument("--unit", default="DEV-UNIT-01")
    p.add_argument("--pc", default="DEV-PC-01")
    p.add_argument("--uuid", default="9DA8D48D0DDCD755903E8FBD3836C153")
    p.add_argument("--days", type=int, default=3650)
    args = p.parse_args()

    root: Path = args.root
    ca_dir = root / "ca"
    unit_dir = root / "units" / args.unit
    pc_dir = root / "pcs" / args.pc
    now = datetime.now(timezone.utc)
    until = now + timedelta(days=args.days)

    ca_key = load_or_make_key(ca_dir / "ca.key")
    ca_name = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MCXN Lab"),
            x509.NameAttribute(NameOID.COMMON_NAME, "MCXN Development Root CA"),
        ]
    )
    ca_crt_path = ca_dir / "ca.crt"
    if ca_crt_path.exists():
        ca_cert = x509.load_pem_x509_certificate(ca_crt_path.read_bytes())
    else:
        ca_cert = (
            x509.CertificateBuilder()
            .subject_name(ca_name)
            .issuer_name(ca_name)
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(until)
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256())
        )
        write_cert(ca_crt_path, ca_cert)

    srv_key = load_or_make_key(unit_dir / "server.key")
    srv_name = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MCXN Lab"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "MCU"),
            x509.NameAttribute(NameOID.COMMON_NAME, args.unit),
        ]
    )
    srv_cert = (
        x509.CertificateBuilder()
        .subject_name(srv_name)
        .issuer_name(ca_cert.subject)
        .public_key(srv_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(until)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=True,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName(args.unit),
                    x509.UniformResourceIdentifier(f"urn:uuid:{args.uuid}"),
                ]
            ),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    write_cert(unit_dir / "server.crt", srv_cert)
    server_fp = hashlib.sha256(srv_cert.public_bytes(serialization.Encoding.DER)).hexdigest()

    cli_key = load_or_make_key(pc_dir / "client.key")
    cli_name = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MCXN Lab"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "PC"),
            x509.NameAttribute(NameOID.COMMON_NAME, args.pc),
        ]
    )
    cli_cert = (
        x509.CertificateBuilder()
        .subject_name(cli_name)
        .issuer_name(ca_cert.subject)
        .public_key(cli_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(until)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=True,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    write_cert(pc_dir / "client.crt", cli_cert)

    meta = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "ca_sha256": sha256_file(ca_crt_path),
        "unit": args.unit,
        "unit_uuid": args.uuid,
        "server_cert_sha256": server_fp,
        "pc": args.pc,
        "client_cert_sha256": sha256_file(pc_dir / "client.crt"),
        "paths": {
            "ca_cert": str(ca_crt_path),
            "server_cert": str(unit_dir / "server.crt"),
            "server_key": str(unit_dir / "server.key"),
            "client_cert": str(pc_dir / "client.crt"),
            "client_key": str(pc_dir / "client.key"),
        },
    }
    meta_path = root / "mtls_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print("Wrote", meta_path)
    print("server_cert_sha256=", meta["server_cert_sha256"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
