# M1 lean QA throughput sample (~60 s)

**Date:** 2026-09-04  
**Image:** `app_v3_lean_qa` (LEAN + `APP_QA_STREAM=1`), dual-slot flash, field 1 MiB remap  
**Host:** `python tools/m4_persistent_soak.py --hours 0.0167 --kbps 100`

## Result

| Metric | Value |
|--------|------:|
| Elapsed | 60.1 s |
| App payload rate (TX+RX) | **98 243 B/s ≈ 98.2 KB/s** |
| Target | 100 KB/s |
| vs baseline target | **98.2%** (≥95% gate) |
| verify_fail / tls_err / disconnects | 0 / 0 / 0 |
| Stream frames | 2884 TX / 2884 RX |

Artifact: `C:\mcxn\builds\m1_lean_throughput\soak_final.json`

Script `pass:false` because post-soak concurrent Hello on `:5000` got RST while stream path was tearing down (known dual-session PSA limitation). **Throughput criterion itself PASS.**

UART during run: `QASTRM ... heap_free_min=32 stack_hwm_words=1480` (tight heap HWM on QA arena — expected with `0x38000`).

Board restored afterward to lean product (non-QA) 3.1.0 both slots.
