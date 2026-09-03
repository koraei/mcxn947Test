# mTLS boot hang — root cause (IMAGE/MCUBOOT)

**Date:** 2026-09-03  
**Branch:** `feat/mtls-tcp-socket`  
**Plan:** `doc/FRDM_MCXN947_RELIABLE_MTLS_TCP_SOCKET_PLAN_REV_B_FINAL.md`

## Verdict

The dual-slot “boot hang” (no ping / empty UART) was **not** an app HardFault, ELS hang, or APP_SIZE overflow.

**Root cause:** the mTLS product image was signed with **`IMG1_1_p256.pem`** (ROM/MBI key).  
IFR MCUboot expects the **same ECDSA-P256 key as known-good V2**:

`mcuxsdk/middleware/mcuboot_opensource/boot/nxp_mcux_sdk/keys/sign-ecdsa-p256-priv.pem`  
(configured in `mcxn.toml` as `paths.imgtool_key`).

Wrong-signer images do not reach the application, so there is no product UART and no Ethernet.

## Evidence — KEYHASH TLV

| Image | KEYHASH (SHA-256 of DER SubjectPublicKeyInfo) | Matches |
|-------|-----------------------------------------------|---------|
| Known-good `app_v2_SIGNED_PAD.bin` | `737072a3…1653` | SDK `sign-ecdsa-p256-priv.pem` |
| Failed mTLS (IMG1_1) | `95e4e495…2f46` | `IMG1_1_p256.pem` |
| Fixed mTLS (re-signed) | `737072a3…1653` | same as V2 |

`imgtool verify --key <sdk_key>`: **PASS** on fixed image.  
Slot fit: `hdr=0x400`, `img_size=0xbfe20`, padded to `0x100000` — inside 1 MiB slot (no APP_SIZE change).

## Layout comparison (V2 vs fixed mTLS)

| Field | V2 | mTLS V1 (fixed) |
|-------|----|-----------------|
| magic | `0x96f3b83d` | same |
| hdr_size | `0x400` | same |
| img_size | `0x30e88` (~200 KB) | `0xbfe20` (~786 KB) |
| slot-size / pad | `0x100000` | same |
| KEYHASH | SDK demo | SDK demo (after fix) |
| trailer boot magic | present | present |

## Debug attach

**Not required** after KEYHASH mismatch was proven and corrected. MCU-Link register capture skipped.

## Fix applied

```text
imgtool sign --key <sdk sign-ecdsa-p256-priv.pem> \
  --align 16 --version 1.0.0 --slot-size 0x100000 \
  --header-size 0x400 --pad-header --pad --confirm \
  mcxn947_secure_ota_cm33_core0.bin app_v1_SIGNED_PAD.bin
```

Dual-slot LinkServer load `@0x0` and `@0x00100000`.

## First-proof after fix (required gate)

| Check | Result |
|-------|--------|
| Boot banner | `MCXN947 Secure OTA prototype` + `mtls: global init OK` |
| Ping | OK `192.168.2.90` |
| mTLS `:5000` | `Hello PC! V1-SLOW-GREEN` via `python tools/mcxn.py hello` |
| STATUS | `version=1.0.0 variant=V1` |
| Raw TCP plaintext | **rejected** (`ConnectionResetError`) |
| UART log | `C:\mcxn\builds\mtls_boot_uart_ok.txt` |

## Process note

Do **not** sign application slots with `IMG1_1` (that key authenticates the IFR MCUboot MBI to ROM). Application slots use `mcxn.toml` `imgtool_key` / `tools/mcxn_lib.workflow.sign_image`.

## Security state

No CMPA/CFPA/IFR/`CUST_MK_SK`/lifecycle changes. APP_SIZE / 1 MiB A/B layout unchanged.
