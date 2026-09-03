# Device state — FRDM-MCXN947

**Last updated:** 2026-09-03  
**Phase:** P5 complete — Ethernet SB3 OTA proven

## Probe

| Field | Value |
|-------|-------|
| Probe | MCU-LINK FRDM-MCXN947 (r0E7) CMSIS-DAP V3.128 |
| Serial | `MNZW4VYTFX113` |
| Device | MCXN947 |
| Board | FRDM-MCXN947 |
| LinkServer | v25.6.131 @ `C:\nxp\LinkServer_25.6.131` |
| VCOM | MCU-Link VCom Port **COM9** @ 115200 (RX OK; TX semaphore timeout — tool issue) |
| HS USB ISP | J11 → `VID_1FC9/PID_014F` (proven) |

## MCU UUID

`9DA8D48D0DDCD755903E8FBD3836C153`

## Network policy

| Field | Value |
|-------|-------|
| Board IP | **192.168.2.90/24** |
| Gateway | 192.168.2.24 |
| Hello port | 5000 |
| Update port | 5555 (new sessions first 180 s) |

## Lifecycle / security state

| Item | Status |
|------|--------|
| Lifecycle | Develop (no close) |
| CMPA | `BOOT_SRC=SECONDARY_BOOTLOADER` + `SEC_BOOT_EN=ECDSA_SIGNED` + RKTH (P4) |
| CFPA | Unchanged vs pre-P3 backup |
| CUST_MK_SK | Provisioned (unit unique; secrets tree only) |
| Debug | Open via MCU-Link |

## Flashed software (as of P5 close)

| Region | Content |
|--------|---------|
| IFR `0x01008000` | NXP `mcuboot_opensource` (SDK 26.06) |
| CMPA `0x01004000` | P4 develop signed_sb CMPA |
| Active app | Product V2 after Ethernet SB3 (test swap; may revert without accept) |

## Evidence

- `docs/evidence/P3_CMPA_IFR_PROOF.md`
- `docs/evidence/P4_SB3_PROVISION_PROOF.md`
- `docs/evidence/P5_ETHERNET_SB3_PROOF.md`
- `docs/protocol-update.md`
- Backups / SEC: `C:\mcxn-secrets\DEV-UNIT-01\`
- Recover: `docs/runbooks/recover.md`
