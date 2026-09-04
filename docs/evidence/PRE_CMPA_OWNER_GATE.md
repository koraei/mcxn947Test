# PRE-CMPA OWNER GATE — 512 KiB A/B + run-hours

**STOP:** No CMPA / `FLASH_REMAP_SIZE` / CFPA / IFR / RoT / `CUST_MK_SK` write has been performed.  
**Awaiting:** explicit owner approval before any security-state change.

**Date:** 2026-09-04  
**Branch:** `feat/512k-ab-encrypted-runhours`  
**HEAD commit:** `f699806d807475cd3ac817d259a1e6f5c7114a8b` (`M1 LEAN_PROD…`)  
**Working tree:** **dirty** — M1/M2/M3 evidence + layout/journal WIP not yet committed (ask if you want a commit).  
**Freeze tag:** `pre-512k-layout-runhours`  
**Board now:** lean product **3.1.0 V3**, Hello/STATUS OK, field **1 MiB** remap unchanged.

---

## 1. Firmware sizes (record correctly)

| Metric | Value | Notes |
|--------|------:|-------|
| Linker text (`arm-none-eabi-size`) | **308 512** B | lean product |
| Raw `.bin` | **308 856** B | |
| Signed **unpadded** (`--slot-size 0x80000`) | **310 032** B | real signed content |
| Signed **padded** 512 KiB file | **524 288** B | **slot pad only — not usage** |
| Build-only 512k `m_text` used / limit | **307 176** / **514 048** (~59.8%) | `mcxn10_cm33_flash_512k.ld` |
| Consecutive lean rebuild SHA-256 | **match** | `M1_lean_rebuild_hash.json` |

DER conversion: **not done** (optional; skipped to avoid risk).

---

## 2. TLS configuration (frozen)

- Overlay: `firmware/app/security/mbedtls_product_user_config.h`
- Negotiated: **`ECDHE-ECDSA-AES256-GCM-SHA384` / TLS 1.2**
- Mutual auth, CA verify, host fingerprint: preserved
- **No further mbedTLS size cuts**

---

## 3. IPv4 / IPv6

| Check | Result |
|-------|--------|
| IPv4 Hello/STATUS | PASS |
| `LWIP_IPV6=1` | unchanged |
| `nd6_*` in lean map | present |
| On-wire IPv6 LL ping | **incomplete** (need board LL from UART/MAC; `ping -6 ff02::1` not conclusive on this PC) |

---

## 4. OTA / security (lean, 1 MiB field layout)

| Test | Result | Evidence |
|------|--------|----------|
| SB3 OTA lean 3.0.0→3.1.0 | PASS | STATUS 3.1.0 |
| Corrupt/wrong update reject | PASS | prior session |
| Negatives no-cert/wrong-CA/wrong-FP | PASS | M1 faults / M2_NEG |
| 1000 reconnect | PASS | `M1_lean_reconnect.json` |
| Interrupted TLS / RST / kill | PASS | `M1_lean_faults.json`, `M1_lean_interrupt_tls.json` |
| Throughput ~60 s @ 100 KB/s target | **98.2 KB/s (98.2%)** | `M1_LEAN_THROUGHPUT.md` |
| Ethernet NIC disable cycles | **blocked** (Windows Access denied) | `M4_CABLE_CYCLES.md` — manual cable still open |
| SB3 layout checker | PASS/FAIL as designed | `check_sb3_layout.py` |

---

## 5. Journal power-fail matrix (host)

**13/13 PASS** — `M3_runhours_host_faults.json` / `M3_RUNHOURS_HOST.md`  
Device flash backend stubbed until remap (pools would still swap under 1 MiB remap).

---

## 6. Proposed exact flash addresses (unchanged from plan §3.1)

```text
0x00000000 .. 0x0007FFFF   Slot A          512 KiB
0x00080000 .. 0x0009FFFF   Platform A      128 KiB
0x000A0000 .. 0x000AFFFF   Run-hours A      64 KiB
0x000B0000 .. 0x000FFFFF   Event/log A     320 KiB
0x00100000 .. 0x0017FFFF   Slot B          512 KiB
0x00180000 .. 0x0019FFFF   Platform B      128 KiB
0x001A0000 .. 0x001AFFFF   Run-hours B      64 KiB
0x001B0000 .. 0x001FFFFF   Event/log B     320 KiB
IFR 0x01008000 .. 0x0100FFFF  MCUboot       32 KiB (unchanged)
```

Build-only: `APP_FLASH_LAYOUT_512K`, `memory_layout.h`, OTA range guards, `UPDATE_SB3_MAX_B=APP_SLOT_SIZE+…`.

---

## 7. Exact CMPA field(s) that would change (proposal only)

| Field | Current (field) | Proposed |
|-------|-----------------|----------|
| **`FLASH_REMAP_SIZE`** | value for **1 MiB** remap (`(N+1)×32 KiB = 1024 KiB` → N=31) | **`15`** → `(15+1)×32 KiB = **512 KiB**` |

**Must remain unchanged:**

- RoTKH  
- `CUST_MK_SK`  
- Secure-boot policy / `SEC_BOOT_EN`  
- Lifecycle  
- Debug policy  
- CFPA (no intentional change)  
- IFR MCUboot image  

---

## 8. Backup & rollback plan (before any write)

1. **ISP + blhost** read CMPA/CFPA/IFR0 to fresh dated tree, e.g.  
   `C:\mcxn-secrets\DEV-UNIT-01\backup\pre_512k_remap_<UTC>\`  
   (same method as P3/P7: `cmpa.bin` / `cfpa.bin` / IFR dumps + SHA-256).
2. Compare hashes to last known-good (`backup\p7_pre\` / post-P3 live).
3. Export human-readable CMPA YAML via NXP tools; confirm **only** `FLASH_REMAP_SIZE` delta in the planned write set.
4. After write: dual-slot flash lean **512k-signed** V1/V2 independently; verify boot + mTLS + SB3 A→B; confirm addresses `≥0x00080000` / `≥0x00180000` do **not** swap.
5. **Rollback:** restore previous CMPA blob from step 1 (ISP), re-flash known-good 1 MiB signed lean images to both slots, verify Hello/STATUS.

---

## 9. Explicitly NOT done yet (blocked on this gate or follow-on)

- Live CMPA/`FLASH_REMAP_SIZE` write  
- Hardware A↔B E2E on **512 KiB** slots  
- On-device journal AES-GCM + HW power-cut campaign  
- Manual Ethernet cable cycles (operator)  
- Optional DER credentials  

---

## Owner decision required

Reply with one of:

1. **APPROVE CMPA `FLASH_REMAP_SIZE=15` write** (after confirming backups), or  
2. **HOLD** / request changes, or  
3. **COMMIT WIP** on this branch first (no CMPA).
