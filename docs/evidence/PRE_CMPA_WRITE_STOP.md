# Pre-CMPA freeze + STOP before write

**Date:** 2026-09-04  
**Branch:** `feat/512k-ab-encrypted-runhours`  
**Tag:** `pre-cmpa-512k-remap` → commit **`0bafb204a535c73efaa3365f4fdf8f5a5ec7dd48`**  
**Working tree:** clean at tag  
**Board smoke after clean lean rebuild:** Hello/STATUS PASS (3.1.0 V3)

## Backups (ISP, before any write)

Directory: `C:\mcxn-secrets\DEV-UNIT-01\backup\pre_512k_remap_20260904\`

| Artifact | SHA-256 | Notes |
|----------|---------|-------|
| `cmpa_pfr_read.bin` / `cmpa_live.bin` | `b66746de53ae92e50ecc47c2293d96d321f80864e40fccf21a32d122592e9ef6` | **Identical to P7 live** |
| `cfpa_pfr_read.bin` | `baac145c328c55b26a4203972d056e185ef3a2fc6fad19510ee0f8ed91beb910` | **Identical to P7 live** |
| `cmpa_live.yaml` / `cfpa_live.yaml` | — | SPSDK `pfr read` parse |
| IFR MCUboot 32 KiB | **not readable** | Alignment Error (same as P7) |

Live CMPA: `BOOT_CFG=0x59630002`, `FLASH_CFG=0x00000000`, **`FLASH_REMAP_SIZE=0`** (same as NXP SDK `cmpa.bin`).

Unchanged fields observed in YAML: `BOOT_SRC=SECONDARY_BOOTLOADER`, `SEC_BOOT_EN=ECDSA_SIGNED`, `ROTKH=670EE45A…5457F`, `CUST_MK_SK_KEY_BLOB` present.

## Proposed CMPA compare — STOP triggers

### A) `pfr export` of YAML with `FLASH_REMAP_SIZE: '0xF'`

Byte diffs vs live (**5 bytes**):

| Offset | Live | Proposed | Meaning |
|--------|------|----------|---------|
| `0x04` | `0x00` | `0x0F` | **FLASH_REMAP_SIZE=15** (intended) |
| `0x42` | `0x00` | `0xFF` | **unexpected** |
| `0x43` | `0x00` | `0xFF` | **unexpected** |
| `0x46` | `0x00` | `0xFF` | **unexpected** |
| `0x47` | `0x00` | `0xFF` | **unexpected** |

Per owner rule (“STOP if any unexpected CMPA difference”), **`pfr export` binary must not be programmed**.

### B) Surgical patch (live ⊕ only low 5 bits of word @4)

File: `cmpa_surgical_remap15.bin` — **exactly one byte** changes (`0x04: 0x00→0x0F`).  
This is the only binary that matches the “FLASH_REMAP_SIZE only” intent.

## Hard blocker: CMPA alone does not set 512 KiB remap

IFR MCUboot (`mcuboot_opensource/main.c`) hardcodes:

```c
/* Remapping size set to full range of 1MB */
NPX0->REMAP = (31 << NPX_REMAP_LIM_SHIFT) | 0x5A5A;
NPX0->REMAP = (31 << NPX_REMAP_LIMDP_SHIFT) | 0xA5A5;
```

`LIM=31` → `(31+1)×32 KiB = 1024 KiB`. Runtime A/B swap window is **software**, not the current CMPA field (which is already `0` on the working 1 MiB board).

Therefore programming CMPA `FLASH_REMAP_SIZE=15` **without** rebuilding/reflashing IFR MCUboot with `LIM=15` will **not** produce 512 KiB Slot A/B mapping. Post-write checks 6/8/9 would fail or remain 1 MiB.

## Decision required (no write performed)

1. **Approve surgical CMPA write** (`cmpa_surgical_remap15.bin` only) **and**  
2. **Approve IFR MCUboot rebuild/reflash** changing `SBL_EnableRemap` `31→15` only (new signed MBI; RoTKH must still match), **or**  
3. Hold.

Until (1)+(2) are both approved, **CMPA write is withheld**.
