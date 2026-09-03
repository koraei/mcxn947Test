# P5 — Ethernet SB3 transport proof

**Date:** 2026-09-03  
**Unit:** DEV-UNIT-01 UUID `9DA8D48D0DDCD755903E8FBD3836C153`  
**Architecture:** TCP `:5555` + 28-byte `OTAS` header + raw SB3 → NXP `sb3_api` → inactive slot → `ReadyForTest`  
**No:** TLS, HTTP, JSON, CBOR, custom signatures, package hashes, extra encryption

## Artifacts

| Item | Path |
|------|------|
| Protocol | `docs/protocol-update.md` |
| Call graph | `docs/evidence/P5_SB3_CALL_GRAPH.md` |
| Product V1 signed | `C:\mcxn\builds\app_v1\app_v1_SIGNED.bin` |
| Product V2 padded | `C:\mcxn\builds\app_v2\app_v2_SIGNED_PAD.bin` |
| Good SB3 | `C:\mcxn-secrets\DEV-UNIT-01\sec-workspace\ota_images\ota_sb_product_v2_pad.sb` (~1 196 828 B) |
| Host CLI | `python tools/mcxn.py update --sb3 <path>` |

## HW matrix

| # | Test | Result |
|---|------|--------|
| 1 | Correct SB3 over Ethernet V1→V2 | **PASS** — reply `OK`; STATUS `version=2.0.0 variant=V2`; Hello OK |
| 2 | Wrong-key SB3 | **PASS** — `ERR SB3`; remained bootable V1; Hello OK |
| 3 | Corrupted SB3 (byte flip @ offset 512) | **PASS** — `ERR SB3`; Hello OK |
| 4 | Connect after window (uptime≥180) | **PASS** — `ConnectionRefusedError`; STATUS `update_window_s=0`; Hello OK |
| 5 | Session start @ uptime_s=175 (window=5) | **PASS** — `OK` in ~4.6 s; rebooted to V2 (session outlives window) |
| 6 | Idle client (no header) | **PASS** — `ERR TIMEOUT`; Hello OK |
| 7 | Connect/disconnect spam ×20 | **PASS** — Hello/STATUS still OK |
| 8 | Bad magic / wrong UUID | **PASS** — `ERR MAGIC` / `ERR UUID` |
| 9 | Post-update ping + Hello + STATUS + UUID | **PASS** |

## Tool note (non-blocking)

MCU-Link VCOM **TX** still fails with semaphore timeout (RX works). P5 Ethernet path does not depend on VCOM TX. Serial `xmodem_sb3` remains unavailable until LinkServer/VCOM TX is restored; crypto path already proven in P4 via `blhost receive-sb-file`.

## Security state

P5 did **not** change CMPA/CFPA/lifecycle/debug/`CUST_MK_SK`.
