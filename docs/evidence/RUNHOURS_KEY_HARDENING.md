# Run-hours journal key hardening (ELS opaque AES-256)

**Date:** 2026-09-04  
**Branch:** `feat/512k-ab-encrypted-runhours`  
**Unit:** DEV-UNIT-01  
**Protected security state:** **unchanged** (no CMPA / CFPA / IFR / lifecycle / `CUST_MK_SK` writes)

**FREEZE:** Owner froze this v2 ELS key architecture on 2026-09-04. No further journal-crypto / keystore changes during the endurance test unless the freeze is explicitly lifted.

## Mechanism

| Item | Detail |
|------|--------|
| NXP API | MCUXpresso 26.06 PSA Crypto + `PSA_CRYPTO_DRIVER_ELS_PKC` |
| Location | `0xc00401` = `PSA_KEY_LOCATION_S50_RFC3394_STORAGE` (same as FRDM `psa_crypto_opaque_key_examples`) |
| Algorithm | AES-256-GCM via `psa_aead_encrypt` / `psa_aead_decrypt` |
| Runtime key | **Volatile** ELS opaque handle (plaintext AES key not held in app RAM after load) |
| Persistence | Device-bound **RFC3394** wrapped blob in `ML_PLATFORM_RESERVE_A` (dual 8 KiB slots @ `0x00080000` / `+0x2000`) |
| Blob capture | After `psa_generate_key`, NXP `StoreKey` places the RFC3394 container in the PSA key buffer; `psa_export_key` returns `NOT_SUPPORTED` for ELS COPRO keys, so the buffer is captured via `psa_get_and_lock_key_slot` (still wrapped bytes, not raw AES) |
| Key ID / version | `RH_KEY_VERSION=2`, monotonic `key_id`; `RHDIAG` exposes `key_ver`, `key_id`, `ks` |
| Separated from | `CUST_MK_SK`, imgtool, ROM/MBI/`IMG1_1`, SB3 signer, mTLS |

FRDM opaque example reference: AES-256 + GCM **PASSED** at location `c00401` (volatile path). PSA ITS (`MBEDTLS_PSA_CRYPTO_STORAGE_C`) was **not** enabled (NXP ITS metadata warning; FatFS/ITS not required for this design).

## Migration v1 → v2 (value-preserving, power-fail tolerant)

1. Authenticate latest v1 record (legacy HMAC-SHA256(domain, UUID) + mbedTLS GCM).  
2. Snap `quanta` / `seq`.  
3. Generate ELS opaque AES-256; stage RFC3394 blob (`BLOB_STAGED`, commit marker still erased).  
4. Re-import; GCM round-trip + wrong-opaque-key negative check.  
5. Append **same quanta** as first v2 journal record; read-back auth.  
6. Phrase-program commit marker → `RH_KEY_VERSION=2` / `COMMITTED` (**no sector erase** on commit).  
7. v1 ciphertext left intact until after successful commit.

Recovery: incomplete blob → ignore, stay v1; staged blob without v2 record → v1 value + continue; staged + authenticable v2 → commit; committed → v2 only.

## Timing semantic

**600 s (`RH_QUANTUM_SECONDS`) is the persisted run-hours accounting quantum** and the background service interval. It is **not** a 15-minute quantum.

## Regression

Tool: `tools/runhours_key_hardening_regress.py`  
Artifact: `docs/evidence/RUNHOURS_KEY_HARDENING_REGRESS.json`

| # | Check | Result |
|---|--------|--------|
| 1 | Init / migrate with new key; quanta preserved | **PASS** (first migrate 140→140; later boots key_ver=2) |
| 2 | Encrypt/decrypt/auth across reset | **PASS** |
| 3 | Wrong-key builtin prove at migrate | **PASS** |
| 4 | Tag/phrase tear → quanta unchanged | **PASS** |
| 5 | Reset during program/commit | **PASS** |
| 6 | One sector rollover | **PASS** |
| 7–8 | Remap 0→1→0 + newer OTA (3.4→3.5→3.6); journal survives | **PASS** |
| 9 | No secret in STATUS/RHDIAG | **PASS** |

Overall: `RUNHOURS_KEY_HARDENING_REGRESS.json` → **`"pass": true`**.

## Confidentiality / anti-tamper (final)

- **Confidentiality:** Journal payload ciphertext under a device-unique AES-256 key that never appears as plaintext in Git, logs, dist, diagnostics, or normal app key buffers after load; wrap uses ELS DIE_KEK (device-bound).  
- **Anti-forgery / authenticity:** AES-GCM tag binds AAD (format/seq/generation/sector/slot); wrong key / bit-flip / torn commit rejected.  
- **Not claimed:** physical debug open (Develop lifecycle); attacker with full ELS/debug compromise; secrecy of the RFC3394 blob alone (blob is wrapped, not secret-as-plaintext).

## Code

- `firmware/app/src/runhours_crypto.c`, `runhours_keystore.c`, `runhours_journal.c`  
- Docs: this file; `docs/security-design.md`; `docs/reuse-map.md`; `docs/dev-log.md`
