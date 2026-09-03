# README — FRDM-MCXN947 Secure Ethernet OTA Prototype

Board static IP (fixed): **192.168.2.90/24**, gateway **192.168.2.24** (do not change PC NIC).

## Quick commands

```powershell
$env:ARMGCC_DIR = 'C:\Program Files (x86)\Arm GNU Toolchain arm-none-eabi\14.3 rel1'
$env:Path = "C:\nxp\LinkServer_25.6.131;$env:ARMGCC_DIR\bin;$env:Path"

python tools/mcxn.py doctor
python tools/mcxn.py build v1
python tools/mcxn.py flash v1
python tools/mcxn.py hello
python tools/mcxn.py status
```

Plan authority: `doc/FRDM_MCXN947_SECURE_ETHERNET_UPDATE_AUTONOMOUS_AGENT_PLAN_REV_C_FINAL.md`

SDK: `C:\mcxn\mcuxsdk-ws` (`v26.06.00-LTS`)
