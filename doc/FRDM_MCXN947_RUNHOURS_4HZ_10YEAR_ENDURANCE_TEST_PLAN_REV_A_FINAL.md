# FRDM-MCXN947 Run-Hours Journal — 4 Hz / 10-Year-Equivalent Endurance Test Plan

**Revision:** A — Final  
**Purpose:** Fast, QA-only accelerated endurance qualification of the already-proven run-hours journal  
**Target unit:** DEV-UNIT-01  
**Scope:** Run-hours journal only; no secure-boot, OTA-layout, PFR, lifecycle, mTLS, or key-architecture redesign  
**Production run-hours quantum:** 600 s  
**Accelerated QA rate:** 4 durable commits/s (250 ms nominal period)  
**10-year-equivalent target:** 525,600 successful durable journal increments  
**Nominal laboratory duration:** 36 h 30 min, plus erase/recovery overhead

---

## 1. Current frozen baseline

The following implementation is considered **already proven and frozen** before this test starts:

- 512 KiB A/B secure OTA layout is proven in both flash-remap states.
- ROM secure boot, IFR MCUboot, MCUboot application signing, SB3.1, mTLS, and `CUST_MK_SK` are frozen.
- Run-hours journal uses the existing physical pools at:
  - `0x000A0000`
  - `0x001A0000`
- Existing pool sizes, sector geometry, record format, phrase-program logic, checkpoint migration, remap awareness, and flash arbiter **must not be changed for this endurance test**.
- Run-hours journal uses AES-256-GCM.
- Run-hours key architecture is frozen at **RH key version 2**:
  - NXP PSA/ELS opaque AES-256 key
  - key location `0xc00401` = `PSA_KEY_LOCATION_S50_RFC3394_STORAGE`
  - device-bound RFC3394 wrapped key blob stored in platform reserve
  - no PSA ITS
  - no raw AES key in Git, logs, `dist`, or normal application plaintext buffers after load
- v1→v2 migration was already proven value-preserving.
- Current production run-hours persistence quantum is **600 s**.

### Hard prohibition

This test must **not** write or modify:

- CMPA
- CFPA
- IFR
- lifecycle
- debug policy
- `CUST_MK_SK`
- SB3 provisioning
- MCUboot
- A/B slot geometry
- flash-remap configuration
- mTLS certificate/key architecture
- run-hours cryptographic key architecture

---

# 2. Test objective

Accelerate the real production journal write path sufficiently to execute the equivalent number of persistent run-hours commits expected in 10 years.

Production rate:

```text
1 durable increment / 600 s
= 6 increments/hour
= 144 increments/day
```

Ten years:

```text
6 × 24 × 365 × 10
= 525,600 durable increments
```

QA rate:

```text
4 durable increments/s
= one increment every 250 ms nominally
```

Nominal accelerated duration:

```text
525,600 / 4 = 131,400 s
                 = 36 h 30 min
```

**The acceptance target is count-based, not time-based.**

The test is complete only when exactly:

```text
525,600 successful new durable journal commits
```

have occurred relative to the test baseline.

---

# 3. Fundamental invariants

Throughout the test, all of the following must remain true.

## 3.1 Journal monotonicity

Let:

```text
Q0 = persisted quanta at the moment the endurance test is first armed
QT = Q0 + 525600
```

Then:

```text
Q0 <= current_quanta <= QT
```

The journal value must never decrease.

## 3.2 Exact stop

When the **successful committed** journal value reaches:

```text
current_quanta == QT
```

the QA endurance writer must stop immediately.

It must not intentionally write `QT + 1` or beyond.

## 3.3 Commit-before-authoritative

A quantum counts toward the endurance target only after the normal production journal path has completed its durable commit.

A failed/torn/uncommitted record must not increment the authoritative run-hours value.

## 3.4 Restart continuity

After reset or power loss:

```text
recover newest valid committed journal record
        ↓
current_quanta = recovered durable value
        ↓
continue toward the SAME absolute QT
```

The test must **never restart from Q0** after an MCU reboot.

## 3.5 No invented state

After any reset/power failure, the recovered value may be:

- the last fully committed value, or
- the next value if that record had completely committed before power loss,

but never:

