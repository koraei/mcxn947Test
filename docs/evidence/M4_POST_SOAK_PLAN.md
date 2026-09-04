# M4 post-soak execution plan (do not run until soak ends)

**Authority:** user accept of current M4 state (2026-09-03).  
**Hard rule until soak completes:** do **not** cable-cycle, flash, LinkServer reset, or otherwise disturb DEV-UNIT-01 / the running `m4_persistent_soak.py` process.

**Soak artifacts (when finished):**
- Live/final: `C:\mcxn\builds\m4_persistent_soak\soak_live.json`, `soak_final.json`, `soak_stdout.txt`
- Copy into repo evidence as needed under `docs/evidence/`

**Frozen constraints (still):** no `APP_SIZE` / MCUboot / slot / CMPA/CFPA/IFR / CUST_MK_SK / secure-boot changes; no TLS architecture redesign without evidence.

---

## 1. Save and verify soak evidence

Acceptance checks against `soak_final.json` (+ UART `QASTRM` stats if captured):

| Check | Pass criterion |
|-------|----------------|
| Sustained rate | `app_bps` ≈ 100 000 (± reasonable pacing jitter) |
| Payload integrity | `verify_fail == 0` |
| Session stability | no unexpected TLS disconnects (`disconnects` only if cleaned up + auto-recovered; prefer 0 for clean run) |
| MCU health | no assert/fault/WDOG reset during soak (UART / uptime continuity) |
| Resources | stable `heap_free_min` and QA task `stack_hwm_words` (UART) |

Save: `docs/evidence/M4_PERSISTENT_SOAK.md` + copy final JSON.

## 2. Manual physical Ethernet cable cycles

Follow `docs/evidence/M4_CABLE_CYCLES.md` (Windows NIC disable remains blocked).

- Target: up to 20 unplug/replug cycles on the board Ethernet cable.
- After each: ping `192.168.2.90` recovers; `python tools/mcxn.py hello` succeeds; **no MCU reboot**.
- Log results in `M4_CABLE_CYCLES.md` table.

Prefer running this **after** soak ends (or on a window when soak is not the priority). Do not interrupt the 24 h soak.

## 3. Concurrent second mTLS session investigation

Keep production protocol; use QA `:5001` + `:5000` or two connects to the same listener as needed for a **bounded** dual-session probe.

Capture:

1. Host: exact `ssl` / `ConnectionResetError` / OpenSSL errors for the second handshake.
2. MCU UART: `mtls: handshake fail …` codes, any PSA/mbedTLS prints.
3. Free heap before first session, while first is open, during second handshake attempt (`mallinfo` / existing QASTRM heap print or temporary PRINTF — QA-only if code change needed).
4. Classify root cause:
   - `mtls_socket` shared `mbedtls_ssl_config` / session state
   - heap or task stack exhaustion
   - PSA/ELS locking / threading ALT
   - intentional single-active-session limitation

**If** a small config/resource fix is evidenced → apply QA or production-safe fix and rerun a short dual-session test.  
**If** NXP PSA/ELS serializes this → document limitation + propose explicit **single-active-mTLS-session** policy (no unexplained TCP RST).  
Do **not** redesign TLS or remove ELS without evidence.

Harness (to be run post-soak): `tools/m4_dual_session_probe.py` (create if missing when executing).

## 4. Restore production (non-QA) image

- Build **without** `--qa`: confirm `APP_QA_STREAM` defaults to 0; no `:5001` listener; production `__heap_size__=0x1B000`.
- Flash or OTA path as appropriate so board is not left on QA soak image for the release proof.
- Prefer: build production `3.0.0` / then OTA to `3.1.0` as step 5 requires.

## 5. Strictly newer mTLS/SB3 OTA: 3.0.0 → 3.1.0

- Package/release **3.1.0** V3 (imgtool key guard enforced).
- Perform mTLS OTAS SB3 update.
- Verify: STATUS version/variant, Hello, UUID unchanged, update window (~180 s) behavior.

## 6. Final M4 report

Write `docs/evidence/M4_FINAL_REPORT.md` covering:

- Churn evidence (1000 reconnect + handshake endurance)
- Fault matrix
- Persistent 24 h soak results
- Cable cycles
- Concurrency investigation + policy/fix
- Production restore + 3.0.0→3.1.0 OTA
- Explicit non-changes (APP_SIZE, boot chain, IFR, etc.)

Update `docs/evidence/M4_RELIABILITY.md` and `docs/dev-log.md`.

---

## Expected soak end

Started ~2026-09-03T20:19Z → **~2026-09-04T20:19Z**.  
Resume this plan when `soak_final.json` exists or process exits.
