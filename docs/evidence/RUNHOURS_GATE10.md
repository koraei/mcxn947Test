# Gate 10 — Encrypted running-hours journal (HW evidence)

**Date:** 2026-09-04  
**Board:** DEV-UNIT-01  
**CMPA/CFPA/IFR MCUboot:** **unchanged**  
**App:** lean + `APP_FLASH_LAYOUT_512K` (V1 1.0.1 / V2 2.0.1 / V3 3.2.1)

## Physical journal map

| Region | Address | Size | Erase sectors |
|--------|---------|------|---------------|
| Pool A | `0x000A0000` | 64 KiB | 8 × 8 KiB (sector IDs 0–7) |
| Pool B | `0x001A0000` | 64 KiB | 8 × 8 KiB (sector IDs 8–15) |
| Total | | **128 KiB** | 16 sectors |

Outside 512 KiB NPX remap window (`LIM=15`). SB3 erase/load remains `0x00100000` + `0x00080000` only.

## Crypto / key

| Item | Choice |
|------|--------|
| AEAD | **AES-256-GCM** via NXP-backed **mbedTLS** (`mbedtls_gcm_*`) |
| Tag | 128-bit |
| Nonce | `be64(sector_generation) \|\| be32(slot)` (12 B) |
| AAD | format/type/seq/generation/sector_id/slot (host model compatible) |
| `K_RH` | **HMAC-SHA256**(`"MCXN947-K_RH-v1"`, SILICONID UUID[16]) → 32 B; not in Git; not CUST_MK_SK / imgtool / SB3 |
| Commit | phrase-3 `COMMIT` magic + `seq` complement; authoritative only after commit + GCM verify |

PUF wrap was not required; no security-state provisioning change.

## Flash arbiter

- FreeRTOS mutex; owners `JOURNAL` / `OTA`.
- OTA takes exclusive ownership for entire SB3 session (released on error; held through reset on success).
- Journal `append` with timeout 0 → `RH_ERR_BUSY` + `deferred` counter.

## Cadence

- Background task: **600 s** per quantum (`RH_QUANTUM_SECONDS`).
- Qual only: Hello `RHFORCE` / `RHWIPE` / `RHFAULT` / `RHDIAG` (do not change production cadence).

## Host fault matrix (Gate A)

`python tools/runhours_host_model.py` → **`runhours_host_fault_matrix PASS`**.

## HW power-cut / reset campaign (Gate B)

Hook stages busy-wait; host issues LinkServer `wiretimedreset` (flash-state equivalent of power loss mid-phrase). Evidence: `docs/evidence/RUNHOURS_HW_CAMPAIGN.json`.

| Case | Result |
|------|--------|
| wipe_virgin | PASS |
| append_5 | PASS |
| cut_before_record | PASS |
| cut_during_phrase0 | PASS |
| cut_during_phrase1 | PASS |
| cut_before_commit | PASS |
| cut_after_commit | PASS |
| sector_rollover (≥130 appends) | PASS |
| rollover erase observed | PASS (`erases≥1`) |

Invariant: recovered quanta is previous or newly committed — never invented. Board remained bootable.

## Remap states (Gate D) + post-qual OTA (Gate E)

| State | Remap | Quanta |
|-------|-------|--------|
| After long journal on V1 | 0 | 136 |
| Secure OTA → V2 2.0.1 | **1** | **136** (unchanged) |
| RHFORCE on remapped | 1 | 137 |
| Secure OTA → V3 3.2.1 | **0** | **137** (unchanged except force) |

Evidence: `docs/evidence/RUNHOURS_OTA_SURVIVE.json`.

## Diagnostics (Hello `RHDIAG`)

Exposes: `seq`, `quanta`, `writes`, `erases`, `auth_fail`, `torn`, `flash_err`, `crypto_err`, `deferred`, `sector`, `remap`, `prov`.

## Implementation files

- `firmware/app/src/runhours_journal.c`, `runhours_crypto.c`, `runhours_task.c`, `flash_arbiter.c`
- Host: `tools/runhours_host_model.py`, `tools/runhours_hw_campaign.py`

## Notes

- FMU re-erase of virgin sectors often returns error; blank CPU-verify after erase is unreliable (CACHE64) — physical dump confirmed `0xFF`; integrity gated by GCM + commit.
- Same-bank program while remapped migrates via checkpoint to the opposite bank before append.
