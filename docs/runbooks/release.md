# Release runbook (P6)

Host-only workflow. Firmware architecture and OTAS/TCP:5555 protocol are frozen.

## Prerequisites

```text
python tools/mcxn.py doctor   # must print DOCTOR PASS
```

Secrets remain at `C:\mcxn-secrets\<unit>\` (never in git / never in `dist/`).

## One-shot release

```text
cd c:\temp\mcxn947Test
python tools/mcxn.py release --unit DEV-UNIT-01 --version 2.0.0
```

Produces:

```text
dist/DEV-UNIT-01/2.0.0/
  DEV-UNIT-01_2.0.0_V2.sb3
  DEV-UNIT-01_2.0.0_V2.sb3.manifest.json
  README_TECHNICIAN.txt
```

Manifest includes unit UUID, firmware version, SB3 SHA-256, creation time (UTC), tool versions, and git commit. `cust_mk_sk_fingerprint` only — not the key.

## Step-wise

```text
python tools/mcxn.py build v2 --version 2.0.0
python tools/mcxn.py package --unit DEV-UNIT-01 --version 2.0.0
```

## Unit registry

Committed non-secret: `units/DEV-UNIT-01.json`  
Fingerprint must match `SHA-256(CUST_MK_SK bytes)` under secrets.

## Do not

- Copy `*.pem`, `cust_mk_sk.hex`, or SEC workspace keys into `dist/`
- Change CMPA/CFPA/`CUST_MK_SK`/lifecycle during packaging
- Invent a new wire protocol (OTAS remains)
