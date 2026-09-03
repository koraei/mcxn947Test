# Development log

## 2026-09-03 â€” Phase P0 start

**Branch:** `feat/secure-ethernet-ota`  
**Plan:** `doc/FRDM_MCXN947_SECURE_ETHERNET_UPDATE_AUTONOMOUS_AGENT_PLAN_REV_C_FINAL.md` (Rev C FINAL)

### Actions

1. Confirmed MCU-Link probe via LinkServer: serial `MNZW4VYTFX113`, board FRDM-MCXN947, VCOM COM9.
2. Installed host Python deps: `west`, `pyserial`, `pytest`.
3. `west init` SDK manifests at `C:\mcxn\mcuxsdk-ws` on tag/rev `v26.06.00-LTS` (manifest commit `b01ab903â€¦`).
4. Started `west update --narrow -o=--depth=1` (PID logged in session; see `C:\mcxn\west-update.log`).
5. Sideloaded MCUXpresso for VS Code/Cursor extension from marketplace VSIX (`NXPSemiconductors.mcuxpresso`).
6. Installed clangd + YAML extensions.
7. Created `docs/device-state.md`, `docs/toolchain-lock.md`, `docs/NXP_REFERENCES.md`.
8. External secrets path created: `C:\mcxn-secrets\DEV-UNIT-01\`.

### Evidence

- LinkServer `probes` output recorded in `docs/device-state.md`.
- Tool versions in `docs/toolchain-lock.md`.

### Deviations / open

- SEC 26.06 / `securep.exe` **not installed** (NXP account download required) â€” needed before P4.
- JP13/R274 not visually confirmed yet â€” will prove via stock ENET example.
- GCC 14.3 vs plan 14.2.x family note.

### Next (at time of P0 start)

- Finish `west update`.
- Build/flash stock examples; write inventory.

## 2026-09-03 â€” Phase P0 progress + Ethernet gate

### Completed

1. SDK examples available under `C:\mcxn\mcuxsdk-ws\mcuxsdk` (west update still may be finishing optional repos).
2. Built + flashed `hello_world` â€” UART `hello world.` / SDK `2026.06.00`.
3. Built + flashed `freertos_hello` â€” UART `Hello world.`.
4. Built `lwip_ping_freertos`, `ota_mcuboot_server_enet`, `ota_mcuboot_basic`, `mcuboot_opensource` (all link OK).
5. Flashed `lwip_ping_freertos` â€” **PHY Auto-negotiation failed** (hardware gate).
6. Wrote `docs/evidence/P0_NXP_INVENTORY.md` with exact paths, build/flash syntax, signing params, layout.

### Evidence

- `C:\mcxn\builds\hello_world_build.log`, UART capture in session
- `C:\mcxn\builds\freertos_hello_uart.txt`
- `C:\mcxn\builds\lwip_ping_uart.txt`
- `docs/evidence/P0_NXP_INVENTORY.md`

### Stop reason

**P0.2 / Â§1.5 Ethernet hardware prerequisite not satisfied.** Host Ethernet adapters disconnected; board PHY reports no link. JP13/R274 not visually verified.

### Next (at Ethernet gate)

Resolved by user: Ethernet connected; static IP policy **192.168.2.90/24**.

## 2026-09-03 â€” P0 closed; P1/P2 progress; P3 CMPA gate

### P0 closed
- Stock `lwip_ping` with EXTRA_CFLAGS IP override: PHY up, `192.168.2.90`, host ping 6/6.
- Evidence: `docs/evidence/P0_ETHERNET_PROOF.md`

### P1
- Repo structure, `mcxn.toml`, `tools/mcxn.py`, docs/ADRs/reuse-map/recover draft.
- Unit registry `units/DEV-UNIT-01.json`.

### P2
- Freestanding export of `ota_mcuboot_server/enet` â†’ `firmware/app`.
- Removed HTTP; added LED/Hello/Update-window stub/diagnostics.
- Standalone linker (`MCUBOOT_HEADER_SIZE=0`) so app boots without IFR MCUboot.
- Verified: Hello â†’ `Hello PC!`; STATUS; IP 192.168.2.90; UUID stable; update port open in window.
- V1 and V2 images build.

### Next gate (P3)
- First CMPA `BOOT_SRC` write + IFR MCUboot program requires **owner approval**.

## 2026-09-03 â€” P3 APPROVED; ISP transport gate

**Owner:** `APPROVE P3 CMPA/IFR` with 8 conditions.

### Completed before any PFR/IFR write

1. **Entered ISP** via `nxpdebugmbox -i mcu-link -s MNZW4VYTFX113 cmd -f mcxn947 ispmode` (reported success). Also tried LinkServer `wirebootconfig` ISP_CTRL patterns + reset.
2. **CMPA/CFPA binary backups** (debug `mem-tool` AHB read; validated by reading app flash @0x0 successfully):
   - `C:\mcxn-secrets\DEV-UNIT-01\backup\cmpa_pre_p3.bin` â€” 512 B, all `0xFF` (erased/unprogrammed)
     - SHA-256: `9f56cda75fefeab90f6fa5d5ddc9601544b121732c5ecccab32e631060453a5d`
   - `C:\mcxn-secrets\DEV-UNIT-01\backup\cfpa_pre_p3.bin` â€” 512 B; almost all `0xFF`, trailer `0x1F0..0x1FF` = `b4a2ee48ab01e4ca9e3f304f15bc9bcd`
     - SHA-256: `12efb28ee3d94d72b5e02af94b14c2e55348dacf5cab60f01d76202b6af566ca`
   - Window: `pfr_window_pre_p3.bin` @ `0x01000000` len `0x6000` SHA-256 `15112ee2c31a2aa498a80d95433b49ffc11398f6bf04952878b8671b46695936`
3. **Inspected NXP SDK `cmpa.bin`** (`â€¦\mcuboot_opensource\cmpa.bin`):
   - SHA-256: `342f7ed070a2206bdd2d2894bab07188653a42f33a6e4c1f908bdbafed76362e`
   - Raw: only word0 = `0x59630002` (HEADER `0x5963` + `BOOT_SRC=0b10`); rest zeros
   - SPSDK `pfr parse -f mcxn947 -t cmpa -d`: **sole diff vs defaults = `BOOT_CFG.BOOT_SRC: SECONDARY_BOOTLOADER`**
   - Security fields (lifecycle/debug-lock/secure-boot/RoTKH/NPX/CUST_MK_SK/seal/CRC) remain default/disabled/zero â€” **no unexpected security changes**
4. IFR @ `0x01008000` still erased (`0xFF`); LinkServer cannot flash IFR; DM `write-to-flash` unsupported in current lifecycle.

### Stop reason (hardware / ISP transport)

Documented NXP flow needs `blhost -u 0x1FC9,0x014F` (ROM USB HID) **or** UART ISP on MCU-Link VCOM after **button** ISP entry.

Observed:
- After DM `ispmode`, **no** USB device `VID_1FC9/PID_014F` (HS USB **J11** not presenting ROM HID â€” cable likely only on MCU-Link **J17**)
- `blhost -p COM9,115200` does **not** PING after DM ISP / wirebootconfig (MCU-Link VCOM is FC4; ROM UART ISP may need physical SW3+SW1 sequence)
- No CMPA/IFR/CMPA writes performed

### Need from owner (one of)

**A.** Plug USB-C PCâ†”**J11** (HS USB), keep J17; reply `USB ISP READY`  
**B.** Hold **SW3**, press/release **SW1**, release SW3; reply `ISP READY`  

Then agent resumes: blhost backup verify â†’ erase/program IFR MCUboot â†’ write `cmpa.bin` â†’ rebuild/sign V1 (`--pad --confirm`) â†’ verify chain â†’ prove recovery.

## 2026-09-03 â€” P3 USB ISP: J11 connected but HID not enumerating

Owner replied `USB ISP READY` (J11 + J17).

### Observed
- DM `ispmode` succeeds (modes 0/4/5 tried).
- After ISP, Windows shows **`Unknown USB Device (Device Descriptor Request Failed)`** `USB\VID_0000&PID_0002\â€¦` â€” J11 is electrically active.
- **`VID_1FC9/PID_014F` never appears**; `blhost -u 0x1FC9,0x014F -- get-property 1` fails.
- No CMPA/IFR writes performed (per gate: verify blhost before write).

### Likely cause
ROM USB device fails Windows enumeration (common with charge-only cable, USB3-only hub quirks, or need for physical SW3+SW1 while J11 plugged).

### Still needed
1. Use a known **data** USB-C cable on J11 (prefer a **USB 2.0** port / hub).
2. After agent enters ISP (or with cable already on J11): hold **SW3**, tap **SW1**, release SW3; confirm Device Manager shows NXP HID / `1FC9:014F`.
3. Reply `ISP READY` when `014F` is visible (or re-say `USB ISP READY` after cable/port change).

## 2026-09-03 â€” P3 CLOSED

Owner changed USB port; `0x1FC9:0x014F` enumerated; blhost OK.

### Executed
1. blhost-verified CMPA/CFPA backups (match pre-P3 hashes).
2. Programmed IFR MCUboot + NXP `cmpa.bin` (`BOOT_SRC=0b10`); ROM filled CMPA CRC/CMAC trailer only.
3. Rebuilt V1 with MCUboot linker (vectors @ `0x400`); imgtool `--pad --confirm`; flashed signed 1 MiB image.
4. Verified ROM â†’ IFR MCUboot â†’ V1; ping; Hello; STATUS.
5. ISP recovery rewrite of IFR+CMPA proven; STATUS OK.
6. Wrong-signer image rejected; good V1 restored.

### Evidence
- `docs/evidence/P3_CMPA_IFR_PROOF.md`
- `docs/runbooks/recover.md` updated
- UART: `C:\mcxn\builds\p3_boot_uart.txt`, `p3_wrong_signer_uart.txt`

### Next gate
**P5** Ethernet SB3 â€” owner accepted P4; continue autonomously.

## 2026-09-03 â€” P5 complete

Thin TCP `:5555` transport into NXP `sb3_api` (no TLS/HTTP/JSON/extra crypto). HW matrix PASS including V1â†’V2 over Ethernet, wrong-key/corrupt reject, 180â€¯s window, late session, idle timeout, Hello resilience. See `docs/evidence/P5_ETHERNET_SB3_PROOF.md`, `docs/protocol-update.md`.

## 2026-09-03 â€” P6 complete

Host CLI is authoritative: `doctor` / `build` / `package` / `release` / `update`. Unit registry `units/DEV-UNIT-01.json`; artefacts under `dist/<unit>/<version>/` with sidecar (no secrets). Pytest 8/8. Live `UPDATE PASS` V1â†’V2 via packaged SB3. See `docs/evidence/P6_HOST_CLI_PROOF.md`. **Stopped before P7.**



## 2026-09-03 — P7 APPROVED and CLOSED (no writes performed)

**Owner:** `APPROVE P7 SECURE BOOT` — inspect/build-only findings accepted.

### Findings accepted

- `SECURE_BOOT_CFG.SEC_BOOT_EN = ECDSA_SIGNED` was written to CMPA at P3 provisioning.
- Live CMPA `ROTKH = 670EE45ABA45117A…` matches the RKTH printed by `nxpimage mbi export` for the installed MCUboot MBI.
- Signed MCUboot MBI: 24 768 B — fits IFR 32 KB slot with 8 KB headroom.
- `CUST_MK_SK` blob intact; SB3.1 OTA update flow fully functional (P4/P5/P6 proven).
- Lifecycle: `Develop`. Debug: fully open via DAP (CC_SOCU all USE_DAP).
- NPX: disabled. UUID_CHECK: disabled. No anti-rollback counters active.
- IFR MCUboot slot hardware read-protected (OEM_ROM_RWXL_CODE) — expected and correct.

### No writes performed
Zero changes to CMPA, CFPA, IFR, RoT hashes, lifecycle, fuses, or any other security state.

### Architecture frozen
The proven secure-boot / SB3 OTA update architecture is frozen. No new optional features.

### Evidence
- Gate report: `docs/evidence/P7_ROM_SECBOOT_GATE_REPORT.md`
- Backups: `C:\mcxn-secrets\DEV-UNIT-01\backup\p7_pre\` (CMPA/CFPA/IFR0 bin+yaml)

## 2026-09-03 — mTLS plan start; GATE (boot hang)

**Branch:** `feat/mtls-tcp-socket` (from P7 `49c24af` / tag `p7-frozen-mtls-baseline`)  
**Plan:** `doc/FRDM_MCXN947_RELIABLE_MTLS_TCP_SOCKET_PLAN_REV_B_FINAL.md`

### Done
- M0: NXP `lwip_httpssrv_mbedTLS` wrapper builds; on-target HTTPS not proven (hang after flash).
- M1: PKI under `C:\mcxn-secrets\mtls`; `mtls_socket` + host Python `ssl` wired; pytest 10/10.
- Product mTLS V1 **links** (~96% flash) but **hangs on boot** after dual-slot flash.

### Board NOW
Restored plaintext V2 (`app_v2_SIGNED_PAD.bin` both slots). STATUS V2 OK. No security writes.

### Evidence
`docs/evidence/M0_M1_MTLS_GATE_REPORT.md`

### Stop
Human/debug gate: diagnose mTLS app boot hang before continuing M2/M3/M4 hardware tests.


## 2026-09-03 — mTLS boot debug APPROVED; M2/M3 proven

### Boot hang root cause
Application image was signed with `IMG1_1` (ROM/MBI). MCUboot expects `mcxn.toml` `imgtool_key` (SDK `sign-ecdsa-p256-priv.pem`). KEYHASH mismatch → no app entry (empty UART / no ping). Evidence: `docs/evidence/MTLS_BOOT_HANG_ROOT_CAUSE.md`.

No APP_SIZE change. No debug-attach needed after KEYHASH proof. No CMPA/CFPA/IFR writes.

### M2
mTLS Hello/STATUS; raw/no-cert/wrong-CA/wrong-FP rejected; 100 reconnect PASS.

### M3
Chunked TLS OTAS required (`send_otas` 8 KiB). V1→V2 and CLI V2→V3 `UPDATE PASS`. Board now V3. Evidence: `docs/evidence/M2_M3_MTLS_PROOF.md`.

### Host fix
`tools/mcxn_lib/workflow.py` `send_otas`: chunked `sendall`.

### Remaining gate (M4 time)
24 h soak / full abort+link matrix still outstanding.