- a fabricated value,
- an unauthenticated record,
- a lower value than the last known durable state,
- a jump beyond the number of successful durable commits.

---

# 4. QA-only implementation strategy

Do **not** modify the production `600000 ms` constant directly.

Add a clearly named build option:

```text
APP_RH_ENDURANCE_TEST=1
```

Production build:

```text
APP_RH_ENDURANCE_TEST=0
RH production quantum = 600 s
```

QA endurance build:

```text
APP_RH_ENDURANCE_TEST=1
nominal QA commit period = 250 ms
```

The release/build tooling must refuse to create a production release when `APP_RH_ENDURANCE_TEST=1`.

The QA firmware must print a conspicuous boot banner:

```text
*** QA RUN-HOURS ENDURANCE MODE ***
period_ms=250
production_quantum_s=600
target_delta=525600
NOT FOR PRODUCTION
```

---

# 5. Do not create a second journal implementation

The accelerated test must use the **same real production path**:

```text
run-hours service
    ↓
flash arbiter
    ↓
AES-256-GCM using RH key v2 / ELS opaque key
    ↓
existing journal record builder
    ↓
existing phrase programming
    ↓
existing commit transition
    ↓
existing sector rollover/checkpoint migration
```

Forbidden shortcuts:

- RAM-only simulated journal
- alternate test journal
- direct flash writes bypassing the journal API
- PC-driven `RHFORCE` four times per second
- bypassing AES-GCM
- bypassing flash arbitration
- special test-only erase algorithm

The point of the test is to stress the **actual production journal path**.

---

# 6. Exact stop/resume architecture

The test must survive MCU reset without requiring new persistent QA metadata in device flash.

Use an **absolute target quanta** controlled by the host monitor.

## 6.1 First start

The host performs `RHDIAG` and reads the current persisted value `Q0`.

It writes to `run_metadata.json` at minimum:

```json
{
  "start_quanta": Q0,
  "target_delta": 525600,
  "target_quanta": Q0 + 525600
}
```

The host then sends the QA-only command:

```text
RHSTRESS START <target_quanta>
```

The MCU stores `target_quanta` in RAM for the active boot session.

## 6.2 Device-side stopping rule

Before scheduling each increment:

```text
if current_quanta >= target_quanta:
    stress_running = false
    stress_complete = true
    do not create another journal record
```

After every successful journal commit, repeat the same check immediately.

Therefore the device itself stops at the exact target while that boot session is running.

## 6.3 After reset/power cycle

QA endurance mode must **not blindly begin writing immediately after boot**.

Instead:

1. boot normally;
2. recover RH key v2;
3. recover the newest valid journal record;
4. expose `RHDIAG` / mTLS diagnostics;
5. wait for the host monitor to reconnect;
6. host reloads the original `target_quanta` from `run_metadata.json`;
7. host reads current recovered `quanta`;
8. if `current_quanta < target_quanta`, send `RHSTRESS START <same target_quanta>`;
9. if `current_quanta >= target_quanta`, do **not** re-arm the writer; mark the run COMPLETE.

This gives exact restart continuity without consuming another device flash region for test-control metadata.

## 6.4 Host monitor restart

The host monitor itself must also be restartable.

On startup:

- if no `run_metadata.json` exists, create a new test baseline;
- if it exists, reuse the original `start_quanta`, `target_quanta`, and test UUID;
- query the MCU;
- verify UUID matches;
- continue from the current durable journal value;
- never create a new baseline accidentally.

Require an explicit operator option such as `--new-run` before overwriting an existing unfinished run.

---

# 7. Timing implementation

Use `vTaskDelayUntil()` with a nominal period of **250 ms**.

However:

> **successful durable commits are authoritative; wall-clock ticks are not.**

If flash erase/checkpoint work causes a 250 ms deadline miss:

```text
stress_deadline_miss++
```

Do not perform burst “catch-up” writes.

Continue with the next normal iteration.

This prevents one long erase from creating an unrealistic series of back-to-back flash operations.

---

# 8. Required QA diagnostics

Maintain RAM counters at minimum:

