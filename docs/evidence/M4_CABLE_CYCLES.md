# M4 Ethernet link / cable-cycle evidence

**Board:** DEV-UNIT-01 (`192.168.2.90`), mTLS `:5000`  
**Date:** 2026-09-03

## Automated NIC disable (lab PC) — blocked

`tools/m4_reliability.py link` / `Disable-NetAdapter` failed with **Access is denied** (Windows admin required).  
Artifact: `docs/evidence/M4_link.json`.

No further time spent fighting Windows permissions.

## Accepted approach

Per plan: perform **manual physical Ethernet cable unplug/replug** cycles, or document the administrative limitation and a reasonable manual sample.

### Operator procedure (manual sample)

For each cycle (target 20 when operator available):

1. Confirm baseline: `python tools/mcxn.py hello` succeeds on `:5000`.
2. Unplug board Ethernet cable ~5–10 s (link-down).
3. Replug; wait until ping to `192.168.2.90` recovers (typically &lt;30 s).
4. Confirm `python tools/mcxn.py hello` succeeds **without MCU reboot / LinkServer reset**.
5. Record cycle N: recovered yes/no, time-to-hello.

Recovery criterion: session cleaned up on link loss; Hello resumes automatically after link-up. **No MCU reboot required.**

### Sample status

| Item | Status |
|------|--------|
| Windows NIC script | **Blocked** (Access denied) — see `M4_link.json` |
| Physical cable cycles | **Deferred until after 24 h soak** (do not disturb board during soak) |
| Precondition | QA soak image on board; run cycles after soak ends (see `M4_POST_SOAK_PLAN.md`) |

When an operator completes N cycles, append results below (or replace this section) and update `M4_RELIABILITY.md`.

### Manual results log

| Cycle | Unplug duration (s) | Ping recover (s) | Hello recover | MCU reboot used? |
|------:|--------------------:|-----------------:|:-------------:|:----------------:|
| — | — | — | pending operator | — |
