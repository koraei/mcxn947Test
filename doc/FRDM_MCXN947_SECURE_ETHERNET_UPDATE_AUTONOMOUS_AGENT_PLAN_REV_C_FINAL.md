# FRDM-MCXN947 Secure Ethernet Firmware Update Prototype
## Autonomous Cursor-Agent Implementation Plan — Rev C FINAL

**Target:** NXP FRDM-MCXN947 / MCXN947VDF connected to the development PC by MCU-Link USB and Ethernet  
**Host:** Windows + Cursor, CLI-first; no dependency on MCUXpresso IDE  
**RTOS/network:** NXP MCUXpresso SDK FreeRTOS + lwIP  
**Boot/update baseline:** NXP `mcuboot_opensource` default FRDM-MCXN947 layout + NXP SB3.1 processing  
**Update transport:** product TCP service during first 180 s of application runtime  
**Normal TCP service:** `Hello MCXN` → `Hello PC!` continuously during normal operation  
**Security objective:** signed application, encrypted/authenticated field package, package generated for the provisioned target unit, ROM/MCUboot chain kept recoverable during development  
**SDK baseline:** **MCUXpresso SDK v26.06.00-LTS**  
**Secure Provisioning Tool baseline:** **MCUXpresso Secure Provisioning Tool 26.06**, which integrates **SPSDK 3.10.0**  
**Status:** FINAL execution authority for the prototype

---

# 0. Final architecture decision

This revision is intentionally smaller than Rev B. The objective is to demonstrate the requested product behavior with the **least custom security code** and the **maximum reuse of NXP-supported components**.

## 0.1 What we will build

1. FRDM-MCXN947 application on **FreeRTOS + lwIP**.
2. Two application versions:
   - **V1:** green LED, slow blink.
   - **V2:** blue LED, fast blink.
3. NXP MCUboot is visibly active during reset by holding one LED steadily ON for a short development-only interval.
4. Normal TCP server:
   - PC sends `Hello MCXN\n`.
   - Board replies `Hello PC!\n`.
5. Secure-update TCP server:
   - available only during the first **180 s** after the application starts;
   - a session accepted before the deadline may finish afterward;
   - no new update sessions are accepted after the deadline.
6. Firmware application is signed using the NXP MCUboot workflow.
7. The field update is delivered as an **NXP SB3.1 secure binary**.
8. Each physical unit is provisioned with its own random **`CUST_MK_SK`** as our fleet policy; the release tool uses the corresponding unit workspace/key material to generate its SB3 package.
9. The PC also checks the MCU UUID before transfer to prevent operator mistakes.
10. The final prototype uses NXP ROM/MCUboot/security tooling as much as possible; there is no product-written encryption algorithm, image parser, or secure-container format.

## 0.2 What we deliberately do NOT implement in the critical path

The following are excluded because they do not prove the requested feature and add time/risk:

- NPX/PRINCE encrypted-XIP;
- MCUboot image-level ECIES encryption;
- custom signed UUID TLVs;
- TLS/mTLS on the 180-s update port;
- automatic application-health rollback/revert;
- custom anti-replay/package-consumption counters;
- firmware anti-rollback monotonic counters;
- licensing;
- lifecycle transition to In-Field/OEM closed;
- debug lockout/authentication;
- second Cortex-M33 application;
- EdgeLock 2GO/cloud provisioning;
- custom CBOR/COSE/FWPKG format;
- custom cryptographic libraries.

These are future product-hardening features only if separately required.

## 0.3 Important reliability statement

NXP's MCXN flash-remap implementation uses MCUboot `DIRECT_XIP` and selects the image with the highest version. NXP explicitly documents that this mode has **no rollback support**. Therefore this prototype shall **not claim automatic revert to the previous application after a successfully authenticated but unhealthy firmware boots**.

For this prototype, the guarantees are:

- invalidly signed inner application does not execute;
- invalid/corrupted/wrong-key SB3 is rejected;
- an interrupted transfer does not mark an image ready for boot;
- the currently executing image remains the known-good image until a complete valid candidate has been installed and explicitly marked using NXP's API;
- recovery through MCU-Link/ISP remains available in the Develop lifecycle.

If Portenta-style automatic health rollback later becomes mandatory, it is a separate architecture task. Do not spend prototype time experimenting with unsupported or undocumented DIRECT_XIP revert behavior.

---

# 1. NXP facts this plan is based on

The AI agent must verify these facts against the **installed 26.06.00-LTS tree** before depending on exact file names or build symbols.

## 1.1 SDK and tools

Use:

- MCUXpresso SDK `v26.06.00-LTS`;
- release branch `release/26.06.00`;
- GCC Arm Embedded Toolchain 14.2.x family;
- MCUXpresso for VS Code v26.06 where available;
- LinkServer / MCU-Link;
- MCUXpresso Secure Provisioning Tool 26.06;
- SPSDK **3.10.0**, preferably the instance integrated with SEC 26.06;
- `west`, CMake, Ninja, Python, Git.

Do not mix a random pip-installed SPSDK with SEC-generated workspaces unless compatibility is first proven and recorded.

## 1.2 FRDM-MCXN947 default NXP MCUboot layout

NXP's default FRDM-MCXN947 MCUboot configuration uses:

