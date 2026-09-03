# P3 gate request — CMPA BOOT_SRC + IFR MCUboot (NOT executed)

**Status:** Waiting for explicit owner approval before any write.

## Board
- Probe: `MNZW4VYTFX113`
- UUID: `9DA8D48D0DDCD755903E8FBD3836C153`
- IP: 192.168.2.90
- Lifecycle assumed Develop; debug open

## Completed before gate
- P0 stock examples + Ethernet ping proof
- P1 CLI/docs
- P2 V1 Hello service on 192.168.2.90:5000 (standalone linker)
- MCUboot example **builds** (`C:\mcxn\builds\mcuboot_opensource`) — not programmed to IFR

## Exact operation requiring approval
NXP FRDM-MCXN947 MCUboot README (ISP mode):

```text
blhost -u 0x1FC9,0x014F -- flash-erase-region 0x01008000 32768 0
blhost -u 0x1FC9,0x014F -- write-memory 0x01008000 mcuboot_opensource.bin
blhost -u 0x1FC9,0x014F -- write-memory 0x01004000 cmpa.bin
```

`cmpa.bin` sets `BOOT_CFG.BOOT_SRC = 0b10` so ROM starts MCUboot from IFR.

## Risk
- Wrong CMPA can prevent normal boot until recovered via ISP
- IFR erase/program is sensitive; mass-erase not planned
- Irreversible relative to “default factory boot source” until CMPA restored

## Required before execute
1. Backup current CMPA/CFPA (read via SEC/blhost) to `C:\mcxn-secrets\DEV-UNIT-01\backup\`
2. Prove ISP entry + blhost connection
3. Save recovery commands in `docs/runbooks/recover.md`
4. Owner replies **APPROVE P3 CMPA/IFR** (or decline)

## Rollback / recovery
1. Enter ISP
2. Restore backed-up CMPA/CFPA with blhost write-memory
3. Re-flash known-good standalone V1 via LinkServer (`west flash -d C:\mcxn\builds\app_v1`)
4. If IFR MCUboot bad: re-write known-good `mcuboot_opensource.bin` or clear BOOT_SRC via restored CMPA

## Also blocked later (not requested now)
- First `CUST_MK_SK` provisioning (P4) — SEC 26.06 not installed yet
