# M2/M3 mTLS proof (after boot-hang fix)

**Date:** 2026-09-03  
**Board:** DEV-UNIT-01 @ `192.168.2.90`  
**Branch:** `feat/mtls-tcp-socket`

## Boot hang root cause (prerequisite)

See `docs/evidence/MTLS_BOOT_HANG_ROOT_CAUSE.md`.

Wrong MCUboot signer (`IMG1_1` vs SDK `sign-ecdsa-p256-priv.pem`). After re-sign with `mcxn.toml` `imgtool_key`, app boots.

## M2 — `:5000` mTLS

| Test | Result |
|------|--------|
| Boot banner + `mtls: global init OK` | PASS |
| Ping | PASS |
| `Hello MCXN` → `Hello PC!` over mTLS | PASS |
| Raw TCP plaintext | Rejected (`ConnectionResetError`) |
| No client certificate | Rejected |
| Wrong CA | `SSLCertVerificationError` |
| Wrong server fingerprint | `FingerprintError` |
| 5× reconnect | PASS |
| 100× reconnect soak | **PASS** (35.7 s) |

UART: `C:\mcxn\builds\mtls_boot_uart_ok.txt`

## M3 — `:5555` mTLS + SB3

| Test | Result |
|------|--------|
| Plaintext OTAS on `:5555` | Rejected |
| Host `sendall(hdr+sb3)` single blob | FAIL (OpenSSL EOF) — fixed: 8 KiB chunks in `send_otas` |
| mTLS OTAS V1→V2 (chunked) | PASS → V2 |
| CLI `mcxn update` V2→V3 | **UPDATE PASS** → `version=3.0.0 variant=V3` |
| Corrupt SB3 (byte flip) | Fail as designed; stayed on then-current image |
| Downgrade V2→V1 (version 1.0.0) | Device replied `OK` then still ran V2 (unsupported path; use newer/equal version) |

## Map / resources (debug build, no APP_SIZE change)

| Region | Used |
|--------|------|
| `m_text` | ~784 KB / 798 KB (~96%) |
| `m_data` | ~184 KB / 312 KB |
| heap `__heap_size__` | `0x1B000` |
| task stacks hello/update | 4096 words each |

HTTPSRV Kconfig: **not set**. No APP_SIZE / Core1 reclaim.

## Security writes

None (CMPA/CFPA/IFR/`CUST_MK_SK` untouched).

## Remaining (M4)

- Full 24 h soak @ ~100 KB/s
- 1000 reconnects / 100 bad-cert / 50 abort / 20 link-cycle matrix
- Optional lean mbedTLS overlay to reclaim flash headroom under 96%
