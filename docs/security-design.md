# Security design (lean)

## Protected by NXP (target end-state)
- MCUboot ECDSA-P256 image signature
- SB3.1 confidentiality/authentication with per-unit `CUST_MK_SK`
- Host UUID check before transfer (operator safety, not crypto)

## Not protected in current Develop/debug-open state
- MCU-Link debug access
- No ROM secure boot of MCUboot until P7
- No TLS on update port (by design)

## Explicit non-claims
- No automatic application-health rollback (DIRECT_XIP has no revert)
- No NPX/PRINCE, no custom crypto formats
