# Technician update runbook (P6)

## What you need

From `dist/<unit>/<version>/`:

| File | Purpose |
|------|---------|
| `*.sb3` | Unit-encrypted SB3.1 package |
| `*.sb3.manifest.json` | Sidecar (UUID, version, SHA-256) |
| `README_TECHNICIAN.txt` | This flow summary |

Board: FRDM-MCXN947 on `192.168.2.90`, Hello `:5000`, update `:5555` (first **180 s** after app boot).

## Update

```text
cd c:\temp\mcxn947Test
python tools/mcxn.py doctor
python tools/mcxn.py status          # confirm UUID + update_window_s > 0
python tools/mcxn.py update --sb3 dist/DEV-UNIT-01/2.0.0/DEV-UNIT-01_2.0.0_V2.sb3
```

Expect `UPDATE PASS` and STATUS `variant=V2` (for a 2.x package).

The CLI will **refuse** before transfer if:

- sidecar missing/corrupt
- SB3 SHA-256 ≠ manifest
- device UUID ≠ package `target_uuid`
- update window closed
- device unreachable

Device SB3 crypto (`CUST_MK_SK`) remains the security boundary; host UUID check is operator safety.

## After update

```text
python tools/mcxn.py status
python tools/mcxn.py hello
```

## Recovery

If the board does not boot the new image: `docs/runbooks/recover.md` (restore signed V1 via LinkServer). Do not re-provision keys for a normal failed transfer.
