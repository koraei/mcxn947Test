# Security design (lean)

## Protected by NXP (target end-state)
- MCUboot ECDSA-P256 image signature
- SB3.1 confidentiality/authentication with per-unit `CUST_MK_SK`
- Host UUID check before transfer (operator safety, not crypto)

## Host packaging (P6)
- Unit registry (`units/*.json`) stores UUID + `cust_mk_sk_fingerprint` only
- `dist/<unit>/<version>/` contains SB3 + sidecar manifest + technician README — **never** keys/PEM/hex
- Sidecar SHA-256 binds the technician package to release metadata (git commit, tool versions)
- Device rejects wrong-unit SB3 via ROM/`CUST_MK_SK` even if a host check is bypassed (`--bypass-uuid-check` is test-only)

## Not protected in current Develop/debug-open state
- MCU-Link debug access
- No ROM secure boot of MCUboot until P7
- No TLS on update port (by design)

## Explicit non-claims
- No automatic application-health rollback (DIRECT_XIP has no revert)
- No NPX/PRINCE, no custom crypto formats
- Sidecar is not a device-verified security object