```text
MCUboot                0x0100_8000 .. 0x0100_FFFF   32 KiB IFR
Primary application    0x0000_0000 .. 0x000F_FFFF    1 MiB
Secondary application  0x0010_0000 .. 0x001F_FFFF    1 MiB
```

NXP documents:

- ECDSA-P256 signing;
- 16-byte flash write alignment;
- 1024-byte MCUboot header;
- `DIRECT_XIP`;
- MCXN internal-flash SWAP/remap hardware for zero-copy image activation.

Use this layout unchanged unless the installed reference example proves a required deviation.

## 1.3 SB3.1 OTA support

NXP provides SB3 processing on FRDM-MCXN947 through the `ota_mcuboot_basic` example. The documented flow is:

1. build application;
2. sign application with MCUboot `imgtool`;
3. create MCXN SB3 using the NXP template/SEC workspace;
4. transfer SB3 to the MCU;
5. NXP secure-binary processing writes the inactive image slot;
6. mark the installed image as ready/test using NXP's MCUboot application-support API;
7. reboot;
8. accept the new image state using the NXP application-support API when desired.

The NXP example uses `xmodem_sb3`. Our only transport change is replacing the XMODEM byte source with a bounded TCP byte source.

## 1.4 `CUST_MK_SK`

NXP Secure Provisioning Tool defines `CUST_MK_SK` as the customer key used by SB secure-binary processing. The NXP MCXN SB3 workflow generates/provisions it through the NXP device-HSM provisioning flow.

**Our fleet rule:** every physical production unit receives a different random `CUST_MK_SK` and a separate SEC workspace/secret backup.

This gives the prototype its per-unit secure-update binding policy without a custom package format.

Mandatory evidence:

- package created with the correct unit workspace/key succeeds;
- package created using a different random `CUST_MK_SK` fails on that unit.

Do not merely assume the binding property; demonstrate it on hardware.

## 1.5 Ethernet board prerequisite

Before debugging any Ethernet software, inspect the FRDM-MCXN947 board according to the NXP ENET example:

```text
JP13 = 2-3
R274 = populated
```

If this is not true, stop and report a hardware prerequisite rather than modifying the network driver.

## 1.6 NXP Ethernet software baseline

FRDM-MCXN947 is supported by NXP with:

```text
FreeRTOS
  + lwIP
  + NXP ENET driver
  + LAN8741 PHY support
```

Reuse the NXP board initialization, ENET, PHY, lwIP and FreeRTOS configuration from the closest current Ethernet/OTA example. Do not recreate clock, PHY, DMA or lwIP integration from scratch.

---

# 2. Architecture

```text
                        DEVELOPMENT / RELEASE PC

 Cursor
   |
   +-- MCUXpresso SDK 26.06 LTS
   +-- west + CMake + Ninja + GCC 14.2.x
   +-- NXP imgtool
   +-- NXP SEC 26.06 / SPSDK 3.10.0
   +-- LinkServer
   +-- thin product CLI: mcxn
   +-- per-unit registry + external secret workspace
   |
   +---------------------------- Ethernet -----------------------------+
                                                                        |
                                  FRDM-MCXN947                           |
                                  ====================================  |
                                  NXP ROM                               |
                                     |                                  |
                                  MCUboot                               |
                                  IFR @ 0x01008000                      |
                                  steady boot LED                       |
                                  ECDSA-P256 verify                     |
                                  DIRECT_XIP / flash remap              |
                                     |                                  |
                             FreeRTOS + lwIP application                |
                                  /             \                       |
                         TCP normal          TCP update                  |
                         port 5000           port 5555                   |
                         always on           first 180 s                 |
                           |                   |                         |
                    Hello MCXN            thin TCP adapter              |
                       ->                  around NXP SB3                |
                    Hello PC!                  |                         |
                                         NXP SB3 processing             |
                                              |                         |
                                      inactive 1 MiB slot               |
                                              |                         |
                                      mark image ready                  |
                                              |                         |
                                           reset                        |
                                              |                         |
                                         MCUboot select                 |
```

## 2.1 NXP-owned code

Reuse without redesign:

- startup and device definitions;
- board clocks/pinmux where applicable;
- ENET and LAN8741 PHY drivers;
- FreeRTOS;
- lwIP;
- MCUboot fork;
- MCUboot image headers/trailers;
- ECDSA-P256 image verification;
- flash partitioning/remap backend;
- MCUboot application-support API;
- SB3 secure-binary processing implementation;
- Secure Provisioning Tool/device-HSM provisioning;
- SPSDK/nxpimage tooling;
- LinkServer/MCU-Link programming/debug.

## 2.2 Product-owned code

Only:

- LED task / variant settings;
- normal hello TCP service;
- 180-s update listener;
- small TCP-to-NXP-SB3 input adapter;
- status/diagnostic counters;
- minimal PC wrapper CLI;
- tests and documentation.

The goal is to keep new firmware code small and auditable.

---

# 3. Required behavior

## 3.1 Application V1

```text
version        1.0.0
LED            green
period         1000 ms
ON             500 ms
OFF            500 ms
```

## 3.2 Application V2

```text
version        2.0.0
LED            blue
period         250 ms
ON             125 ms
OFF            125 ms
```

Both color and speed differ so the new image is obvious.

## 3.3 MCUboot LED

During MCUboot:

