# Run-hours journal key hardening (ELS opaque) — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans / implement directly after owner approval (approved 2026-09-04).

**Goal:** Replace UUID/domain HMAC `K_RH` with volatile ELS opaque AES-256 at PSA location `0xc00401` (`PSA_KEY_LOCATION_S50_RFC3394_STORAGE`), persist only the device-bound RFC3394 blob in platform reserve, value-preserving power-fail-safe v1→v2 migration.

**Architecture:** Journal format/addresses/arbiter/OTA unchanged. Keystore dual-copy in `ML_PLATFORM_RESERVE_A`. States: EMPTY → BLOB_STAGED → COMMITTED (`RH_KEY_VERSION=2`). Never write v2 ciphertext before durable staged blob. Never commit version before v2 record read-back auth. On `BLOB_STAGED` boot: probe with v2 first; if no v2 record, fall back to v1 and continue migration.

**Quantum:** 600 s remains the persisted production quantum.

## Files

- `firmware/app/src/runhours_keystore.c` + `inc/runhours_keystore.h` — dual-copy flash blob + state
- `firmware/app/src/runhours_crypto.c` — v1 HMAC path + v2 PSA opaque AEAD + migrate
- `firmware/app/src/runhours_journal.c` — init migration hook; wipe keeps keystore
- `firmware/app/inc/runhours_format.h`, `hello_service.c`, `flash_range_guard.h`, `CMakeLists.txt`
- Docs + `tools/runhours_key_hardening_regress.py`

## Migration (power-fail)

1. Auth latest v1 → snap quanta/seq  
2. Generate ELS opaque → export RFC3394 → dual-write `BLOB_STAGED` (verify)  
3. Re-import + GCM self-test  
4. Append same quanta as v2 record; read-back auth  
5. Dual-write `COMMITTED` / `RH_KEY_VERSION=2`  
6. Leave v1 records intact  

## Test plan

Focused suite tests 1–9 from owner request; 600 s semantic documented.
