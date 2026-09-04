"""Prepare proposed CMPA with only FLASH_REMAP_SIZE=15 and diff vs live."""
from __future__ import annotations

import hashlib
import re
import struct
import subprocess
from pathlib import Path

bak = Path(r"C:\mcxn-secrets\DEV-UNIT-01\backup\pre_512k_remap_20260904")
cmpa = (bak / "cmpa_pfr_read.bin").read_bytes()
cfpa = (bak / "cfpa_pfr_read.bin").read_bytes()
assert len(cmpa) == 512 and len(cfpa) == 512

print("cmpa sha", hashlib.sha256(cmpa).hexdigest())
print("cfpa sha", hashlib.sha256(cfpa).hexdigest())
print("cmpa==blhost", cmpa == (bak / "cmpa_live.bin").read_bytes())
print(
    "cfpa==p7",
    cfpa == Path(r"C:\mcxn-secrets\DEV-UNIT-01\backup\p7_pre\cfpa_live.bin").read_bytes(),
)
print(
    "cmpa==p7",
    cmpa == Path(r"C:\mcxn-secrets\DEV-UNIT-01\backup\p7_pre\cmpa_live.bin").read_bytes(),
)

text = (bak / "cmpa_live.yaml").read_text(encoding="utf-8")
new, n = re.subn(r"(FLASH_REMAP_SIZE:\s*)'0x0'", r"\1'0xF'", text, count=1)
if n != 1:
    raise SystemExit(f"expected 1 FLASH_REMAP_SIZE substitution, got {n}")
prop_yaml = bak / "cmpa_proposed_remap15.yaml"
prop_yaml.write_text(new, encoding="utf-8")
print("yaml remap substitutions", n)

prop_bin = bak / "cmpa_proposed_remap15.bin"
r = subprocess.run(
    ["pfr", "export", "-c", str(prop_yaml), "-o", str(prop_bin)],
    capture_output=True,
    text=True,
)
print("export rc", r.returncode)
if r.returncode != 0:
    print(r.stdout)
    print(r.stderr)
    raise SystemExit(1)

pb = prop_bin.read_bytes()
print("prop len", len(pb), "sha", hashlib.sha256(pb).hexdigest())
w0, w1 = struct.unpack_from("<II", cmpa, 0)
p0, p1 = struct.unpack_from("<II", pb, 0)
print(f"live  BOOT={w0:#010x} FLASH={w1:#010x} REMAP={w1 & 0x1F}")
print(f"prop  BOOT={p0:#010x} FLASH={p1:#010x} REMAP={p1 & 0x1F}")

diffs = [(i, a, b) for i, (a, b) in enumerate(zip(cmpa, pb)) if a != b]
if len(cmpa) != len(pb):
    print("LEN MISMATCH", len(cmpa), len(pb))
print("byte diffs count", len(diffs))
print("diff offsets", [d[0] for d in diffs])
for i, a, b in diffs[:30]:
    print(f"  @{i:#04x}: {a:#04x} -> {b:#04x}")

# Semantic gate: only FLASH_CFG low 5 bits may change in intentional payload.
# ROM CRC/CMAC trailer (often end of page) may also differ on export.
intentional_ok = (w0 == p0) and ((w1 & ~0x1F) == (p1 & ~0x1F)) and ((p1 & 0x1F) == 15)
print("intentional_flash_cfg_only", intentional_ok)

# Parse ROTKH / SEC_BOOT snippets from yaml for evidence
for key in ("ROTKH", "SEC_BOOT_EN", "BOOT_SRC", "CUST_MK_SK", "FLASH_REMAP_SIZE"):
    for line in new.splitlines():
        if key in line and not line.strip().startswith("#"):
            print("yaml:", line.strip())
            break