- use one simple board LED, preferably red, steadily ON;
- development build may hold it ON for ~300-400 ms so a human can see the boot stage;
- production-like build removes the artificial delay;
- application first turns the boot LED OFF, then starts its own pattern.

Do not add animation or extra bootloader features.

## 3.4 Normal socket

Default:

```text
TCP port 5000
```

Protocol:

```text
PC      -> Hello MCXN\n
DEVICE  -> Hello PC!\n
```

Optional diagnostic request only if trivial:

```text
PC      -> STATUS\n
DEVICE  -> STATUS version=1.0.0 variant=V1 uuid=<hex> uptime_s=<n> update_window_s=<n>\n
```

Constraints:

- max request 128 B;
- receive timeout <= 5 s;
- one request per connection;
- malformed request -> `ERR\n` and close;
- always close socket on every exit path;
- must continue working indefinitely after the OTA listener closes.

## 3.5 Update window

Default:

```text
TCP port 5555
window = first 180 s after application runtime starts
```

Rules:

1. Window start = application/RTOS start, not first network connection.
2. If Ethernet becomes ready at t=10 s, only 170 s remain.
3. New sessions are rejected/port closed at 180 s.
4. A session whose valid start handshake was accepted before 180 s may finish after 180 s.
5. Idle/slow clients have short inactivity timeouts so they cannot reserve the session indefinitely.
6. If a session fails before the deadline, listener may reopen while time remains.
7. After the deadline, the update task terminates and cannot reopen until next reboot.

## 3.6 Minimal update transport protocol

Do **not** create another security envelope.

Recommended application framing:

```text
PC      -> MCXNUP1 <uuid32hex> <length_decimal>\n
DEVICE  -> READY\n
PC      -> exactly <length> bytes of SB3.1
DEVICE  -> OK\n
```

or:

```text
DEVICE -> ERR <code>\n
```

Purpose of this header:

- prevent accidental wrong-device transfer;
- bound file length;
- provide protocol versioning.

It is **not** the cryptographic authorization layer.

Do not add:

- custom signature;
- custom AES;
- custom CRC;
- custom SHA requirement;
- JSON/CBOR parser;
- TLS.

TCP gives transport integrity/retransmission; SB3 gives the secure firmware authentication/confidentiality property.

---

# 4. Repository structure

Keep it simple:

```text
mcxn947-secure-ota/
├── README.md
├── mcxn.toml
├── firmware/
│   ├── app/
│   │   ├── src/
│   │   │   ├── main.c
│   │   │   ├── led_task.c
│   │   │   ├── hello_service.c
│   │   │   ├── update_service.c
│   │   │   └── diagnostics.c
│   │   ├── inc/
│   │   ├── board/
│   │   └── variants/
│   │       ├── v1.conf
│   │       └── v2.conf
│   └── mcuboot_overlay/
│       ├── README.md
│       └── minimum board override/patch required for steady LED
├── tools/
│   └── mcxn.py
├── tests/
│   ├── host/
│   └── hw/
├── docs/
│   ├── FINAL_PLAN.md
│   ├── dev-log.md
│   ├── toolchain-lock.md
│   ├── reuse-map.md
│   ├── architecture.md
│   ├── security-design.md
│   ├── device-state.md
│   ├── adr/
│   ├── runbooks/
│   │   ├── provision.md
│   │   ├── release.md
│   │   └── recover.md
│   └── evidence/
├── dist/           # gitignored
├── build/          # gitignored
└── .gitignore
```

Do not build an elaborate Python package hierarchy until one file becomes genuinely difficult to maintain.

---

# 5. Cursor and development tools

## 5.1 Required tools

Install/check:

- Cursor;
- official **MCUXpresso for VS Code v26.06** extension if Cursor can install or side-load it;
- MCUXpresso Installer / SDK Developer dependencies;
- Git;
- Python;
- west;
- CMake;
- Ninja;
- GCC Arm Embedded 14.2.x;
- LinkServer;
- MCUXpresso Secure Provisioning Tool 26.06;
- pyserial;
- pytest.

Useful optional Cursor extensions only:

- Python;
- clangd;
- YAML;
- CMake Tools;
- Markdown/Mermaid.

Do not spend time building an IDE-centric workflow. CLI is authoritative.

## 5.2 CLI rule

The following must work from a normal terminal:

```text
west build ...
west flash -r linkserver ...       # where supported by the example
LinkServer ...                     # fallback/direct operations
imgtool.py ...
securep.exe ...
nxpimage ...                       # only through pinned SEC/SPSDK environment
python tools/mcxn.py ...
pytest ...
```

## 5.3 Pinning

Preferred SDK setup:

```powershell
west init -m https://github.com/nxp-mcuxpresso/mcuxsdk-manifests.git --mr v26.06.00-LTS C:\mcxn\mcuxsdk-ws
cd C:\mcxn\mcuxsdk-ws
west update
```

If the installed NXP documentation recommends a different exact command for 26.06, follow the installed documentation and record it.

Capture versions to `docs/toolchain-lock.md`:

```text
west
arm-none-eabi-gcc
cmake
ninja
LinkServer
securep
SPSDK/nxpimage
Python
MCUXpresso SDK git revisions
```

---

# 6. Safety and autonomy rules

## 6.1 Agent may do autonomously

