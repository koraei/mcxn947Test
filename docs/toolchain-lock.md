# Toolchain lock

**Recorded:** 2026-09-03  
**Plan baseline:** MCUXpresso SDK v26.06.00-LTS, SEC 26.06 / SPSDK 3.10.0, GCC 14.2.x family

| Tool | Version / path | Notes |
|------|----------------|-------|
| west | 1.5.0 | `python -m west` |
| arm-none-eabi-gcc | 14.3.1 20250623 (Arm GNU Toolchain 14.3.Rel1) | Plan asked 14.2.x family; 14.3.x installed — accepted, record deviation |
| cmake | 4.2.0-rc2 | `C:\Program Files\CMake\bin` |
| ninja | 1.13.0.git.kitware.jobserver-pipe-1 | Python Scripts |
| Python | 3.11.9 | |
| LinkServer | 25.6.131 | `C:\nxp\LinkServer_25.6.131` — probes FRDM-MCXN947 OK |
| MCUXpresso IDE | 25.6.136 | `C:\nxp\MCUXpressoIDE_25.6.136` (not required for CLI flow) |
| MCUXpresso for VS Code / Cursor | installed via marketplace VSIX `NXPSemiconductors.mcuxpresso` | Cursor marketplace ID failed; VSIX sideload OK |
| clangd | vscode-clangd 0.6.0 | |
| YAML | redhat.vscode-yaml | |
| pyserial | 3.5 | |
| pytest | 9.1.1 | |
| SEC `securep.exe` | **NOT INSTALLED** | Required by P4+; download from https://nxp.com/sec (needs NXP account) |
| SPSDK / nxpimage | **NOT INSTALLED** | Prefer instance bundled with SEC 26.06 |
| MCUXpresso SDK | west init `v26.06.00-LTS` @ `C:\mcxn\mcuxsdk-ws` | `west update` in progress |

## SDK pin commands

```powershell
west init -m https://github.com/nxp-mcuxpresso/mcuxsdk-manifests.git --mr v26.06.00-LTS C:\mcxn\mcuxsdk-ws
cd C:\mcxn\mcuxsdk-ws
west update --narrow -o=--depth=1
```

## Deviations from plan text

1. Host GCC is **14.3.x**, not 14.2.x — same Arm GNU 14 family; keep unless an example fails.
2. LinkServer is **25.6.131**, not a 26.06-branded package — successfully enumerates FRDM-MCXN947; upgrade only if flash/debug fails.
3. SEC 26.06 not yet present — blocks P4 provisioning only; P0–P3 proceed with SDK + LinkServer.
