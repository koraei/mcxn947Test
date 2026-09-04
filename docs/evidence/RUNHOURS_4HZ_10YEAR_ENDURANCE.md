# Run-hours 4 Hz / 10-year endurance evidence

**Plan:** `doc/FRDM_MCXN947_RUNHOURS_4HZ_10YEAR_ENDURANCE_TEST_PLAN_REV_A_FINAL.md`  
**Unit:** DEV-UNIT-01 (`9DA8D48D0DDCD755903E8FBD3836C153`)  
**Firmware under test:** V3 lean 512k `APP_RH_ENDURANCE_TEST=1` version **3.7.0**  
**RH key:** version **2**, key_id=1, ks=2 (ELS opaque AES-256 + RFC3394)  
**Raw logs:** `C:\mcxn\builds\rh_endurance_4hz\`

## Constraints honored

- No journal/crypto/OTA/mTLS/flash-layout/MCUboot/CMPA/CFPA/IFR/lifecycle/CUST_MK_SK redesign.
- Production quantum remains **600 s**; QA mode commits every **250 ms** via `rh_journal_append_quanta`.
- Count stop: `target_quanta = start_quanta + N`; never write past target.
- Erase events: RAM ring only (`RHERASE`); no flash erase log.
- Host uses existing mTLS `:5000` only.

## Implementation

| Piece | Location |
|-------|----------|
| Stress writer | `firmware/app/src/runhours_stress.c` |
| Erase hook | `runhours_journal.c` `sector_erase` → `rh_erase_note` |
| mTLS cmds | `RHSTRESS START/STATUS/STOP`, `RHERASE` in `hello_service.c` |
| Build flag | `--rh-endurance` → `-DAPP_RH_ENDURANCE_TEST=1` + heap `0x28000` |
| Host monitor | `tools/rh_endurance_monitor.py` / `mcxn.py rh-stress-monitor` |
| Unit tests | `tools/test_rh_endurance_monitor.py` |

**Heap note:** first endurance lean build OOMed Hello handshake (`mbedtls -0x7F00`). QA endurance builds raise `QA_HEAP_SIZE=0x28000` (not a production change).

## Gate results

### Host unit tests

```text
python tools/test_rh_endurance_monitor.py
→ Ran 5 tests … OK
```

### 5-minute smoke (`smoke/`, delta=1200)

| Check | Result |
|-------|--------|
| start→target | 671 → **1871** (exact +1200) |
| commits_ok | **1200** / attempts 1200 / commit_fail 0 |
| auth_fail / flash_err | **0** / **0** |
| key_ver | **2** preserved |
| erase rotation | 9 events in pool B `0x001A0000`–`0x001AE000` |
| auto-stop | `complete=1`, `running=0` |

### Restart/resume proof (`resume_proof/`, delta=400)

1. Mid-run reset at quanta≈1954 (target 2271).
2. After reset: recovered **quanta=1971** (not zero); writer idle until host.
3. Host resumed **same** `run_metadata.json` target=2271 (no `--new-run`).
4. Completed exactly at **2271**.

### 1-hour pilot (`pilot_1h/`, delta=14400)

| Check | Result |
|-------|--------|
| start→final | 2271 → **16671** (exact +14400) |
| auth_fail / flash_err / erase_fail | **0** / **0** / **0** |
| erase events | 116, all in pool B `0x001Axxxx`, balanced across sectors 0–7 |
| mid-run host hang | LinkServer reset blocked probe; **host resume** re-armed same target at quanta 9559 → completed |
| auto-stop | `complete=1` at exact target |

Erase per-sector counts (pilot): B0–B7 ≈ 14–15 each.

### Full 525,600 run (`full/`)

- Started: start=16671 target=542271 on 3.7.0.
- **False FAIL** at ~7 min: `erase_event_overflow` — ring wrap counted overflow even when host had drained events (plan means “PC fell behind”).
- Fix: firmware 3.7.1 host-ack overflow + ring 256 (built; LinkServer probe hung so flash pending). Host now treats ovf bump as WARN + uses erase id-gap as hard fail.
- **Resumed** same absolute target without `--new-run`.

## PASS checklist (fill at closeout)

| Requirement | Status |
|-------------|--------|
| Exactly 525,600 new durable commits | |
| Zero target overshoot | |
| Zero quanta regression | |
| Zero unexpected journal re-init | |
| Zero AES-GCM auth failures | |
| Zero flash program/erase errors | |
| Zero lost RH key state | |
| Successful restart/resume | smoke+resume **PASS** |
| Correct sector rotation | smoke **PASS** (pool B walk) |
| Final reboot preserves target | |
| Production 600 s continues from final | |
| Zero CMPA/CFPA/IFR writes | **PASS** (not invoked) |

### Controlled reset (manual) during full run

| Field | Value |
|-------|-------|
| UTC | 2026-09-04T18:01:17Z |
| Method | LinkServer wiretimedreset |
| Pre quanta / seq | 47816 / 47822 |
| Pre commits_ok / erase_total / remap | 9 / 0 / 0 |
| Recovered quanta / seq | 47816 / 47822 |
| Target (unchanged) | 542271 |
| Resume rate (8s sample) | 4.125 cps |
| auth/flash/commit_fail / key_ver | 0 / 0 / 0 / 2 |

### Operator power-cycle during full run

Operator turned the board off, disconnected it, and reconnected it.

| Check | Result |
|-------|--------|
| Journal | Recovered mid-run (not from zero); quanta continued (~48315) |
| Absolute target | Still **542271** |
| Host | mTLS timeout, then automatic \RHSTRESS\ re-arm |
| auth/flash/commit / key_ver | 0 / 0 / 0 / 2 |
| Writer | running again toward same target |

