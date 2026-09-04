# IFR MCUboot 512 KiB — pre-flash geometry & RKTH gate

**Date:** 2026-09-04  
**CMPA/CFPA:** **unchanged** (HOLD surgical CMPA)  
**Source:** `firmware/mcuboot_ifr_512k` (from NXP board port; rebuilt, not binary-patched)

## Geometry proof (built ELF)

| Check | Value | Result |
|-------|-------|--------|
| Slot A `fa_off` / `fa_size` | `0x0` / **`0x00080000`** | PASS (`boot_flash_map`) |
| Slot B `fa_off` / `fa_size` | `0x00100000` / **`0x00080000`** | PASS |
| NPX `SBL_EnableRemap` | words `0x000f5a5a`, `0x0f00a5a5` → **LIM/LIMDP=15** | PASS |
| Banner | `MCUboot 512K remap LIM=%u` | linked |
| imgtool / app | `--slot-size 0x80000` + `APP_FLASH_LAYOUT_512K` | required for apps |

`0x00100000` still appears as **Slot B base**, not as slot size.

## MBI

| Item | Value |
|------|-------|
| Raw bin | 29 672 B |
| Signed MBI | see `bootable_images/frdmmcxn947_mcuboot_opensource_512k.bin` |
| IFR limit | 32 768 B |
| RKTH (nxpimage) | `670ee45aba45117a081a87d82ac4f079241f98b3170053888f63c5b69e05457f` |
| Live RoTKH | `670EE45ABA45117A…5457F` | **MATCH** |
| Signer | existing `IMG1_1_p256.pem` + cert block |

## Not changed

- CMPA / `FLASH_REMAP_SIZE` / CFPA / lifecycle / debug / `CUST_MK_SK`
