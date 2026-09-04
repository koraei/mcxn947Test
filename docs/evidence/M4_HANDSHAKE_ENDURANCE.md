# M4 handshake / reconnect endurance (partial soak — superseded)

**Classification:** TLS handshake/reconnect endurance only. **Not** the representative throughput soak.

**Stopped:** 2026-09-03 ~20:02 UTC after user redirected M4 soak requirements.

## Result snapshot

| Metric | Value |
|--------|------:|
| Elapsed | ~2024 s (~33.7 min) |
| messages_ok | 5876 |
| messages_fail | 1 |
| handshake_fail | 0 |
| reconnects | 5882 |
| unexpected_reset | 0 |
| app_bps (payload) | ~556 B/s |
| ping | true |
| STATUS at stop | `3.0.0` / `V3` |

Artifact: `C:\mcxn\builds\m4_soak\handshake_endurance_partial.json`

## Why not representative

Product `:5000` Hello/ECHO closes after one request → every message needs a full mTLS handshake. Throughput is handshake-bound (~0.5 KB/s), not the required ~100 KB/s persistent-session load.

## Combined connection-churn evidence

| Evidence | Result |
|----------|--------|
| `docs/evidence/M4_reconnect.json` — 1000 reconnects @ 50 ms | **PASS** |
| This partial endurance run | **PASS** (stable, no unexpected MCU reset) |
| Burst reconnect without pacing | Ethernet hung until MCU reset (rate-limit note) |

Primary M4 throughput soak moves to QA-only persistent mTLS stream (compile-time gated).
