#!/usr/bin/env python3
"""Emit firmware/src/security/mtls_creds.inc.c from secrets PEMs (gitignored build input)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def c_string_literal(pem: str, name: str) -> str:
    lines = []
    lines.append(f"const char {name}[] =")
    for ln in pem.splitlines(True):
        escaped = ln.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")
        lines.append(f'    "{escaped}"')
    lines.append(";")
    lines.append(f"const unsigned int {name}_len = sizeof({name});")
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=r"C:\mcxn-secrets\mtls", type=Path)
    p.add_argument("--unit", default="DEV-UNIT-01")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    ca = (args.root / "ca" / "ca.crt").read_text(encoding="ascii")
    srv_crt = (args.root / "units" / args.unit / "server.crt").read_text(encoding="ascii")
    srv_key = (args.root / "units" / args.unit / "server.key").read_text(encoding="ascii")

    body = (
        "/* AUTO-GENERATED - do not commit. Private key material. */\n"
        "#include <stddef.h>\n\n"
        + c_string_literal(ca, "mtls_ca_pem")
        + "\n"
        + c_string_literal(srv_crt, "mtls_server_crt_pem")
        + "\n"
        + c_string_literal(srv_key, "mtls_server_key_pem")
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(body, encoding="ascii")
    print("Wrote", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