```text
stress_running
stress_complete
stress_start_boot_quanta
stress_target_quanta
stress_attempts
stress_commits_ok
stress_commit_fail
stress_deadline_miss
journal_record_seq
journal_auth_fail
journal_torn_recovery
journal_flash_error
erase_total
erase_fail_total
ota_deferred_count
remap_state
uptime_s
```

Also expose:

```text
key_ver
key_id
key_state
```

to prove RH key v2 remains active.

Do not expose key material or wrapped-key contents.

---

# 9. Erase instrumentation

The PC must be able to see when an erase block/sector was erased.

Instrument the **existing low-level journal erase path**.

Do not add a second erase implementation.

For every erase attempt capture:

```text
erase_event_id
uptime_ms
physical_address
pool
sector_index
erase_result
sector_erase_count
erase_total
record_seq
quanta
remap_state
```

Example:

```text
RHERASE id=27 addr=0x000A6000 pool=A sector=3 count=4 total=27 seq=18442 quanta=18582 remap=0 result=OK
```

## 9.1 Erase-event storage

Erase event history must be **RAM-only**.

Do not write a flash log of erase events because that would contaminate the endurance measurement.

Use a bounded RAM ring, for example 64 or 128 events.

Maintain:

```text
erase_event_overflow
```

If the PC falls behind, overflow is visible and treated as a test-instrumentation failure.

---

# 10. Ethernet reporting

Reuse the existing **mTLS TCP :5000** service.

Do not add a new network service.

All stress commands are compiled only when `APP_RH_ENDURANCE_TEST=1`.

Recommended QA commands:

```text
RHSTRESS START <absolute_target_quanta>
RHSTRESS STATUS
RHSTRESS STOP
RHERASE <last_event_id>
```

`RHSTRESS STATUS` returns a compact summary, for example:

```text
RHSTRESS mode=4HZ running=1 complete=0 quanta=18320 target=525740 commits_ok=18180 attempts=18180 commit_fail=0 deadline_miss=2 erase_total=21 erase_fail=0 auth_fail=0 flash_err=0 key_ver=2 key_id=1 remap=0 uptime_s=4548
```

`RHERASE <last_event_id>` returns a bounded number of erase events newer than the supplied event ID.

If more events remain, return `MORE=1` and the PC immediately requests another batch.

This avoids large `:5000` responses.

---

# 11. PC monitor

Add:

```text
python tools/mcxn.py rh-stress-monitor
```

or an equivalent standalone script that reuses the existing mTLS host library.

Default behavior:

```text
poll/report every 60 s
```

## 11.1 Every minute

The monitor must:

1. connect over mTLS `:5000`;
2. request `RHSTRESS STATUS`;
3. verify UUID;
4. verify journal monotonicity;
5. verify target did not change;
6. retrieve all new erase events using `RHERASE`;
7. update machine-readable logs;
8. print one concise human-readable report.

Example:

```text
[01:00]
quanta=380
delta=240/525600
rate=4.000 commits/s
erase_total=0
commit_fail=0
auth_fail=0
flash_err=0
deadline_miss=0
equivalent_days=1.67

[02:00]
quanta=620
delta=480/525600
rate=4.000 commits/s
ERASE id=1 addr=0x000A0000 pool=A sector=0 count=1
erase_total=1
errors=0
```

---

# 12. Host result files

Create a dedicated directory:

```text
C:\mcxn\builds\rh_endurance_4hz\
```

Recommended files:

```text
run_metadata.json
minute_status.jsonl
erase_events.jsonl
monitor_events.jsonl
console.log
final_summary.json
```

## 12.1 `run_metadata.json`

Record:

- unit ID
- silicon UUID
- firmware version
- Git commit
- SDK/tool versions
- RH key version
- start UTC/local timestamp
- `start_quanta`
- `target_delta = 525600`
- `target_quanta`
- production quantum = 600 s
- QA period = 250 ms

## 12.2 Minute status

Record at minimum:

- timestamp
- uptime
- quanta
- delta commits
- target remaining
- attempts
- commits OK
- commit failures
- average commit rate
- deadline misses
- record sequence
- erase total
- erase failures
- auth failures
- torn recoveries
- flash errors
- remap state
- key version/state
- mTLS monitor errors

---

# 13. Equivalent production-time reporting

Use:

```text
equivalent_seconds = durable_test_commits × 600
```

