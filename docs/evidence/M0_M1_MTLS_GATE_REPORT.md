# M0 / M1 mTLS progress — gate report

**Date:** 2026-09-03  
**Branch:** `feat/mtls-tcp-socket`  
**Baseline tag:** `p7-frozen-mtls-baseline` @ `49c24af`  
**Plan:** `doc/FRDM_MCXN947_RELIABLE_MTLS_TCP_SOCKET_PLAN_REV_B_FINAL.md`

## Board state NOW (recovered)

- Flashed known-good **plaintext** `app_v2_SIGNED_PAD.bin` to **both** `0x0` and `0x00100000`.
- Live proof: ping OK; `STATUS version=2.0.0 variant=V2`.
- No CMPA/CFPA/`CUST_MK_SK`/IFR writes were performed during this work.

## Completed

### M0 — NXP stock TLS stack (partial)

| Item | Result |
|------|--------|
| Inspect `lwip_httpssrv_mbedTLS/freertos` | Done — mbedTLS3x + PSA + ELS_PKC + `psa_crypto_init` + HTTPSRV TLS BIO |
| Build wrapper `firmware/m0_httpssrv` | **PASS** (debug, static IP 192.168.2.90, IPv6 off, WS off) |
| Footprint | `m_text` ~778 KB / ~990 KB with enlarged M0 linker |
| Sign with unit `IMG1_1_p256` | Done |
| On-target HTTPS proof | **FAIL** — after dual-slot flash board hung (no ping/UART). Restored product image. |
| SDK note | `example.yml` excludes `armgcc@debug` for FRDM-MCXN947; stock map needs MCUboot header linker for IFR boot |

### M1 — PKI + wrapper (code complete; on-target not proven)

| Item | Result |
|------|--------|
| Dev CA + DEV-UNIT-01 server + DEV-PC-01 client (ECDSA-P256) | `C:\mcxn-secrets\mtls\` (not in Git) |
| Public fingerprint in `units/DEV-UNIT-01.json` | `mtls_server_cert_sha256` = DER SHA-256 |
| `mtls_socket.c/.h` | Implemented (NXP BIO pattern, `VERIFY_REQUIRED`, time-flag ignore only) |
| Host `ssl` path | `tools/mcxn_lib/mtls.py`; `hello`/`status`/`echo`/`update` use mTLS |
| Host pytest | **10/10 PASS** |

### Product integrate (M2/M3 code present; boot FAIL)

| Item | Result |
|------|--------|
| Product `prj.conf` + mbedtls3x + ELS_PKC + threading ALT | Linked |
| `:5000` / `:5555` wrapped in mTLS | Code present |
| Build V1 with mTLS | **PASS** — `m_text` **783912 B / 798 KB (95.93%)** |
| Flash signed V1 mTLS | Board **hangs** (no ping, empty UART). Restored V2. |

## Requested human / debug action

**Gate:** Diagnose why the mTLS-enabled application (and earlier M0 HTTPS image) hang after LinkServer flash while pre-mTLS V2 boots.

Suggested next steps (owner/debugger):

1. Attach MCU-Link debugger; capture faulting PC / HardFault / MCUboot reject reason on UART after power-cycle.
2. Confirm whether hang is MCUboot image validation vs app early init (`psa_crypto_init` / ELS / heap).
3. Optionally approve expanding OTA linker `APP_SIZE` (reclaim core1 reservation) and/or `-Os` to reduce flash pressure (~96% used).
4. Keep dual-slot flash discipline (remap): always program **both** slots when replacing the running image via LinkServer.

## Risk / rollback

- **Risk if left on hung image:** board unreachable on Ethernet until reflash.
- **Rollback used:** flash `C:\mcxn\builds\app_v2\app_v2_SIGNED_PAD.bin` @ `0x0` and `0x00100000`.
- **Security state:** unchanged (ROM/IFR/CMPA/CUST_MK_SK frozen).

## Artifacts

- M0 build: `C:\mcxn\builds\m0_httpssrv_mbedtls\`
- Product mTLS ELF/bin: `C:\mcxn\builds\app_v1\mcxn947_secure_ota_cm33_core0.{elf,bin}`
- Secrets PKI: `C:\mcxn-secrets\mtls\`
- Generated creds C: `C:\mcxn-secrets\mtls\generated\mtls_creds.c`
