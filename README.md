# README — FRDM-MCXN947 Secure Ethernet OTA Prototype

Board static IP (fixed): **192.168.2.90/24**, gateway **192.168.2.24** (do not change PC NIC).

## Quick commands

```powershell
python tools/mcxn.py doctor
python tools/mcxn.py build v1
python tools/mcxn.py release --unit DEV-UNIT-01 --version 2.0.0
python tools/mcxn.py update --sb3 dist/DEV-UNIT-01/2.0.0/DEV-UNIT-01_2.0.0_V2.sb3
python tools/mcxn.py hello
python tools/mcxn.py status
```

Runbooks: `docs/runbooks/release.md`, `docs/runbooks/technician-update.md`, `docs/runbooks/recover.md`  
Evidence: `docs/evidence/P6_HOST_CLI_PROOF.md`  
Unit registry: `units/DEV-UNIT-01.json` (non-secret). Secrets: `C:\mcxn-secrets\`.

Plan authority: `doc/FRDM_MCXN947_SECURE_ETHERNET_OTA_AUTONOMOUS_AGENT_PLAN_REV_C_FINAL.md`  
SDK: `C:\mcxn\mcuxsdk-ws` (`v26.06.00-LTS`)
