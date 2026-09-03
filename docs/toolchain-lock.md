# Toolchain lock

**Recorded:** 2026-09-03 (P7 freeze — architecture frozen, no further security writes planned)  
**Plan baseline:** MCUXpresso SDK v26.06.00-LTS, SEC 26.06 / SPSDK 3.10.0, GCC 14.x family

| Tool | Version / path | Notes |
|------|----------------|-------|
| west | 1.5.0 | `python -m west` |
| arm-none-eabi-gcc | 14.3.1 20250623 (Arm GNU Toolchain 14.3.Rel1) | Plan 14.2.x family; 14.3.x accepted |
| cmake | 4.2.0-rc2 | |
| ninja | 1.13.0.git.kitware.jobserver-pipe-1 | |
| Python | 3.11.9 | |
| LinkServer | 25.6.131 | `C:\nxp\LinkServer_25.6.131` |
| SEC `securep.exe` | 26.06.b260612 | `C:\nxp\SEC_Provi_26.06\bin\securep.exe` |
| SPSDK / nxpimage | 3.10.0 | packaging via `nxpimage sb31 export` |
| imgtool | via SDK tree / SEC bundle | MCUboot sign |
| pytest | 9.x | `tests/test_host_package_update.py` |
| MCUXpresso SDK | `v26.06.00-LTS` @ `C:\mcxn\mcuxsdk-ws` | |

## Authoritative host CLI

```text
python tools/mcxn.py doctor|build|package|release|update|...
```

Config: `mcxn.toml`. Secrets: `C:\mcxn-secrets\`. Unit registry: `units/`.

## Deviations from early plan text

1. Host GCC is **14.3.x**, not 14.2.x.
2. Wire protocol is **OTAS** (P5), not draft `MCXNUP1`.
3. LinkServer **25.6.131** (not a 26.06-branded package).

## Frozen security state (post-P7)

ROM secure boot active: `SEC_BOOT_EN = ECDSA_SIGNED`, `ROTKH = 670EE45ABA…`.
CUST_MK_SK provisioned. Lifecycle = Develop. No further security writes in scope.
