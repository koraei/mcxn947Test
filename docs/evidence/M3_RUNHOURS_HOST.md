# M3 host journal fault matrix

**Date:** 2026-09-04  
**Tool:** `python tools/runhours_host_model.py`  
**Artifact:** `docs/evidence/M3_runhours_host_faults.json`

## Protocol (aligned to plan §§7–10)

- AES-256-GCM, commit-last 64-byte records, READY-last sector headers
- Nonce = `be64(sector_generation) || be32(slot)`
- Never erase newest valid sector before checkpoint in another sector

## Cases (all PASS)

| Case | Expected recovery |
|------|-------------------|
| cut after phrase 0..2 | previous quanta |
| cut after phrase 3 (commit) | 10 or 11 (atomic boundary) |
| cut during sector erase | previous latest |
| cut before READY marker | previous latest |
| cut after READY before checkpoint | previous latest |
| corrupt ciphertext/tag | previous valid |
| partially erased sector | ignore dirty; continue |
| torn commit | previous |
| repeated boots after interrupt | ≥ previous; then append OK |
| sector transition recycle | newest after fill |
| erased RAM / VBAT stand-in | recover from flash |

**Device on-flash AES-GCM append** remains stubbed (`RH_ERR_NOT_PROVISIONED`) until post-CMPA remap makes pools non-swapping. Do not enable live journal writes under current 1 MiB remap.
