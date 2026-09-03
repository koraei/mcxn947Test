# P6 — Host release/update CLI proof

**Date:** 2026-09-03  
**Unit:** DEV-UNIT-01  
**Firmware:** unchanged (P5 OTAS transport frozen)

## Commands proven

| Command | Result |
|---------|--------|
| `python tools/mcxn.py doctor` | **DOCTOR PASS** (SDK, GCC 14.3, LinkServer 25.6.131, SEC 26.06.b260612, SPSDK 3.10.0, probe, ping, Hello/STATUS) |
| `python tools/mcxn.py package --unit DEV-UNIT-01 --version 2.0.0` | **PACKAGE OK** → `dist/DEV-UNIT-01/2.0.0/` |
| `python tools/mcxn.py release --unit DEV-UNIT-01 --version 2.0.0` | **RELEASE OK** (+ `README_TECHNICIAN.txt`) |
| `python tools/mcxn.py update` (window closed) | **FAIL** as designed (`update_window_s=0`) |
| `python tools/mcxn.py update --sb3 dist/.../DEV-UNIT-01_2.0.0_V2.sb3` after flash V1 | **UPDATE PASS** → STATUS V2 + Hello |
| `pytest tests/test_host_package_update.py` | **8 passed** |

## Package artefact (release)

| Field | Value |
|-------|-------|
| SB3 | `dist/DEV-UNIT-01/2.0.0/DEV-UNIT-01_2.0.0_V2.sb3` |
| SHA-256 | `54e01267785d7ae0af7f4e6a8ccfec2419d85432b96344f0286891f28ec618ef` |
| Bytes | 1196828 |
| UUID | `9DA8D48D0DDCD755903E8FBD3836C153` |
| Git commit (at package) | `3faac63a61ce185ace351027a75fba44f057b06e` |
| Secrets in dist/ | **none** (no pem/hex/key) |

## Tool versions (doctor)

- west 1.5.0  
- arm-none-eabi-gcc 14.3.1 (Arm GNU 14.3.Rel1)  
- SPSDK / nxpimage 3.10.0  
- SEC `securep` 26.06.b260612  
- LinkServer 25.6.131  

## Stop

P6 complete. **Do not start P7** until owner authorizes ROM-secure-boot hardening.
