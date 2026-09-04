# Security design — FRDM-MCXN947 Secure Ethernet OTA

**Status:** Architecture frozen as of P7 (2026-09-03). No further security writes planned.

---

## Boot chain (proven, frozen)

```
NXP ROM (immutable)
  │  reads CMPA → BOOT_SRC=SECONDARY_BOOTLOADER, SEC_BOOT_EN=ECDSA_SIGNED
  │  reads MBI from IFR (0x01008000, 32 KB slot)
  │  verifies ECDSA-P256 signature; RKTH in cert block must match CMPA.ROTKH
  ▼
MCUboot (IFR 0x01008000, signed MBI 24 768 B)
  │  processes SB3.1 OTA package from inactive app slot
  │  authenticates SB3 with per-unit CUST_MK_SK (AES-CBC-MAC)
  ▼
Application slot A  0x00080000  (1 MiB, imgtool-signed)
Application slot B  0x00180000  (1 MiB, imgtool-signed, OTA target)

OTA delivery: mTLS TCP:5555 → decrypt → [OTAS header][raw SB3.1 stream]
Normal app:   mTLS TCP:5000 → decrypt → Hello/ECHO/STATUS plaintext
```

---

## Security state (DEV-UNIT-01, post-P7)

| Property | Value | Set at |
|----------|-------|--------|
| `BOOT_SRC` | `SECONDARY_BOOTLOADER (0b10)` | P3 |
| `SEC_BOOT_EN` | **`ECDSA_SIGNED`** — ROM auth ON | P3 |
| `ROTKH` | `670EE45ABA45117A081A87D82AC4F079241F98B3170053888F63C5B69E05457F` | P3 |
| RoT key | ROT1_p256 (ECDSA-P256); one active slot | P3 |
| Image signing key | IMG1_1_p256 (ECDSA-P256), certified by ROT1 | P3 |
| `CUST_MK_SK` | 32-byte AES key, per-unit unique; stored in CMPA blob | P4 |
| `CUST_MK_SK` fingerprint | `fb954a586b2259ca427a7af70dcb91bb6035430e18fa49c3c0e7ab0b4da4e535` | P4 |
| Lifecycle | **`Develop`** — SWD/DAP open, ISP recovery available | P3 |
| Debug (CC_SOCU_PIN) | All `USE_DAP` | P3 |
| NPX/PRINCE | Disabled (all context words = 0) | P3 |
| UUID_CHECK | Disabled | P3 |
| Key revocation (CFPA) | `IMAGE_KEY_REVOKE = 0` — no revocations | — |
| IFR MCUboot slot | Hardware read-protected (`OEM_ROM_RWXL_CODE`) | P3 |

---

## OTA update security (P4 / P5 / P6)

- SB3.1 package authenticated by `CUST_MK_SK` inside the NXP ROM crypto subsystem.
- Wrong-key SB3 rejected by `sb3_api` before any flash write.
- Corrupt SB3 rejected; slot not marked ready-for-test.
- 180-second update window: new sessions refused after window closes.
- Device UUID checked in OTAS header before SB3 streaming begins (host preflight + firmware guard).

## Host packaging (P6)

- Unit registry (`units/*.json`) stores UUID + `cust_mk_sk_fingerprint` only — never keys/PEM/hex.
- `dist/<unit>/<version>/` contains SB3 + sidecar manifest + technician README — no secrets.
- Sidecar SHA-256 binds the technician package to git commit + tool versions.
- Wrong-unit SB3 rejected by ROM/`CUST_MK_SK` even if host UUID check is bypassed.

---

## Transport authentication (mTLS phase)

- Mutual TLS (mbedTLS 3.x / PSA / ELS_PKC) on **both** `:5000` and `:5555`.
- Application still sees decrypted plaintext (Hello / OTAS+SB3 unchanged).
- SB3.1 + `CUST_MK_SK` remain mandatory for firmware authenticity/unit binding.
- Dev CA + per-unit server cert + PC client cert live under `secrets_root/mtls/` (not in Git).
- Host pins server cert SHA-256 (`units/*.json` → `mtls_server_cert_sha256`).
- Application slot images are signed with `mcxn.toml` `imgtool_key` (MCUboot), **not** `IMG1_1` (ROM/MBI).

## Encrypted run-hours journal key (post Gate 10 hardening)

**FREEZE (2026-09-04, owner):** v2 ELS opaque journal-key architecture is frozen. Do **not** change crypto, keystore layout, key location, migration logic, or related APIs for the endurance campaign unless the owner explicitly re-opens this freeze.

| Property | Value |
|----------|--------|
| Mechanism | NXP PSA opaque AES-256-GCM @ location `0xc00401` (`PSA_KEY_LOCATION_S50_RFC3394_STORAGE`) |
| Runtime | Volatile ELS opaque key handle; AEAD via `psa_aead_encrypt/decrypt` |
| Persistence | Device-bound RFC3394 wrapped blob in `ML_PLATFORM_RESERVE_A` (dual 8 KiB slots); **not** plaintext AES |
| Key version | `RH_KEY_VERSION=2` / `key_id` in keystore + `RHDIAG` (`key_ver`, `key_id`, `ks`) |
| Legacy | v1 = HMAC-SHA256(domain, SILICONID UUID); one-time value-preserving migrate to v2 |
| Separated from | `CUST_MK_SK`, imgtool, ROM/MBI, SB3 signer, mTLS keys |
| Protected state | **Unchanged** — no CMPA/CFPA/IFR/lifecycle/`CUST_MK_SK` writes |
| Quantum | **600 s** = persisted run-hours accounting quantum (= background cadence); not 15 minutes |

Evidence: `docs/evidence/RUNHOURS_KEY_HARDENING.md`

## Explicit non-claims (by design, not defects)

- No automatic application-health rollback (DIRECT_XIP; no revert).
- No NPX/PRINCE encryption.
- Sidecar manifest is not a device-verified security object.
- Lifecycle is `Develop`; debug/ISP access intentionally open.
- No lifecycle advancement, no debug lock, no seal — outside current project scope.
- Downgrade OTA (e.g. 2.0.0→1.0.0) is not a supported qualification path; use equal/newer version.

---

## What is NOT protected in current state

- Physical MCU-Link SWD/JTAG access (debug open by design).

---

## Evidence documents

| Phase | Evidence |
|-------|---------|
| P3 — CMPA/IFR provisioning | `docs/evidence/P3_CMPA_IFR_PROOF.md` |
| P4 — CUST_MK_SK + SB3 signing | (sec-workspace logs) |
| P5 — Ethernet SB3 OTA hardware matrix | `docs/evidence/P5_ETHERNET_SB3_PROOF.md` |
| P6 — Host CLI + packaging | `docs/evidence/P6_HOST_CLI_PROOF.md` |
| P7 — ROM secure boot gate report | `docs/evidence/P7_ROM_SECBOOT_GATE_REPORT.md` |
| Gate 10 — encrypted run-hours | `docs/evidence/RUNHOURS_GATE10.md` |
| Run-hours key hardening (ELS opaque) | `docs/evidence/RUNHOURS_KEY_HARDENING.md` |

*Last updated: 2026-09-03 (P7 approved, architecture frozen)*
