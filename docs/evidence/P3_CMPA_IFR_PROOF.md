# P3 proof — CMPA BOOT_SRC + IFR MCUboot + signed V1

**Date:** 2026-09-03  
**Unit:** DEV-UNIT-01 / UUID `9DA8D48D0DDCD755903E8FBD3836C153`

## ISP transport
- J11 HS USB + J17 MCU-Link
- Enter: `nxpdebugmbox -i mcu-link -s MNZW4VYTFX113 cmd -f mcxn947 ispmode -m 5`
- Device: `VID_1FC9/PID_014F`
- `blhost -u 0x1FC9,0x014F -- get-property 1` → ROM K3.2.0

## Pre-write backups (blhost-verified)
| File | SHA-256 |
|------|---------|
| `C:\mcxn-secrets\DEV-UNIT-01\backup\cmpa_pre_p3.bin` | `9f56cda75fefeab90f6fa5d5ddc9601544b121732c5ecccab32e631060453a5d` |
| `C:\mcxn-secrets\DEV-UNIT-01\backup\cfpa_pre_p3.bin` | `12efb28ee3d94d72b5e02af94b14c2e55348dacf5cab60f01d76202b6af566ca` |

ISP read matched mem-tool backups exactly before any write.

## CMPA inspect (NXP SDK `cmpa.bin`)
- Intent: `BOOT_CFG.BOOT_SRC=SECONDARY_BOOTLOADER (0b10)` only
- Post-program: same + ROM-filled `CMPA_CRC32` / `CMPA_CMAC*` trailer (expected)
- Live post image: `backup\cmpa_post_p3_live.bin` SHA-256 `bffe78730df4c218f0d34ddd126ca34bfc79f365c435669311aeaf3084c01500`

## Programming (NXP flow)
```text
blhost -u 0x1FC9,0x014F -- flash-erase-region 0x01008000 32768 0
blhost -u 0x1FC9,0x014F -- write-memory 0x01008000 mcuboot_opensource_cm33_core0.bin
blhost -u 0x1FC9,0x014F -- write-memory 0x01004000 cmpa.bin
```
IFR head verified vs MCUboot binary after reset.

## Signed V1
- App rebuilt **without** standalone linker (vectors @ `0x400`)
- `imgtool sign` with `--align 16 --version 1.0.0 --slot-size 0x100000 --header-size 0x400 --pad-header --pad --confirm`
- Key: SDK `sign-ecdsa-p256-priv.pem`
- Flashed: `C:\mcxn\builds\app_v1\app_v1_SIGNED.bin` (1 MiB) via LinkServer `@0x0`

## Boot / functional verify
- UART: `hello sbl.` → MCUboot 2.3.0 → `Primary slot: version=1.0.0+0` → ECDSA OK → jump `@0x400` → V1
- Ping `192.168.2.90` 4/4
- `Hello MCXN` → `Hello PC!`
- `STATUS version=1.0.0 variant=V1 uuid=9DA8D48D…`

## ISP recovery proof
Re-entered ISP; re-erased/re-wrote IFR MCUboot; re-wrote live CMPA; reset; IFR head match; STATUS OK again.

## Wrong-signer negative test (P3.5)
- Signed same binary with alternate ECDSA key → flashed slot 0
- UART: `Image not found` / `Unable to find bootable image` (no V1 execution)
- Restored `app_v1_SIGNED.bin`; STATUS V1 OK again
- UART log: `C:\mcxn\builds\p3_wrong_signer_uart.txt`

## Not done (out of P3 scope)
No lifecycle / debug-lock / secure-boot / fuse / seal / NPX / CFPA changes beyond CMPA BOOT_SRC + ROM CRC/CMAC.  
Stock IFR MCUboot used (no extra boot-LED overlay patch).