Then report equivalent days and years.

Useful milestones:

```text
52,560 commits  = 1 production year
262,800 commits = 5 production years
525,600 commits = 10 production years
```

The host should explicitly print milestone events:

```text
MILESTONE: 1-year equivalent reached
MILESTONE: 5-year equivalent reached
MILESTONE: 10-year equivalent reached
```

---

# 14. Automatic failure conditions

The monitor must mark the run FAILED and stop further stress writes where practical if any of the following occur:

- `quanta` decreases
- journal sequence decreases unexpectedly
- target quanta changes
- `current_quanta > target_quanta`
- AES-GCM authentication error
- nonce/IV reuse detected
- flash phrase-program error
- erase error
- journal unexpected reinitialization
- wrapped RH key unavailable/corrupt
- RH key version unexpectedly changes
- persistent record cannot be recovered after reset
- erase-event ring overflows
- repeated mTLS monitor failure indicating MCU/network lockup
- unexpected watchdog reset/assert/HardFault
- device UUID changes/mismatch
- wrong firmware image unexpectedly boots

On a failure, preserve the board state and logs for diagnosis.

Do not automatically wipe/reformat the journal.

---

# 15. Pilot tests before the full run

Do not start the 36.5-hour run immediately.

## 15.1 Five-minute smoke

Expected:

```text
5 min × 60 × 4 = approximately 1,200 commits
```

Check:

- monotonic quanta
- correct commit count
- no auth/flash error
- mTLS report works
- erase-event reporting works if an erase occurs

Then:

- reset the MCU;
- verify journal recovery;
- verify the host monitor resumes toward the original absolute target.

For the smoke, use a separate small target so it can finish cleanly.

## 15.2 One-hour pilot

Expected:

```text
approximately 14,400 durable commits
```

Check:

- sector rollover/checkpoint activity
- erase distribution
- no memory/resource leak
- no increasing error trend
- restart/resume once during the pilot

Only after this pilot passes should the full run begin.

---

# 16. Full 10-year-equivalent execution

Start a fresh run.

The host records:

```text
Q0
QT = Q0 + 525600
```

Arm:

```text
RHSTRESS START QT
```

Then let the test run until the device reports:

```text
current_quanta == QT
stress_complete=1
stress_running=0
```

Nominal runtime:

```text
~36 h 30 min
```

Actual runtime may be slightly longer because sector erases, checkpoint migration, and missed periods are not caught up with burst writes.

That is acceptable.

**Do not stop based only on elapsed laboratory time.**

Stop only when:

```text
successful durable delta == 525600
```

---

# 17. Restart/resume qualification during full run

The full run should include at least several controlled MCU resets.

Recommended milestones:

- around 5%
- around 25%
- around 50%
- around 75%

For each reset:

1. leave the host test metadata intact;
2. reset MCU;
3. wait for boot;
4. host reconnects automatically;
5. read recovered `quanta`;
6. verify it is monotonic;
7. re-arm with the **same original absolute target `QT`**;
8. continue.

At least one restart should be close to an erase/checkpoint event if practical.

Optional physical power cuts may be added, but this endurance test does not replace the already-passed Gate-10 power-fail campaign.

---

# 18. Erase-distribution analysis

At the end of the run calculate, for each actual journal erase sector used by the current implementation:

```text
physical address
pool
sector index
successful erase count
failed erase count
first erase event
last erase event
```

Verify:

- sector rotation follows the designed journal policy;
- no sector is being unexpectedly hammered;
- no erase occurs outside approved journal/platform ranges;
- active/remapped bank rules remain correct;
- checkpoint migration occurs as designed.

Do not assume perfectly equal counts if the production bank-aware algorithm intentionally favors one pool depending on remap state.

---

# 19. Final recovery test

After the exact target is reached:

```text
stress_running=0
stress_complete=1
```

Record final diagnostics.

Then:

1. reset the MCU;
2. do **not** re-arm stress;
3. verify the journal recovers exactly `final_quanta == target_quanta`;
4. wait several minutes and confirm the QA stress writer remains stopped;
5. confirm `RHDIAG` reports:
   - key version 2
   - correct key ID/state
   - no journal corruption
   - correct final quanta.

