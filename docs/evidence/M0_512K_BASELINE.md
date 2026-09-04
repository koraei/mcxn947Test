# M0 baseline freeze — 512 KiB plan

**Branch:** `feat/512k-ab-encrypted-runhours` @ `fd8670d` (+ lean WIP)  
**Tag:** `pre-512k-layout-runhours`  
**Authority:** `doc/FRDM_MCXN947_512K_AB_ENCRYPTED_RUNHOURS_TEST_PLAN_REV_B_FINAL.md`

## Soak

Prior 24 h persistent soak **stopped by owner request** (2026-09-04); board freed for M0/M1 work.

## Baseline image (debug product V3, non-QA)

| Item | Value |
|------|------:|
| text+data | **785 640 B** (~767 KiB) |
| raw `.bin` | 785 976 B |
| signed/padded (1 MiB slot) | 1 048 576 B |
| `m_text` region | ~96% of ~798 KiB |

Artifacts: `C:\mcxn\builds\m0_512k_baseline\` (`size.txt`, `sha256.txt`, `top100_symbols.txt`, elf/bin/map/signed).

## On-board smoke (after dual-slot flash)

| Check | Result |
|-------|--------|
| Ping 192.168.2.90 | PASS |
| mTLS Hello | `Hello PC! V3-PULSE-RED` |
| STATUS | `3.0.0` / `V3` / UUID `9DA8D48D…` / window 163 s |

## Security-state backup

**Deferred until before any CMPA write (M5).** No PFR/CMPA/CFPA/IFR changes in M0–M1.

## Next

M1 LEAN_PROD_TEST: `python tools/mcxn.py build v3 --lean` → size vs ≤448 KiB signed / &lt;512 KiB gate.
