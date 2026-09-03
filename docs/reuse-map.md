# Reuse map

| NXP source | SDK rev | Destination | Why | Changes |
|------------|---------|-------------|-----|---------|
| `examples/ota_examples/ota_mcuboot_server/enet` | 26.06.00-LTS | `firmware/app` via `west export_app` | FreeRTOS+lwIP+ENET+MCUboot app-support parent | Removed HTTPSRV; added hello/update/LED/diagnostics |
| `network_enet/init_enet.c` | same | `firmware/app/network_enet/` | Network bring-up | Include `app_config.h` first for IP policy |
| `examples/_boards/frdmmcxn947/ota_examples/ota_linker/mcxn10_cm33_flash.ld` | same | `firmware/app/linker/mcxn10_cm33_flash_standalone.ld` | Slot-compatible map | `MCUBOOT_HEADER_SIZE=0` for P2 standalone boot |
| `middleware/mcuboot_opensource/.../app_support` | same | linked via Kconfig | Image state APIs later | unchanged |
| `examples/ota_examples/_common/sb3_api` | same | `firmware/app` via CMake (`sb3_api_mcxn10.c`) | SB3 processing | unchanged NXP; TCP replaces XMODEM only |
| `components/silicon_id` (MCXN) | same | diagnostics | UUID | `SILICONID_GetID` |
| SPSDK `nxpimage sb31` | 3.10.0 | `tools/mcxn.py package/release` | Unit SB3 generation | Host wrapper only; keys stay in secrets |
| SDK `imgtool.py` | MCUboot in SDK | `tools/mcxn_lib` sign step | Slot image sign | unchanged NXP params; key = `paths.imgtool_key` (not IMG1_1) |
| `middleware/lwip/.../httpsrv_tls.c` BIO pattern | 26.06.00-LTS | `firmware/app/src/mtls_socket.c` | mbedTLS↔lwIP send/recv | No HTTPSRV; raw mTLS sockets only |
| `middleware/mbedtls3x` + PSA + ELS_PKC + thread_alt | 26.06.00-LTS | product `prj.conf` | TLS 1.2 mTLS | Project overlay; SDK sources untouched |
| Python `ssl` | host | `tools/mcxn_lib/mtls.py` | PC client mTLS + fingerprint pin | Secrets under `secrets_root/mtls/` |
