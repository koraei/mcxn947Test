# P4 gate request — SEC 26.06 / first CUST_MK_SK provisioning (NOT executed)

**Status:** Waiting for SEC install + owner approval before any device-HSM / key provisioning.

## Why stop
Rev C P4 requires **MCUXpresso Secure Provisioning Tool 26.06** (`securep.exe`) and a unit SEC workspace. Tool is **not installed** on this host.

## P3 closed
See `docs/evidence/P3_CMPA_IFR_PROOF.md` — ROM → IFR MCUboot → signed V1 proven; ISP recovery proven; wrong-signer rejected.

## Exact next gated operations (after SEC install)
1. Create SEC workspace `DEV-UNIT-01` (lifecycle Develop)
2. Generate random `CUST_MK_SK` + backup workspace under `C:\mcxn-secrets\DEV-UNIT-01\`
3. Owner approval before first on-target provision (`P4.3`)
4. Stock `ota_mcuboot_basic` / `xmodem_sb3` correct-key + wrong-key proofs

## Do not without approval
- Close lifecycle / lock debug / NPX / unrelated fuses
- Start Ethernet SB3 (P5) before P4 exit criteria

## Owner actions
1. Install SEC 26.06 from nxp.com (account download)
2. Reply with install path / confirm `securep.exe` on PATH
3. Reply **APPROVE P4 PROVISION** when ready for on-target `CUST_MK_SK` (after workspace created & backed up)

## 2026-09-03 — APPROVE received; SEC binary not found

Owner: `APPROVE P4 PROVISION` + claimed SEC 26.06 install, but path field was placeholder `<PASTE EXACT PATH HERE>`.

### Agent verification (no device writes)
Searched and did **not** find `securep.exe` (or alternate SEC launcher) under:
- `C:\NXP`, `C:\nxp`, `C:\Program Files\NXP`
- `C:\Users\mostafak\AppData\Local\Programs`, `...\Local\NXP`
- `where securep`, winget Secure packages (none for MCUXpresso SPT)
- Python walk of NXP/local roots

Present NXP tools: LinkServer 25.6.131, MCUXpresso IDE 25.6.136 only.

### Stop reason
Cannot verify SEC **exactly 26.06** or inspect generated provisioning config without `securep.exe`. Per owner conditions: **no key/security programming** until version + path confirmed.

### Need from owner
Paste the **exact** `securep.exe` full path (e.g. from Start Menu → Open file location), or reinstall SEC 26.06 and confirm the path. Then agent resumes P4.

## 2026-09-03 — Path given but still missing on host

Owner provided:
`C:\nxp\SEC_Provi_26.06\bin\securep.exe`

Agent check: **path does not exist** (`Test-Path` = False). `C:\nxp` currently contains only:
- `LinkServer_25.6.131`
- `MCUXpressoIDE_25.6.136`

No `SEC_Provi*` folder; `securep.exe` not found under common NXP locations. **No P4 device writes performed.**

Please confirm install completed on **this** PC and re-send a path that Explorer can open (or run `dir C:\nxp\SEC_Provi_26.06\bin\securep.exe` and paste output).