- install ordinary software/extensions;
- clone/pin SDK;
- build examples/product code;
- flash ordinary application regions;
- flash/reflash MCUboot when using an already-approved board configuration;
- reset/reboot board;
- read UART/network output;
- run tests;
- generate development signing keys in an external/gitignored secret directory;
- generate SB3 packages after the NXP provisioning workspace exists;
- edit/commit source/docs;
- read CMPA/CFPA/security state.

## 6.2 Owner approval required before

- first CMPA write;
- first BOOT_SRC change;
- first `CUST_MK_SK` provisioning;
- any CFPA write;
- ROM secure-boot enablement if not already part of the approved SEC workflow;
- lifecycle change;
- debug lock/disable;
- fuse/monotonic-counter programming;
- NPX/PRINCE configuration;
- mass erase after security provisioning.

The agent must prepare a short gate request containing:

- board UUID;
- exact command/script;
- current state backup;
- expected state;
- recovery procedure.

## 6.3 Secrets

Never commit:

- private MCUboot signing key;
- `CUST_MK_SK`;
- OEM SB seed;
- device-HSM secrets;
- ROM root signing private keys;
- full SEC secret workspace.

Recommended external path:

```text
C:\mcxn-secrets\DEV-UNIT-01\
```

Git stores only:

- unit UUID;
- public keys;
- key fingerprints;
- workspace fingerprint/hash;
- artifact hashes;
- non-secret release metadata.

---

# 7. Phase P0 — preflight and unchanged NXP examples

## Goal

Prove hardware and NXP baseline before custom development.

## P0.1 Board discovery

Detect:

- MCU-Link probe;
- VCOM port;
- board/device identity;
- installed LinkServer.

Record in `docs/device-state.md`.

## P0.2 Ethernet hardware

Verify physically:

```text
JP13 = 2-3
R274 = populated
```

Stop if not satisfied.

## P0.3 Tool installation

Install Section 5 tools.

## P0.4 SDK pin

Pin `v26.06.00-LTS`.

## P0.5 Build/flash NXP stock examples

At minimum:

1. `hello_world`;
2. `freertos_hello`;
3. FRDM-MCXN947 Ethernet/lwIP example;
4. `ota_mcuboot_server/enet` or closest 26.06 Ethernet OTA example;
5. `ota_mcuboot_basic` with SB3 command support;
6. default `mcuboot_opensource` FRDM-MCXN947 configuration.

Do not edit these examples during this phase.

## P0.6 Inventory exact NXP APIs

Before custom code, locate in installed sources:

- default FRDM-MCXN947 MCUboot partition header;
- board MCUboot `main.c`;
- app-support API to inspect/mark image state;
- source of `xmodem_sb3`;
- shared `sb3_api`/processing functions;
- SB3 MCXN template;
- ENET/lwIP initialization code;
- UUID API (`FFR_GetUUID` or installed equivalent);
- exact `west` build syntax;
- exact LinkServer flash syntax;
- exact SEC workspace/build/provision CLI syntax.

Write:

```text
docs/evidence/P0_NXP_INVENTORY.md
```

## P0 exit

Do not continue until:

- FreeRTOS stock app runs;
- Ethernet stock example works;
- MCUboot builds;
- SB3-enabled OTA basic builds;
- all exact source paths are known.

---

# 8. Phase P1 — thin project/CLI foundation

## Goal

Make repeated agent operations deterministic without overengineering.

## P1.1 Create repository

Use Section 4 structure.

## P1.2 Minimal `mcxn.py`

Initial commands:

```text
python tools/mcxn.py doctor
python tools/mcxn.py build v1
python tools/mcxn.py build v2
python tools/mcxn.py build mcuboot
python tools/mcxn.py flash <target>
python tools/mcxn.py serial --seconds 10
python tools/mcxn.py hello
python tools/mcxn.py status
```

Later add:

```text
python tools/mcxn.py package --unit DEV-UNIT-01 --version 2.0.0
python tools/mcxn.py update <file.sb>
python tools/mcxn.py test
```

Do not duplicate NXP functionality. `mcxn.py` should invoke NXP commands and handle logs/preflight checks.

## P1.3 Documentation skeleton

Create:

- `dev-log.md`;
- `toolchain-lock.md`;
- `reuse-map.md`;
- `architecture.md`;
- `security-design.md`;
- `runbooks/recover.md`.

## P1 exit

`doctor` reports:

- SDK/tag;
- compiler;
- LinkServer probe;
- COM port;
- unit UUID if available;
- board IP reachability.

---

# 9. Phase P2 — FreeRTOS V1/V2 and normal Ethernet socket

## Goal

Finish all non-security application behavior first.

## P2.1 Parent example

Use NXP's **Ethernet/OTA server example** as the main application skeleton because it already proves:

- FreeRTOS;
- lwIP;
- ENET;
- PHY;
- board network setup;
- MCUboot app-support linkage where available.

Remove/ignore HTTP functionality not required by this product. Do not retain a web server merely because the example has one.

## P2.2 Variant configuration

Compile-time configuration only:

```text
V1 -> 1.0.0, green, 500/500 ms
V2 -> 2.0.0, blue, 125/125 ms
```

## P2.3 LED task

- low priority;
- `vTaskDelay`/`vTaskDelayUntil`;
- no busy loops;
- first action turns bootloader LED OFF.

## P2.4 Hello service

Use lwIP socket API exactly as available in NXP's stack.

