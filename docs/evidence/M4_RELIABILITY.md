# M4 reliability — accepted; soak undisturbed

**Accepted:** 2026-09-03 (user).  
**Board:** DEV-UNIT-01, firmware **3.0.0 V3** + **QA stream** (`APP_QA_STREAM=1`) for load soak only.  
**Hard rule:** do **not** cable-cycle, flash, or reset the board until the 24 h persistent soak finishes.

**Post-soak sequence:** `docs/evidence/M4_POST_SOAK_PLAN.md` (verify soak → cable cycles → dual-session root-cause → prod restore → 3.0.0→3.1.0 OTA → final report).

## Resource baseline

| Build | `m_text` | `m_data` | `__heap_size__` | Notes |
|-------|----------|----------|-----------------|-------|
| Product V3 | ~784 KB / 798 KB | ~184 KB / 312 KB | `0x1B000` | Production; QA stream not linked/active |
| QA V3 soak | ~786 KB / 798 KB | ~303 KB / 312 KB | `0x38000` via `-DQA_HEAP_SIZE` | QA stream task + mTLS buffers |

Production Hello/ECHO protocol unchanged. QA stream is compile-time gated (`APP_QA_STREAM`), TCP `:5001`, same `lwIP` + `mtls_socket` + mbedTLS path.

**Observed (not yet closed):** second concurrent mTLS handshake can RST while one session is open — investigate after soak (`M4_POST_SOAK_PLAN.md` §3); do not redesign TLS/ELS without evidence.

## Separate M4 evidence (kept)

| Test | Result |
|------|--------|
| 1000 reconnect @ 50 ms | **PASS** — `docs/evidence/M4_reconnect.json` |
| Handshake/reconnect endurance (~34 min partial soak) | **PASS** (reclassified) — `docs/evidence/M4_HANDSHAKE_ENDURANCE.md` |
| Cert/fault matrix (no-cert, wrong-CA, RST, PC kill) | **PASS** — `docs/evidence/M4_faults.json` |
| Burst reconnect no delay | Ethernet hung until MCU reset (rate-limit note) |
| 20 NIC disable / cable cycles | **Deferred** until after soak — `docs/evidence/M4_CABLE_CYCLES.md` |

## Primary soak (representative load) — RUNNING (do not disturb)

| Parameter | Value |
|-----------|--------|
| Session | One long-lived mTLS TCP session (auto-reconnect on drop) |
| Target rate | ~100 KB/s total application payload (TX+RX echo ≈ 5×20 KB/s) |
| Duration | 24 hours |
| Frame | 1024 B: `seq` + magic `M4S1` + patterned payload; both directions verified |
| Host | `python tools/m4_persistent_soak.py --hours 24 --kbps 100 --logdir C:\mcxn\builds\m4_persistent_soak` |
| Live | `C:\mcxn\builds\m4_persistent_soak\soak_live.json` |
| Approx. start (UTC) | 2026-09-03T20:19Z |
| Approx. end (UTC) | 2026-09-04T20:19Z |

No changes to `APP_SIZE`, secure boot, MCUboot, SB3, CUST_MK_SK, CMPA/CFPA/IFR, lifecycle, or production mTLS architecture.
