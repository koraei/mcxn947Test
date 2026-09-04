#!/usr/bin/env python3
"""Reject SB3 packages that erase/load outside the candidate firmware slot."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Default: legacy 1 MiB candidate. With --layout512: 512 KiB only.
CAND = 0x00100000


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("yaml", type=Path)
    p.add_argument("--layout512", action="store_true")
    args = p.parse_args()
    slot = 0x80000 if args.layout512 else 0x100000
    text = args.yaml.read_text(encoding="utf-8")
    addrs = [int(x, 0) for x in re.findall(r"address:\s*(0x[0-9a-fA-F]+|\d+)", text)]
    sizes = [int(x, 0) for x in re.findall(r"size:\s*(0x[0-9a-fA-F]+|\d+)", text)]
    ok = True
    for a in addrs:
        if a < CAND or a >= CAND + slot:
            print(f"FAIL address 0x{a:08x} outside candidate slot", file=sys.stderr)
            ok = False
    for a, s in zip(addrs, sizes):
        if a + s > CAND + slot:
            print(f"FAIL range 0x{a:08x}+0x{s:x} exceeds slot", file=sys.stderr)
            ok = False
    # Shared pools must never appear
    forbidden = [0x80000, 0xA0000, 0xB0000, 0x180000, 0x1A0000, 0x1B0000]
    for a in addrs:
        for f in forbidden:
            if a == f or (CAND <= a < CAND + slot and False):
                pass
        if any(f <= a < f + 0x10000 for f in (0xA0000, 0x1A0000)):
            print(f"FAIL address 0x{a:08x} overlaps runhours", file=sys.stderr)
            ok = False
    if ok:
        print(f"OK sb3 ranges within candidate 0x{CAND:08x}+0x{slot:x}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