Server state machine:

```text
CREATE
BIND
LISTEN
ACCEPT
RECV with timeout
REPLY
CLOSE client
repeat
```

A connection/network failure must not stop the task permanently.

## P2.5 Identity/status

Read UUID through NXP FFR API and publish it through UART/status.

## P2.6 Basic recovery

Verify:

- unplug/replug Ethernet cable;
- kill/restart PC client;
- client connects then sends nothing;
- invalid greeting.

No board reset should be required.

## P2 acceptance

- V1 and V2 build from CLI;
- human sees distinct LED behavior;
- `Hello MCXN` -> `Hello PC!`;
- UUID is stable;
- Ethernet recovers after cable reconnect.

---

# 10. Phase P3 — NXP default MCUboot and signed images

## Goal

Use the exact NXP boot architecture before any SB3 work.

## P3.1 Default layout only

Use:

```text
IFR MCUboot: 0x01008000, 32 KiB
slot 0:      0x00000000, 1 MiB
slot 1:      0x00100000, 1 MiB
```

Do not switch to the alternative main-flash MCUboot configuration.

## P3.2 Boot source configuration

The default NXP example requires ROM boot source configuration to start MCUboot from IFR.

Before first write:

1. read/backup CMPA and CFPA;
2. prove ISP connection;
3. save NXP-provided recovery commands;
4. request owner approval.

Use the exact NXP-generated/reference CMPA workflow. Do not manually patch binary CMPA fields.

## P3.3 Boot LED

Make the smallest possible board overlay/patch:

```text
initialize one LED
turn it ON
optional dev-only 300-400 ms hold
continue into sbl_boot_main()
```

No other MCUboot behavior changes.

## P3.4 Inner image signing

Use the `imgtool.py` inside the pinned NXP MCUboot tree.

Use the **exact parameters printed in the installed FRDM-MCXN947 example**. Expected shape:

```text
--align 16
--slot-size 0x100000
--header-size 0x400
--pad-header
--version X.Y.Z
```

Initial directly flashed image follows the NXP documented initial-image `--pad --confirm` form.

Do not use MCUboot `-E` image encryption.

## P3.5 Negative signature test

Build/sign a candidate with a different signing key.

Expected:

- candidate does not execute;
- current valid application remains available.

## P3 acceptance

- reset visibly shows steady boot LED then V1/V2 app;
- valid signed app boots;
- wrong-signer app does not boot;
- slot addresses match NXP reference;
- modified MCUboot still fits completely inside the NXP 32 KiB IFR region; inspect the map/binary size and fail the phase if it overflows.

---

# 11. Phase P4 — NXP SB3.1 over the stock XMODEM path

## Goal

Prove **NXP provisioning + NXP SB3** before touching Ethernet transport.

This isolation step is mandatory.

## P4.1 SEC workspace

Use MCUXpresso Secure Provisioning Tool 26.06.

Create one workspace for:

```text
DEV-UNIT-01
```

Keep lifecycle:

```text
Develop
```

Use NXP's MCXN + MCUboot profile/workflow matching the selected IFR bootloader.

Generate:

- required authentication/PKI material;
- a random `CUST_MK_SK`;
- OEM SB seed;
- NXP generated device-HSM provisioning artifacts/scripts.

Back up the complete secret workspace externally.

## P4.2 SEC CLI first

Use `securep.exe` whenever possible.

Recommended process:

1. configure workspace;
2. use `--script-only` where supported;
3. inspect generated NXP script/log;
4. only then execute the provisioning action after gate approval.

Do not rewrite the device-HSM provisioning procedure in Python.

## P4.3 Provision target

Gated.

Do not:

- close lifecycle;
- lock debug;
- configure NPX;
- program rollback counters;
- burn unrelated fuses.

## P4.4 Generate signed V2

Build V2 and sign it with NXP MCUboot imgtool.

## P4.5 Generate SB3.1

Start from the **NXP MCXN SB3 template** in the installed OTA example tree / SEC SB Editor.

Do not create SB3 YAML from memory.

The package must target the inactive slot according to NXP's current flash-remap workflow.

## P4.6 Stock XMODEM proof

Use NXP `ota_mcuboot_basic` and its documented:

```text
xmodem_sb3
```

workflow.

Expected:

- valid SB3 is processed;
- candidate appears in inactive slot;
- use NXP `image`/app-support command to mark ready/test;
- reboot runs the new image.

## P4.7 Wrong-key proof

Create a **separate test SEC workspace/key set** with a different random `CUST_MK_SK`.

Generate an otherwise valid SB3 package with that wrong unit key.

Send through the same stock XMODEM path.

Expected:

- SB3 processing/authentication fails;
- no executable candidate is selected;
- current application remains usable.

This is mandatory evidence for the unit-bound update claim.

## P4 exit

Do not start Ethernet SB3 work unless:

- correct-key SB3 succeeds over NXP stock path;
- wrong-key SB3 fails;
- SEC workspace backup is proven;
- recovery via ISP/MCU-Link is proven.

---

# 12. Phase P5 — TCP transport for NXP SB3 + 180-s window

## Goal

Change only the transport, not the secure-binary engine.

## P5.1 Parent application

Start from the working P2 Ethernet app.

Import/reuse only the minimum NXP SB3 processing code/interface used by `ota_mcuboot_basic`.

