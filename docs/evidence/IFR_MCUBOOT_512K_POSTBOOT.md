# IFR MCUboot 512 KiB — post-flash boot gate

**Date:** 2026-09-04  
**CMPA/CFPA:** **unchanged** (no write)  
**IFR:** rewritten with rebuilt 512 KiB MCUboot MBI only  
**Backup:** `C:\mcxn-secrets\DEV-UNIT-01\backup\pre_ifr_512k_20260904\`

## Boot path (UART)

```
hello sbl.
MCUboot 512K remap LIM=15
Bootloader Version 2.3.0
Built Sep  4 2026 12:44:26
Upgrade mode: FLASH REMAP
...
bootutil_verify_sig: ECDSA builtin key 0
Image 0 loaded from the primary slot
Jumping to the image
Booting the primary slot - flash remapping is disabled
=== MCXN947 Secure OTA prototype ===
App V3 version=3.1.0
```

Evidence capture: `docs/evidence/IFR_512k_boot_uart.txt`

| Gate | Result |
|------|--------|
| ROM → IFR MCUboot → app | PASS |
| Banner `MCUboot 512K remap LIM=15` | PASS |
| ECDSA image verify | PASS |
| Hello `Hello PC! V3-PULSE-RED` | PASS |
| STATUS `version=3.1.0 variant=V3` | PASS |
| CMPA/CFPA programmed | **NO** (HOLD) |

## Next

Prove clean V1/V2 512 KiB A↔B OTA; shared pools untouched; then journal + HW power-cut.
