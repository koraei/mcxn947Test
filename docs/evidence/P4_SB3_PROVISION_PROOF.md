# P4 — SEC 26.06 CUST_MK_SK provision + SB3.1 proofs (DEV-UNIT-01)

**Date:** 2026-09-03  
**Status:** P4 exit criteria met (correct SB3 accept + wrong-key reject + bootable app).  
**Note:** Host MCU-Link VCOM **TX** currently returns `semaphore timeout` (RX works). Stock `xmodem_sb3` shell path was therefore exercised via NXP’s documented alternate `blhost receive-sb-file` of the same NXP-template SB3 packages while `ota_mcuboot_basic` remained the target firmware image.

## SEC tool

| Item | Value |
|------|-------|
| Path | `C:\nxp\SEC_Provi_26.06\bin\securep.exe` |
| ProductVersion | 26.06.0.0 |
| CLI | MCUXpresso Secure Provisioning Tool Version 26.06.b260612 |
| Workspace | `C:\mcxn-secrets\DEV-UNIT-01\sec-workspace` (secrets only; never commit) |

## Pre-write backups

| File | SHA-256 |
|------|---------|
| `backup\cmpa_pre_p4.bin` | `bffe78730df4c218f0d34ddd126ca34bfc79f365c435669311aeaf3084c01500` |
| `backup\cfpa_pre_p4.bin` | `12efb28ee3d94d72b5e02af94b14c2e55348dacf5cab60f01d76202b6af566ca` |

## Provisioning config inspection (before on-target write)

- Lifecycle: **Develop** (`open_develop`)
- Boot: `signed_sb` + `ifr_memory` + `device_hsm`
- USB ISP: `0x1FC9:0x014F`
- `--script-only` build/write scripts inspected: **no** lifecycle close, **no** debug lock, **no** NPX lock, **no** seal
- CMPA word diffs vs pre-P4 (only intentional SB3/signed Develop deltas):
  - `0x050`: `SEC_BOOT_EN` → `ECDSA_SIGNED` (0x3) — required by SEC `signed_sb`
  - `0x060..0x07C`: **RKTH** programmed
  - `BOOT_SRC` unchanged: `SECONDARY_BOOTLOADER`
  - NPX lock contexts: not locked; CC_SOCU debug remains usable

## Keys / secrets (location only)

- Unique random `CUST_MK_SK` + `SB_SEED` under `C:\mcxn-secrets\DEV-UNIT-01\`
- RKTH: `670ee45aba45117a081a87d82ac4f079241f98b3170053888f63c5b69e05457f`
- IMG signer: workspace `keys/IMG1_1_p256.pem`

## On-target write

`write_image_win.bat` (ISP):

1. `receive-sb-file` `dev_hsm_provisioning.sb` (CUST_MK_SK + CMPA) → Success  
2. CFPA write → Success  
3. `receive-sb-file` signed IFR MCUboot SB → Success  

Post-P4 live CMPA SHA-256: `b66746de53ae92e50ecc47c2293d96d321f80864e40fccf21a32d122592e9ef6`  
Security state after write: **UNSECURE** / Develop (`get-property 17` → `0x5aa55aa5`)

## Stock SB3 proofs (`ota_mcuboot_basic`)

SB3 YAML started from NXP template  
`mcuxsdk/examples/ota_examples/_common/sb3_templates/mcxn_sb3_cfg_primary_slot.yaml`  
(secondary load @ `0x00100000`).

| Test | Result |
|------|--------|
| Correct `CUST_MK_SK` SB3 via `blhost receive-sb-file` | **PASS** (`Response status = 0`) |
| Wrong `CUST_MK_SK` SB3 (separate random key) | **FAIL** (`Response status = 1`) |
| Firmware still bootable | **PASS** — MCUboot → app shell |

### Correct-key boot evidence (padded V2)

```text
Primary   slot: version=1.0.0+0
Secondary slot: version=2.0.0+0
Image 0 loaded from the secondary slot
Booting the secondary slot - flash remapping is enabled
* Basic MCUBoot application example *
```

### Wrong-key evidence

```text
blhost ... receive-sb-file ota_sb_secondary_WRONG_KEY.sb
Response status = 1 (0x1) Fail.
```

Secondary slot still held prior good image header (`IMAGE_MAGIC 0x96f3b83d`, version 2) after wrong-key reject.

## Workspace backup

Secrets tree: `C:\mcxn-secrets\DEV-UNIT-01\sec-workspace\` (keys, configs, bootable_images, ota_images, scripts).

## Open item (non-blocking for P4 crypto exit)

MCU-Link VCOM **host→device** writes fail with semaphore timeout; RX works. Re-run `xmodem_sb3` over serial after VCOM TX is restored; crypto/path already proven with the same SB3 packages via ISP `receive-sb-file`.

## P4 exit checklist

- [x] Correct-key SB3 accepted  
- [x] Wrong-key SB3 rejected  
- [x] SEC workspace under secrets  
- [x] ISP recovery path still works (`ispmode` + `blhost`)  
- [x] Ethernet SB3 (P5) — **PASS** — see `docs/evidence/P5_ETHERNET_SB3_PROOF.md`  