Record the source mapping in `docs/reuse-map.md`.

## P5.2 First task before coding

Trace the installed `xmodem_sb3` call graph:

```text
shell command
 -> XMODEM receive
 -> SB3 init
 -> SB3 feed/process block(s)
 -> SB3 finalization/result
```

Write:

```text
docs/evidence/P5_SB3_CALL_GRAPH.md
```

The product code shall call the same SB3 processing layer in the same sequence.

## P5.3 Update listener task

Implement:

```text
WAIT_NETWORK
LISTEN
ACCEPT_HEADER
RECEIVE_SB3
PROCESS
MARK_READY
RESPOND
RESET
```

Only this task may call the NXP SB3 interface.

## P5.4 Window implementation

Use a monotonic RTOS tick deadline.

Do not reset the 180-s window on:

- cable reconnect;
- failed client;
- socket retry;
- DHCP retry.

## P5.5 Stream adapter

The custom adapter may only perform:

- `recv()` with finite timeout;
- buffer management;
- exact length accounting;
- feeding received bytes/blocks to NXP SB3;
- mapping NXP return codes to simple product errors.

It shall **not**:

- decrypt;
- parse cryptographic SB3 structures itself;
- derive keys;
- verify signatures itself;
- write arbitrary flash addresses itself.

## P5.6 Candidate activation

Only after NXP SB3 reports success:

1. inspect the candidate through NXP MCUboot application-support API;
2. verify expected image/version is visible;
3. use NXP API to mark it ready/test;
4. send `OK` to PC;
5. wait a short bounded interval for TCP flush;
6. reset.

Do not manually modify MCUboot trailer/state bytes.

## P5.7 Failure behavior

On any failure:

- do not mark image ready;
- close connection;
- retain current running image;
- publish error counter/code;
- reopen listener only if deadline has not expired.

## P5 acceptance matrix

### Valid package at t=30 s

Expected: update succeeds and V2 boots.

### New connection at t>180 s

Expected: port closed/refused; Hello service still works.

### Valid session starts at ~175 s

Expected: session may finish after 180 s.

### PC disconnect halfway

Expected: no image marked ready; current image continues/boots.

### Reset halfway

Expected: incomplete candidate does not execute.

### Wrong-key SB3 over TCP

Expected: NXP SB3 rejects; current app remains valid.

### Corrupted SB3

Expected: NXP SB3 rejects; current app remains valid.

---

# 13. Phase P6 — minimal host release/update tool

## Goal

Make Cursor able to perform the full workflow reproducibly.

## P6.1 Unit registry

Committed non-secret JSON/YAML:

```json
{
  "unit_name": "DEV-UNIT-01",
  "mcu_uuid": "...",
  "board": "frdmmcxn947",
  "sdk": "26.06.00-LTS",
  "ip": "192.168.0.102",
  "hello_port": 5000,
  "update_port": 5555,
  "sec_workspace_fingerprint": "...",
  "cust_mk_sk_fingerprint": "..."
}
```

Never store the actual secret.

## P6.2 Package sidecar

For every generated `.sb`/SB3 file create non-secret metadata:

```json
{
  "unit_name": "DEV-UNIT-01",
  "target_uuid": "...",
  "firmware_version": "2.0.0",
  "variant": "V2",
  "signed_image_sha256": "...",
  "sb3_sha256": "...",
  "sb3_bytes": 123456,
  "git_commit": "...",
  "toolchain_lock": "..."
}
```

The sidecar is an operator/release aid, not a device security object.

## P6.3 `mcxn.py package`

The wrapper shall:

1. select target unit;
2. build desired variant;
3. sign using NXP imgtool;
4. invoke the **unit's existing NXP SEC/SPSDK SB3 configuration/workspace**;
5. emit SB3 + sidecar;
6. record hashes and NXP command log.

Do not reimplement SB3 generation.

## P6.4 `mcxn.py update`

The wrapper shall:

1. read sidecar;
2. query live device UUID/status;
3. refuse if UUID differs;
4. verify local SB3 file hash/length against sidecar;
5. verify update window open;
6. connect update socket;
7. send `MCXNUP1` header;
8. wait for `READY`;
9. stream exact SB3 bytes;
10. wait for `OK`/error;
11. monitor reset/reconnect;
12. verify expected version and Hello service;
13. save evidence.

A test-only override may bypass host UUID checking so wrong-unit security tests can prove that device SB3 security, not the host check, is the true security boundary.

## P6 exit

One command can perform:

```text
build -> sign -> unit-specific SB3 -> Ethernet update -> verify new version
```

with no IDE interaction.

---

# 14. Phase P7 — ROM-authenticated MCUboot (production-shaped hardening)

## Why this exists

The functional SB3/MCUboot OTA demo can be proven before ROM secure boot. However, before describing the design as a **secure boot chain**, MCUboot itself must be authenticated by the immutable NXP ROM security mechanism.

This phase is required for a production-shaped security demo, but it is **not allowed to block P0-P6**.

## P7.1 Use NXP SEC workflow only

Use MCUXpresso Secure Provisioning Tool 26.06 and the current NXP MCX N secure-boot workflow (including AN14148/current installed documentation).

Do not hand-compose:

- RoT hashes;
- certificate blocks;
- CMPA binary structures;
- device-HSM provisioning.

