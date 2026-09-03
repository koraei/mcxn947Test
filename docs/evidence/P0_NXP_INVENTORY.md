# P0 — NXP inventory (SDK 26.06.00-LTS)

**Recorded:** 2026-09-03  
**SDK workspace:** `C:\mcxn\mcuxsdk-ws`  
**Manifest:** `v26.06.00-LTS` (`mcuxsdk-manifests` @ `b01ab903…`)  
**Board target string:** `-b frdmmcxn947 -Dcore_id=cm33_core0`

## Exact build / flash syntax (verified)

```powershell
$env:ARMGCC_DIR = 'C:\Program Files (x86)\Arm GNU Toolchain arm-none-eabi\14.3 rel1'
$env:Path = "C:\nxp\LinkServer_25.6.131;$env:ARMGCC_DIR\bin;$env:Path"
cd C:\mcxn\mcuxsdk-ws

python -m west build -b frdmmcxn947 -d C:\mcxn\builds\<name> `
  mcuxsdk/examples/<path> -Dcore_id=cm33_core0 --toolchain armgcc --config debug -p always

python -m west flash -d C:\mcxn\builds\<name> -r linkserver
```

LinkServer probe serial: `MNZW4VYTFX113`  
Direct flash alternative:

```text
LinkServer.exe flash -p MNZW4VYTFX113 MCXN947:FRDM-MCXN947 load <file.elf>
```

## Stock examples built (P0.5)

| Example | Source | Build dir | Result |
|---------|--------|-----------|--------|
| hello_world | `mcuxsdk/examples/demo_apps/hello_world` | `C:\mcxn\builds\hello_world` | **PASS** — UART: `hello world.` / SDK `2026.06.00` |
| freertos_hello | `mcuxsdk/examples/freertos_examples/freertos_hello` | `C:\mcxn\builds\freertos_hello` | **PASS** — UART: `Hello world.` |
| lwip_ping freertos | `mcuxsdk/examples/lwip_examples/lwip_ping/freertos` | `C:\mcxn\builds\lwip_ping_freertos` | **BUILD PASS / LINK FAIL** — see Ethernet gate |
| ota_mcuboot_server/enet | `mcuxsdk/examples/ota_examples/ota_mcuboot_server/enet` | `C:\mcxn\builds\ota_mcuboot_server_enet` | **BUILD PASS** (not run — needs Ethernet) |
| ota_mcuboot_basic | `mcuxsdk/examples/ota_examples/ota_mcuboot_basic` | `C:\mcxn\builds\ota_mcuboot_basic` | **BUILD PASS** (includes `sb3_api_mcxn10.c`, xmodem) |
| mcuboot_opensource | `mcuxsdk/examples/ota_examples/mcuboot_opensource` | `C:\mcxn\builds\mcuboot_opensource` | **BUILD PASS** — `m_text` 28008 B / 31 KiB (88.23%), fits IFR |

Evidence logs: `C:\mcxn\builds\*_build.log`, `C:\mcxn\builds\*_uart.txt`

## Flash layout (installed `flash_partitioning.h`)

Path: `mcuxsdk/examples/_boards/frdmmcxn947/ota_examples/mcuboot_opensource/flash_partitioning/flash_partitioning.h`

```text
Primary app     0x00000000 .. 0x000FFFFF   1 MiB   BOOT_FLASH_ACT_APP
Secondary app   0x00100000 .. 0x001FFFFF   1 MiB   BOOT_FLASH_CAND_APP
MCUboot IFR     0x01008000 .. 0x0100FFFF  32 KiB
```

Matches plan §1.2. Do **not** enable `CONFIG_MCXN_CUSTOM_CFG_MAIN_FLASH_ONLY`.

## Signing parameters (board README)

Path: `mcuxsdk/examples/_boards/frdmmcxn947/ota_examples/mcuboot_opensource/example_board_readme.md`

```text
imgtool sign --key sign-ecdsa-p256-priv.pem
             --align 16
             --version X.Y.Z
             --slot-size 0x100000
             --header-size 0x400
             --pad-header
             <in.bin> <out.SIGNED.bin>
```

First manually flashed image also needs `--pad --confirm`.  
ECDSA-P256, DIRECT_XIP, flash remap. Header 1024 B.

**imgtool path (use tree copy, not random pip):**  
`mcuxsdk/middleware/mcuboot_opensource/scripts/imgtool.py`

## Key source paths

| Item | Path |
|------|------|
| Board MCUboot `main.c` | `mcuxsdk/examples/_boards/frdmmcxn947/ota_examples/mcuboot_opensource/main.c` |
| Flash partitioning | `.../mcuboot_opensource/flash_partitioning/` |
| Board cmpa.bin (BOOT_SRC) | under same ota board folder (CMPA write is **gated**) |
| App-support API | `mcuxsdk/middleware/mcuboot_opensource/boot/nxp_mcux_sdk/app_support/mcuboot_app_support.c` (+ headers alongside) |
| ota_mcuboot_basic + xmodem | `mcuxsdk/examples/ota_examples/ota_mcuboot_basic/` (`xmodem.c`, shell `xmodem_sb3`) |
| Board bindings | `mcuxsdk/examples/_boards/frdmmcxn947/ota_examples/ota_mcuboot_basic/platform_bindings.c` |
| SB3 API (MCXN) | `mcuxsdk/examples/ota_examples/_common/sb3_api/sb3_api.h` + `sb3_api_mcxn10.c` |
| SB3 YAML templates | `mcuxsdk/examples/ota_examples/_common/sb3_templates/mcxn_sb3_cfg_primary_slot.yaml` (+ secondary if present) |
| SB3 docs | `mcuxsdk/examples/ota_examples/_doc/sb3_mcxn_readme.md`, `sb3_common_readme.md` |
| Flash remap docs | `mcuxsdk/examples/ota_examples/_doc/flash_remap_readme.md` |
| ENET init (OTA server) | `mcuxsdk/examples/ota_examples/ota_mcuboot_server/network_enet/init_enet.c` |
| lwIP / ENET port | `mcuxsdk/middleware/lwip/port/enet_ethernetif*.c` |
| UUID API | `mcuxsdk/devices/MCX/MCXN/MCXN947/drivers/romapi/flash/fsl_flash_ffr.h` → `FFR_GetUUID()` (16-byte UUID) |
| ENET HW notes | board `driver_examples/enet/*/example_board_readme.md`: **JP13=2-3**, **R274 populated** |

## SEC / SPSDK CLI

**Not installed on this PC.** Required for P4+:

- MCUXpresso Secure Provisioning Tool **26.06** (`securep.exe`) from https://nxp.com/sec  
- Prefer SPSDK **3.10.0** bundled with SEC (do not mix random pip SPSDK with SEC workspaces)

## Ethernet hardware gate (blocks P0 exit)

Stock `lwip_ping_freertos` after flash (UART evidence `C:\mcxn\builds\lwip_ping_uart.txt`):

```text
Initializing PHY...
PHY Auto-negotiation failed. Please check the cable connection and link partner setting.
```

Host NICs: onboard `Intel I219-LM` = **Disconnected**; `Realtek USB GbE` = **Disconnected**.  
Agent cannot visually confirm JP13/R274. Per plan §1.5 / P0.2: **stop — do not modify ENET driver**.

## Gated operations noted for later phases

From board MCUboot README — **owner approval required** before:

1. CMPA write (`BOOT_CFG.BOOT_SRC = 0b10`) via ISP/`blhost` + attached `cmpa.bin`
2. IFR erase/program at `0x01008000`
3. Any `CUST_MK_SK` / device-HSM provisioning (P4)
