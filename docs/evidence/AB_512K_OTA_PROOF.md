# 512 KiB A/B OTA proof (IFR MCUboot LIM=15, CMPA unchanged)

**Date:** 2026-09-04  
**Board:** DEV-UNIT-01  
**CMPA/CFPA:** unchanged  
**MCUboot:** IFR rebuild, banner `MCUboot 512K remap LIM=15`

## Packages

| Version | Variant | Slot size | SB3 erase/load | Layout check |
|---------|---------|-----------|----------------|--------------|
| 1.0.0 | V1 | `0x80000` | `0x00100000` + `0x00080000` | PASS |
| 2.0.0 | V2 | `0x80000` | same | PASS |
| 3.2.0 | V3 | `0x80000` | same | PASS |

Host: `python tools/mcxn.py package --version … --lean --layout512`

## Sequence

1. Dual-slot LinkServer load of confirmed lean V1 `@0x0` and `@0x00100000` (512 KiB each).
2. Planted 32-byte marker `SHARED_POOL_MARKER_512K_OK!!!!!!` at **`0x00080000`** and **`0x00180000`** (outside remap window).
3. **OTA A→B:** `1.0.0 V1` → `2.0.0 V2` — UPDATE PASS.
4. **OTA opposite slot:** `2.0.0 V2` → `3.2.0 V3` — UPDATE PASS.

## Remap / active slot (UART)

| After | Slot selected | Remap |
|-------|---------------|-------|
| V2 OTA | secondary | **enabled** |
| V3 OTA | primary | **disabled** |

UART excerpts: `docs/evidence/AB_512k_V2_boot_uart.txt`, `AB_512k_V3_boot_uart.txt`

## Shared pools after both OTAs

| Address | Marker | Result |
|---------|--------|--------|
| `0x00080000` | intact | **PASS** |
| `0x00180000` | intact | **PASS** |

SB3 never targeted these addresses (erase confined to inactive 512 KiB candidate).

## Live board after proof

`STATUS version=3.2.0 variant=V3` — Hello OK.

## STOP conditions not met

- No 1 MiB slot reported by MCUboot (`LIM=15`, slot sizes `0x80000`).
- No CMPA/CFPA write required or performed.
- RKTH/RoTKH path unchanged from IFR MBI gate.