## P7.2 Keep lifecycle Develop

For this prototype:

- no lifecycle closure;
- no debug disable;
- no fuse lock;
- no NPX;
- no anti-rollback counter.

## P7.3 Gate and recovery

Before execution:

- backup CMPA/CFPA;
- backup full SEC workspace;
- verify ISP recovery;
- preserve known-good signed MCUboot artifact;
- owner approves exact NXP-generated script.

## P7.4 Negative test

After ROM secure boot is proven:

1. deliberately corrupt MCUboot artifact;
2. verify ROM does not execute it;
3. recover through documented NXP recovery path;
4. restore valid MCUboot;
5. rerun one Ethernet SB3 update.

## P7 exit

Only after this phase may documentation say:

> The boot chain begins at NXP ROM, authenticates MCUboot, and MCUboot authenticates the application; field updates use NXP SB3 secure-binary processing with per-unit provisioning policy.

---

# 15. Prototype acceptance tests

Keep tests proportionate to this task.

## 15.1 Functional

- V1 boots and green slow blink is visible.
- V2 boots and blue fast blink is visible.
- MCUboot LED is steady during boot.
- Hello works before and after the 180-s update window.
- STATUS/UUID stable.

## 15.2 Security

- wrong MCUboot image signing key rejected;
- corrupted SB3 rejected;
- wrong `CUST_MK_SK` SB3 rejected;
- host refuses wrong UUID sidecar by default;
- host UUID check bypassed in a test does not make wrong-key SB3 succeed;
- incomplete transfer never marks candidate ready;
- P7 only: corrupted MCUboot rejected by ROM.

## 15.3 180-s behavior

- update at t<180 accepted;
- new session t>180 rejected;
- session accepted around t=175 completes after deadline;
- failed session before deadline may retry;
- failed session after deadline does not reopen port.

## 15.4 Ethernet/reliability smoke

Automate at least:

```text
10,000 Hello connect/request/reply/close cycles
20 cable down/up cycles
100 client-process kill/restart cycles
20 board reboot cycles
```

Monitor at minimum:

```text
hello_accept_count
hello_error_count
update_accept_count
update_success_count
update_failure_count
sb3_failure_count
link_down_count
free_heap
minimum_free_heap
hello_task_stack_high_water
update_task_stack_high_water
```

Acceptance:

- no leak-like monotonic resource decline;
- no task death;
- network service recovers without board reset after ordinary cable/client faults.

This is prototype qualification, not the final one-year product reliability campaign.

---

# 16. Recovery runbook — mandatory before security provisioning

`docs/runbooks/recover.md` must be completed before the first `CUST_MK_SK`/secure configuration write.

Include:

1. Board MCU-Link serial and MCU UUID.
2. Physical ISP-entry procedure.
3. UART/USB ISP connection commands.
4. How to read/backup CMPA/CFPA.
5. How to restore NXP boot-source configuration.
6. How to restore known-good IFR MCUboot.
7. How to restore initial signed V1.
8. Where the SEC workspace backup is stored.
9. Consequence of losing `CUST_MK_SK`/workspace backup.
10. Which operations are deliberately not performed in this prototype.

A recovery procedure that has never been executed is not considered proven.

---

# 17. Documentation requirements — lean version

Do not create documentation for its own sake. Maintain only:

## 17.1 `docs/dev-log.md`

At each phase:

- date;
- git commit;
- commands run;
- evidence paths;
- deviations;
- next step.

## 17.2 `docs/reuse-map.md`

For every NXP file copied/overridden:

```text
NXP source path
SDK revision
our destination
why copied
what changed
```

## 17.3 ADRs

Only these are mandatory:

### ADR-001 — FreeRTOS + lwIP + NXP ENET

### ADR-002 — NXP default IFR MCUboot / DIRECT_XIP flash remap

### ADR-003 — NXP SB3.1 + unique per-unit CUST_MK_SK fleet policy

### ADR-004 — 180-second application-layer Ethernet update service

### ADR-005 — ROM secure boot outcome after P7

Do not create ADRs for trivial implementation details.

## 17.4 `docs/security-design.md`

Must explicitly distinguish:

- MCUboot image signature;
- SB3 confidentiality/authentication;
- per-unit `CUST_MK_SK` policy;
- UUID host check;
- what is not protected in Develop/debug-open state;
- no automatic rollback claim.

---

# 18. AI-agent execution rules

1. **NXP example first.** Never start custom implementation before the equivalent NXP example works.
2. **One unknown at a time.** Do not debug TCP and SB3 simultaneously; stock SB3 must pass first.
3. **No custom crypto.** If code starts implementing AES/ECDSA/SB3 parsing, stop: the architecture has drifted.
4. **No SDK edits.** Upstream SDK checkout stays clean; use overlays/copies/project files.
5. **Use exact installed docs.** If plan command differs from SDK 26.06 reality, installed NXP source wins and the deviation is logged.
6. **Do not guess flash/security fields.** Use NXP SEC/generated config/scripts.
7. **Do not hide failures.** Three attempts at the same failing step -> write a short analysis before changing architecture.
8. **Do not weaken checks to get a demo.** Negative security tests are exit gates.
9. **Preserve recovery.** Develop lifecycle/debug remains open for the prototype unless explicitly approved otherwise.
10. **Keep product code minimal.** Prefer deleting copied sample functionality to adding new framework layers.

