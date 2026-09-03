# Recover — FRDM-MCXN947 DEV-UNIT-01

## Identity

| Item | Value |
|------|-------|
| Probe | `MNZW4VYTFX113` |
| VCOM | COM9 @ 115200 |
| UUID | `9DA8D48D0DDCD755903E8FBD3836C153` |
| Secrets | `C:\mcxn-secrets\DEV-UNIT-01\` |

## ISP entry (proven)

USB-C on **J11** (HS) + **J17** (MCU-Link). Prefer a USB 2.0-capable host port for J11.

```text
nxpdebugmbox -i mcu-link -s MNZW4VYTFX113 cmd -f mcxn947 ispmode -m 5
blhost -u 0x1FC9,0x014F -- get-property 1
```

Alternate: hold SW3, tap SW1, release SW3; same `blhost` USB command if `0x014F` appears.

## PFR backups

| File | SHA-256 | Notes |
|------|---------|-------|
| `backup\cmpa_pre_p3.bin` | `9f56cda75fefeab90f6fa5d5ddc9601544b121732c5ecccab32e631060453a5d` | Pre-P3 erased CMPA |
| `backup\cfpa_pre_p3.bin` | `12efb28ee3d94d72b5e02af94b14c2e55348dacf5cab60f01d76202b6af566ca` | Unchanged through P3 |
| `backup\cmpa_post_p3_live.bin` | `bffe78730df4c218f0d34ddd126ca34bfc79f365c435669311aeaf3084c01500` | BOOT_SRC=IFR + ROM CRC/CMAC |
| `backup\cfpa_post_p3_live.bin` | same as pre | |

## Restore CMPA / IFR MCUboot (ISP)

```text
blhost -u 0x1FC9,0x014F -- flash-erase-region 0x01008000 32768 0
blhost -u 0x1FC9,0x014F -- write-memory 0x01008000 C:\mcxn\builds\mcuboot_opensource\mcuboot_opensource_cm33_core0.bin
blhost -u 0x1FC9,0x014F -- write-memory 0x01004000 C:\mcxn-secrets\DEV-UNIT-01\backup\cmpa_post_p3_live.bin
```

To return toward factory CMPA (all `0xFF`): use SPSDK `pfr erase-cmpa` (not exercised in P3), then optionally rewrite pre image if needed.

## Restore signed V1 application

```text
LinkServer flash -p MNZW4VYTFX113 MCXN947:FRDM load C:\mcxn\builds\app_v1\app_v1_SIGNED.bin --addr 0x0
```

Or standalone P2 image (no MCUboot header) only after clearing `BOOT_SRC` / restoring pre-P3 CMPA.

## Ethernet SB3 update (P5)

```text
cd c:\temp\mcxn947Test
python tools/mcxn.py status
python tools/mcxn.py update --sb3 C:\mcxn-secrets\DEV-UNIT-01\sec-workspace\ota_images\ota_sb_product_v2_pad.sb
python tools/mcxn.py status   # expect variant=V2
```

Protocol: `docs/protocol-update.md`. New accepts only in first 180 s after app start.

## VCOM TX tool issue

MCU-Link VCOM host→device writes fail (`semaphore timeout`); RX works. Do not rely on serial XMODEM until restored. Prefer Ethernet update or ISP `blhost receive-sb-file`.

## Proven

2026-09-03: ISP re-entry, IFR erase/rewrite, CMPA rewrite, reset → V1 STATUS OK. See `docs/evidence/P3_CMPA_IFR_PROOF.md`.  
2026-09-03: Ethernet SB3 V1→V2 + negatives. See `docs/evidence/P5_ETHERNET_SB3_PROOF.md`.

## Do not

- Lose `CUST_MK_SK` backup after P4 provisioning
- Close lifecycle / lock debug / program NPX on this prototype
- Change CMPA/CFPA/`CUST_MK_SK` during transport-only work
