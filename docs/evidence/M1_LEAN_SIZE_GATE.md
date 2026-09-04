# M1 LEAN_PROD_TEST — size gate (intermediate)

**Date:** 2026-09-04  
**Branch:** `feat/512k-ab-encrypted-runhours`  
**Build:** `python tools/mcxn.py build v3 --version 3.0.0 --lean` → `C:\mcxn\builds\app_v3_lean`

## Size comparison

| Metric | BASELINE (debug) | LEAN_PROD_TEST (-Os + USER_CONFIG) |
|--------|-----------------:|-----------------------------------:|
| `arm-none-eabi-size` text | 785 632 | **308 512** |
| raw `.bin` | 785 976 | **308 856** |
| `m_text` used / limit | ~785 KB / 798 KB (96%) | **307 KB / 798 KB (38%)** |
| Signed for **1 MiB** slot (current CMPA) | 1 048 576 | 1 048 576 (pad) |
| Signed for **512 KiB** slot (`--slot-size 0x80000`) | N/A (too big) | **524 288** (full pad) |

### Gates (plan §4.2 / M1.11)

| Gate | Result |
|------|--------|
| Preferred loadable ≤400 KiB | **PASS** (301.6 KiB) |
| Preferred signed ≤448 KiB | **PASS** for content; padded image is slot-sized |
| Absolute signed &lt;512 KiB including header/trailer | **PASS** when built for 512 KiB slot |

Delta vs baseline: **≈477 KiB saved** (~61%).

## How size was cut (allow-list, not security weaken)

1. `-Os` + release config + `--gc-sections`
2. `MBEDTLS_USER_CONFIG_FILE=mbedtls_product_user_config.h` overlay on NXP `mcux_mbedtls_config.h`:
   - ECDHE-ECDSA only (no RSA/PSK/DHE key exchanges)
   - No RSA_C / DHM / DES / MD5 / SHA-1 / client / DTLS / tickets / ALPN / SNI
   - P-256 only
   - **Kept:** TLS 1.2+1.3 path as in NXP base, AES-GCM, SHA-256/512, X.509 verify, ELS/PSA, IPv6 untouched

## On-board smoke (lean flashed both 1 MiB slots)

| Test | Result |
|------|--------|
| Hello | PASS |
| STATUS 3.0.0 V3 | PASS |
| ECHO | PASS |
| 5× reconnect | PASS |
| no-cert / wrong-CA / wrong-FP | FAIL_AS_DESIGNED |
| `mtls_m2_neg.py` | **M2_NEG_PASS** |

## Still required before M2/M5

- Full M1.12/M1.13 matrix (1000 reconnect, fault matrix, OTA, soak/throughput vs baseline)
- DER credential conversion (M1.8)
- PSA fine-grained config (optional further ELS trim)
- **No CMPA/remap yet** — size gate for 512 KiB slot is met on flash content

IPv4+IPv6 compile flags unchanged (`LWIP_IPV6=1`).