---

# 19. Concrete execution order

```text
P0  Install/pin tools, verify JP13/R274, run stock NXP examples
 |
P1  Create lean repo + mcxn.py + docs skeleton
 |
P2  FreeRTOS/lwIP V1/V2 + Hello socket + UUID/status
 |
P3  Default IFR MCUboot + steady LED + signed inner images
 |
P4  NXP SEC provisioning + SB3 over stock xmodem_sb3
 |     correct CUST_MK_SK PASS
 |     wrong CUST_MK_SK FAIL
 |
P5  Replace XMODEM transport with 180-s TCP adapter
 |
P6  Thin host package/update CLI + unit registry + evidence
 |
 +--> BENCH DEMO READY
 |
P7  NXP ROM secure boot of MCUboot, Develop lifecycle, recovery proof
 |
 +--> PRODUCTION-SHAPED SECURE UPDATE PROTOTYPE READY
```

No NPX/TLS/revert/antirollback work is on this critical path.

---

# 20. Definition of done

## 20.1 Bench demo ready — end P6

All must be true:

- FreeRTOS + lwIP application runs;
- V1/V2 visually distinct;
- bootloader LED steady ON;
- Hello socket works reliably;
- update socket only accepts new sessions in first 180 s;
- NXP MCUboot verifies signed application;
- correct unit SB3 works;
- wrong-key SB3 fails;
- corrupted SB3 fails;
- secure update works through Ethernet using NXP SB3 processing;
- transfer interruption cannot activate partial image;
- full process is CLI-driven from Cursor terminal;
- recovery runbook proven;
- secret material not in Git.

## 20.2 Production-shaped secure-update prototype — end P7

Additionally:

- NXP ROM authenticates MCUboot;
- tampered MCUboot is rejected;
- development recovery still works;
- one final V1 -> V2 encrypted Ethernet update passes after secure-boot enablement.

---

# 21. Deferred product backlog — explicitly not part of this implementation

Only reconsider after the prototype is accepted:

1. production lifecycle/OTP/debug authentication;
2. firmware anti-rollback using MCXN monotonic counters;
3. Portenta-style automatic health rollback using a separately qualified update strategy;
4. TLS/mTLS/client authorization;
5. exact-package single-use (`C_pkg`-style) anti-replay;
6. NPX encrypted-XIP / IP protection at rest;
7. production HSM/signature-provider integration;
8. manufacturing automation for the whole fleet;
9. long-duration one-year reliability qualification;
10. licensing.

None shall be silently pulled into P0-P7.

---

# 22. Authoritative references to keep with the project

The agent should save these URLs in `docs/NXP_REFERENCES.md` and, where possible, use the matching documentation inside the pinned SDK/SEC installation.

1. **MCUXpresso SDK 26.06 FRDM-MCXN947 board documentation**  
   https://mcuxpresso.nxp.com/mcuxsdk/26.06.00/html/boards/MCX/frdmmcxn947/index.html

2. **MCUboot / OTA example changelog**  
   https://docs.mcuxpresso.nxp.com/mcuxsdk/26.06.00/html/examples/ota_examples/CHANGELOG.html

3. **FRDM-MCXN947 MCUboot example / default layout**  
   Use the 26.06 installed SDK board-specific `ota_examples/mcuboot_opensource` README; equivalent public documentation is under the MCUXpresso SDK docs.

4. **NXP MCUboot flash-remap documentation**  
   https://mcuxpresso.nxp.com/mcuxsdk/latest/html/examples/ota_examples/_doc/flash_remap_readme.html

5. **MCXN SB3 OTA workflow**  
   https://mcuxpresso.nxp.com/mcuxsdk/latest/html/examples/ota_examples/_doc/sb3_mcxn_readme.html

6. **Secure Provisioning Tool 26.06 release notes**  
   https://docs.mcuxpresso.nxp.com/secure/latest/release_notes.html

7. **Secure Provisioning Tool command-line operations**  
   https://docs.mcuxpresso.nxp.com/secure/latest/08_command_line_operations.html

8. **Secure Provisioning Tool processor-specific workflows**  
   https://docs.mcuxpresso.nxp.com/secure/latest/06_processor_specific_workflow.html

9. **FRDM-MCXN947 Ethernet hardware example**  
   Use the 26.06 installed `driver_examples/enet` README; it specifies JP13 2-3 and R274 populated.

10. **NXP MCX N documentation page** — includes current AN14148 Secure Boot and AN14166 SB3 OTA application notes  
    https://www.nxp.com/products/MCX-N94-N54-N53-N52-N24

---

# 23. Final engineering recommendation

For this prototype, do **not** port the Portenta updater architecture.

The shortest credible path is:

```text
NXP ROM
  -> NXP MCUboot
  -> NXP signed application
  -> NXP SB3.1 secure update
  -> unique CUST_MK_SK per unit
  -> NXP FreeRTOS/lwIP Ethernet
  -> only a thin 180-s TCP transport adapter written by us
```

That architecture meets the requested demonstration while keeping security-sensitive custom firmware to the minimum practical amount.

If implementation begins to require a new encrypted container, custom key derivation, custom signature verification, a large bootloader fork, NPX, TLS, or a custom rollback state machine, stop: the project has drifted away from the purpose of this prototype.
