# M1 LEAN_PROD — frozen configuration & size record

**Date:** 2026-09-04  
**Branch:** `feat/512k-ab-encrypted-runhours`  
**Authority:** `doc/FRDM_MCXN947_512K_AB_ENCRYPTED_RUNHOURS_TEST_PLAN_REV_B_FINAL.md`

## Freeze decision

Lean mbedTLS USER_CONFIG is **frozen**. No further crypto feature removal for flash size.

| Item | Value |
|------|------:|
| Linker text (`arm-none-eabi-size`) | **308 512** B (~301.3 KiB) |
| Raw `.bin` | **308 856** B |
| Signed **unpadded** (`--slot-size 0x80000`, no `--pad`) | **310 032** B |
| Signed **padded** 512 KiB slot file | **524 288** B (= slot pad, **not** firmware usage) |
| `m_text` used / **512 KiB** link limit | **307 176** / **514 048** (502 KiB region) ≈ **59.8%** |
| Negotiated suite (on-target) | `ECDHE-ECDSA-AES256-GCM-SHA384` / TLS 1.2 |

### Explicit non-goals (accepted)

- No further mbedTLS allow-list cuts for size.
- DER credential conversion **deferred** (optional; abandon if complex).
- No TLS/lwIP buffer or stack shrink for flash.
- IPv4 + IPv6 remain enabled (`LWIP_IPV6=1`).

## Overlay

`firmware/app/security/mbedtls_product_user_config.h` via `-DMBEDTLS_USER_CONFIG_FILE` on NXP `mcux_mbedtls_config.h`.

## Validation summary (lean on field 1 MiB remap)

| Gate | Result | Evidence |
|------|--------|----------|
| Hello / STATUS / ECHO | PASS | M1_LEAN_SIZE_GATE.md |
| Negatives (no-cert / wrong-CA / wrong-FP) | PASS | M2_NEG + M1 faults |
| 1000 reconnect | PASS | `M1_lean_reconnect.json` |
| Fault matrix (handshake/RST/kill) | PASS | `M1_lean_faults.json` |
| Mid-session TLS interrupt recovery | PASS | `M1_lean_interrupt_tls.json` |
| Lean SB3 OTA 3.0.0→3.1.0 | PASS | prior session / STATUS 3.1.0 |
| Corrupt SB3 reject | PASS | prior session |
| IPv6 compiled (`nd6_*` in map) | PASS | `M1_lean_interrupt_tls.json` |
| IPv6 on-wire ping6 | **INCOMPLETE** (need UART LL addr / operator) | same |
| NIC/cable link cycles | **BLOCKED** (Windows Access denied); manual procedure | `M4_CABLE_CYCLES.md` |
| Throughput ≥95% baseline | **PENDING** short lean+QA sample | see M1_throughput |

## Build-only 512 KiB layout

`python tools/mcxn.py build v3 --lean --layout512` → `C:\mcxn\builds\app_v3_lean_512k`  
Linker: `firmware/app/linker/mcxn10_cm33_flash_512k.ld` (`SLOT_SIZE=0x80000`).  
**CMPA / `FLASH_REMAP_SIZE` not written.**