The final stress value must survive restart.

---

# 20. Optional post-endurance OTA regression

After endurance completion, perform one strictly newer secure mTLS/SB3 OTA.

Verify:

- OTA succeeds;
- run-hours journal is not erased;
- recovered quanta remains exactly at the endurance target unless a separately authorized production-mode increment legitimately occurs;
- RH key version 2 remains valid;
- A/B remap may change but logical journal state remains continuous.

Do not perform a downgrade as an acceptance test.

---

# 21. Restore production firmware

After all endurance evidence has been collected:

1. build a normal production image with `APP_RH_ENDURANCE_TEST=0`;
2. verify the QA commands are absent/disabled;
3. verify production cadence is exactly **600 s**;
4. flash/update to the production build;
5. confirm normal run-hours counting resumes **from the final persisted journal state**, not from zero.

This is an explicit requirement:

> The accelerated test must not destroy the accumulated journal. Once the production firmware is restored, normal 600-second run-hours counting must continue from the last valid value produced by the endurance test.

If the product policy later chooses to reset test-unit run-hours before shipment, that must be a separate explicit factory operation. It is not part of this endurance plan.

---

# 22. Acceptance criteria

The full endurance test passes only if all mandatory criteria are satisfied.

| Criterion | PASS requirement |
|---|---:|
| Durable accelerated increments | **Exactly 525,600 new commits** |
| Final quanta | `start_quanta + 525600` |
| Overshoot beyond target | **0** |
| Unexpected quanta regression | **0** |
| Unexpected journal re-init | **0** |
| AES-GCM auth failures | **0** |
| Nonce/IV reuse | **0** |
| Phrase-program errors | **0** |
| Erase errors | **0** |
| Lost key blob / key recovery failures | **0** |
| Unrecoverable restart | **0** |
| Erase outside approved journal ranges | **0** |
| Permanent mTLS diagnostic loss | **0** |
| HardFault/assert/watchdog reset caused by journal | **0** |
| Restart/resume from last durable state | **PASS** |
| Final reboot retains target value | **PASS** |
| Production 600-s build continues from final state | **PASS** |
| CMPA/CFPA/IFR writes | **0** |

`stress_deadline_miss` may be non-zero if bounded and explained by erase/checkpoint timing. It must be reported but does not automatically fail the endurance test.

---

# 23. Required final evidence

Create:

```text
docs/evidence/RUNHOURS_4HZ_10YEAR_ENDURANCE.md
```

Include:

- firmware commit/version
- SDK/tool versions
- UUID
- RH key version and key ID
- starting quanta
- target quanta
- final quanta
- successful commit count
- laboratory duration
- equivalent production years
- total phrase programs if available
- total sector erases
- per-sector erase table/histogram
- maximum erase count on any sector
- erase failures
- AES-GCM/auth failures
- torn-record recoveries
- deadline misses
- MCU resets/power cycles performed
- each restart recovered value
- host mTLS polling statistics
- final reboot result
- optional post-endurance OTA result
- production-mode restore result
- confirmation that protected security state was untouched

Also keep the raw:

```text
run_metadata.json
minute_status.jsonl
erase_events.jsonl
final_summary.json
```

as attachments/evidence.

---

# 24. Agent execution sequence

Proceed autonomously through:

```text
instrumentation
→ host monitor
→ unit tests
→ 5-minute smoke
→ reset/resume proof
→ 1-hour pilot
→ full 525,600-commit run
→ final reboot
→ optional newer OTA
→ restore production build
→ evidence report
```

Stop only for:

- a genuine irreversible/protected-state write requirement;
- journal corruption;
- flash error;
- key-loss condition;
- unexplained erase outside approved range;
- failure to recover the last durable state.

Do not redesign a proven subsystem merely to improve test convenience.

---

## Final test definition

**This test simulates 10 years of production journal commit count, not 10 years of calendar aging or flash retention.**

It validates:

- journal write endurance behavior
- repeated AES-GCM use
- phrase programming
- sector erase/rotation
- checkpoint migration
- restart continuity
- exact stop behavior
- mTLS observability
- continuation from the last durable state

It does **not** replace separate retention, temperature, battery-life, or long-term environmental qualification.
