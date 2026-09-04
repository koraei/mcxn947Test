# FRDM-MCXN947 512 KiB A/B + Encrypted Running-Hours Journal Test Plan

**Document:** Implementation and qualification plan — Rev B FINAL  
**Target:** NXP FRDM-MCXN947 / MCXN947  
**Repository:** `koraei/mcxn947Test`  
**Baseline:** latest clean state containing the currently proven secure boot + SB3 OTA + FreeRTOS/lwIP + mTLS Hello/STATUS/update functionality; currently this is represented by `feat/mtls-tcp-socket`, but the agent MUST first check for newer local/unpushed reliability work before branching.  
**Proposed branch:** `feat/512k-ab-encrypted-runhours`
**Rev B focus:** safe mbedTLS/PSA footprint reduction while preserving all current security, reliability, performance, IPv4 and IPv6 behavior  
**Purpose:** Test a new 2 MiB internal-flash layout with 512 KiB A/B firmware slots, 256 KiB platform reserve, 128 KiB encrypted power-fail-safe running-hours journal, and 640 KiB reserved for future event/maintenance logs, while preserving current secure boot, SB3 secure update, mTLS, Ethernet, FreeRTOS, Hello/STATUS, and update behavior.

---


## Rev B final-review changes

Rev B keeps the Rev A flash/journal architecture but strengthens the firmware-size phase. The current mTLS image is too large for a 512 KiB slot, and the reduction must not be obtained by weakening the product. Rev B therefore makes the following changes mandatory:

1. **Branch from the latest locally-qualified reliability state, not blindly from the remote GitHub branch.** Preserve any completed soak/QA-stream/reconnect work that exists locally but is not yet pushed.
2. **Preserve both IPv4 and IPv6.** `LWIP_IPV4=1` and `LWIP_IPV6=1` are release invariants. Do not disable IPv6 for size.
3. **Preserve the existing TLS security properties:** mutual certificate authentication, CA validation, exact device fingerprint check on the host, no plaintext fallback, ECDSA P-256 certificates, SHA-256, forward-secret ECDHE, AES-GCM, TLS >=1.2, bounded handshake/timeouts, and SB3 remaining independently mandatory for updates.
4. **Use a custom product Mbed TLS configuration rather than NXP's broad default profile.** Keep the SDK itself unmodified.
5. **Use NXP's PSA fine-grained crypto configuration and ELS/PKC acceleration where the pinned SDK proves support.** Software fallbacks may be removed only when the driver-only build is explicitly supported for that primitive.
6. **Remove unused cryptographic/protocol features by allow-list, not by guesswork.** RSA, finite-field DH, PSK, DTLS, TLS session tickets/resumption, 0-RTT, ALPN, SNI, unused curves, unused ciphers and certificate-writing tooling are candidates because the current product does not use them.
7. **Keep TLS 1.2 and TLS 1.3 initially.** TLS 1.3-only is an owner-approved fallback only if the otherwise-equivalent profile still cannot meet the slot target. It is not an automatic size optimization.
8. **Convert embedded credentials from PEM to DER** after proving certificate/key fingerprints are unchanged. This can remove Base64/PEM parsing without changing trust semantics.
9. **Do not shrink TLS record buffers, lwIP TCP windows, pbufs or task stacks merely to save flash.** Those changes target RAM and can reduce throughput/reliability. Any such change requires separate measured justification.
10. **Preserve performance:** the optimized build must remain within 5% of the qualified streaming throughput and must pass the existing reconnect/negative-certificate/update tests plus the long soak.
11. **Preserve diagnostics semantically.** Large debug strings/full formatted console support may be replaced by compact production diagnostics only after equivalent counters/status visibility exists.
12. **No PFR/CMPA change until the fully optimized current-feature image fits with margin and passes the complete regression suite.**

---
## 1. Executive decision

The proposed memory architecture is **physically compatible with MCXN947 flash geometry and flash-remap capabilities**, with one major implementation blocker that MUST be resolved before any layout or CMPA change:

> **The last proven mTLS firmware does not fit a 512 KiB slot.** The recorded debug build used approximately 784 KiB of `m_text` out of approximately 798 KiB. Therefore this project starts with a mandatory size-reduction gate. No CMPA/remap modification and no 512 KiB flashing is allowed until the complete signed firmware fits the new slot with margin.

The storage architecture itself is suitable:

- MCXN947 has 2 MiB internal program flash in two 1 MiB banks.
- FRDM-MCXN947 MCUboot uses the hardware **SWAP** remap mechanism.
- `FLASH_REMAP_SIZE` controls only the address range that participates in remap in 32 KiB increments.
- A 512 KiB remap therefore uses `FLASH_REMAP_SIZE = 15`, because `(15 + 1) × 32 KiB = 512 KiB`.
- The upper 512 KiB of each 1 MiB bank can therefore remain outside the A/B swap window and be used as fixed-address shared storage.
- Flash erase sector size is 8 KiB.
- Flash change/program block size is 16 bytes.
- MCUboot itself remains in the separate 32 KiB IFR region at `0x01008000..0x0100FFFF`; the 256 KiB “platform reserve” in the map below is therefore main-flash reserve, not the bootloader itself.

This is a controlled experimental branch. It MUST NOT be merged into the frozen baseline until every gate in this document passes.

---

## 2. Current baseline that must remain functional

The agent must preserve these current capabilities unless a test specifically proves otherwise:

1. ROM secure boot of the IFR MCUboot image.
2. Existing production/test Root-of-Trust hash and secure-boot configuration.
3. Existing `CUST_MK_SK` and SB3.1 provisioning material.
4. MCUboot DIRECT_XIP / flash-SWAP behavior.
5. FreeRTOS.
6. lwIP Ethernet with the current static network policy.
7. **Both IPv4 and IPv6 enabled in lwIP.** IPv6 must not be traded away for footprint.
8. mTLS server on the existing Hello/STATUS service.
9. mTLS-protected SB3 update service.
10. Existing client-certificate, CA and server-identity checks.
11. Hello/ECHO behavior and STATUS behavior.
12. Existing update-window, timeout and negative-update behavior.
13. Existing host CLI/tooling and unit registry semantics unless this plan explicitly extends them.
14. No weakening of secure boot, mTLS authentication, SB3 authentication, signing keys, or update authorization in order to meet the size goal.

Current evidence in the repository records:

- MCUboot signed MBI size: 24,768 bytes; fits the 32 KiB IFR slot.
- Secure boot enabled; RoTKH verified; `CUST_MK_SK` intact.
- mTLS Hello/STATUS and mTLS SB3 OTA are proven.
- Last recorded mTLS debug map: `m_text ~784 KB / 798 KB (~96%)`, `m_data ~184 KB / 312 KB`.

The last item is the mandatory reason for Phase M1 below.

---

## 3. Proposed main-flash map

### 3.1 Exact address map

All boundaries below are both 8 KiB erase-sector aligned and compatible with a 512 KiB remap window.

```text
MCXN947 Program Flash: 0x00000000 .. 0x001FFFFF = 2 MiB

BANK 0: 0x00000000 .. 0x000FFFFF = 1 MiB

0x00000000 .. 0x0007FFFF   512 KiB   Firmware Slot A / Primary remap region
0x00080000 .. 0x0009FFFF   128 KiB   Platform Reserve A
0x000A0000 .. 0x000AFFFF    64 KiB   Running-Hours Journal Pool A
0x000B0000 .. 0x000FFFFF   320 KiB   Future Event/Maintenance Log Pool A

BANK 1: 0x00100000 .. 0x001FFFFF = 1 MiB

0x00100000 .. 0x0017FFFF   512 KiB   Firmware Slot B / Secondary remap region
0x00180000 .. 0x0019FFFF   128 KiB   Platform Reserve B
0x001A0000 .. 0x001AFFFF    64 KiB   Running-Hours Journal Pool B
0x001B0000 .. 0x001FFFFF   320 KiB   Future Event/Maintenance Log Pool B

Separate IFR:
0x01008000 .. 0x0100FFFF    32 KiB   Existing MCUboot; unchanged unless a reviewed
                                      bootloader rebuild is required for slot geometry
```

### 3.2 Totals

```text
Firmware A/B           1024 KiB
Platform reserve        256 KiB
Running-hours journal   128 KiB
Future event/log pool    640 KiB
                       --------
Program flash total     2048 KiB
```

### 3.3 Why the shared storage remains stable across A/B swaps

Configure flash remapping for only the first 512 KiB of each bank. The hardware SWAP therefore applies to:

```text
0x00000000 .. 0x0007FFFF
<->
0x00100000 .. 0x0017FFFF
```

The regions beginning at `0x00080000` and `0x00180000` remain outside the remapped address range. The running-hours and event-log partitions therefore retain fixed logical addresses regardless of whether firmware A or firmware B is active.

This invariant MUST be proved on hardware before the journal is enabled for qualification.

---

## 4. Hard sizing policy

### 4.1 512 KiB is the physical slot, not the allowed firmware target

The slot is exactly:

```text
0x80000 = 524,288 bytes = 512 KiB
```

The release image must also accommodate the MCUboot header/trailer and any format overhead required by the existing DIRECT_XIP flow.

### 4.2 Required size gates

The agent must establish the exact current signed-image geometry from the actual build/link/sign commands. Do not rely only on stale comments in a linker script.

Preferred target:

```text
loadable application flash content <= 400 KiB
```

Hard signed-image gate for this experiment:

```text
signed/padded image + required trailer < 512 KiB
```

Recommended additional margin gate:

```text
signed image <= 448 KiB (0x70000)
```

This leaves at least 64 KiB of physical slot margin for metadata/growth and avoids operating at the absolute edge of the partition.

### 4.3 STOP condition

If all current features cannot be retained while meeting the 512 KiB slot gate:

- STOP before any CMPA change.
- Do not disable mTLS, SB3 authentication, secure boot, certificate validation, update checks, FreeRTOS, lwIP or required diagnostics simply to fit.
- Produce a size-attribution report.
- Propose the smallest larger remap/slot size that solves the problem, for owner review. Because remap is programmable in 32 KiB increments, 640 KiB, 704 KiB, 768 KiB, etc. can be evaluated without abandoning the overall fixed-storage concept.

### 4.4 Security/reliability/performance equivalence contract

The optimized image is acceptable only if all of the following remain true:

```text
Secure boot:            unchanged ROM -> IFR MCUboot -> signed app chain
Firmware update:        SB3.1 remains mandatory and independently authenticated
Transport security:     mTLS only; no plaintext fallback
Client authentication:  certificate REQUIRED
Certificate trust:      project CA validation remains mandatory
Host device identity:   exact stored server-certificate fingerprint remains mandatory
Certificate algorithm:  ECDSA P-256 / SHA-256
Key exchange:           ECDHE (forward secrecy)
Record protection:      AES-GCM only in approved profile
TLS versions:           TLS 1.2 + TLS 1.3 initially
IPv4:                   enabled
IPv6:                   enabled
FreeRTOS/lwIP:          unchanged task/socket architecture
OTA window:             unchanged
Hello/ECHO/STATUS:      unchanged application semantics
DAQ-stream performance: no >5% regression from qualified baseline
```

Do not claim equivalence from successful compilation. The complete negative/soak/update matrix in M1 and M10 is the proof.

---

## 5. Running-hours semantics

### 5.1 What is counted

For this test, **running hours means powered application operating time after normal application initialization completes**, independent of Ethernet link state.

Do not use RTC wall-clock time as the authoritative source. Use monotonic FreeRTOS/runtime tick accumulation.

The production interval is:

```text
10 minutes = 600 seconds
```

Every completed 10-minute interval appends one new durable journal record.

### 5.2 Initial record

At first provisioning of a truly virgin journal region, write a valid initial record:

```text
record_seq      = 0
runtime_quanta  = 0
total_seconds   = 0
record_type     = INITIAL
```

**Critical rule:** Do not create a new zero-hour record merely because no valid record was found.

On boot:

- If the entire 128 KiB region is erased/virgin, initialization to zero is allowed.
- If any journal bytes are non-erased but there is no valid authenticated record, report `RUNHOURS_JOURNAL_CORRUPT` and stop automatic reinitialization.

This prevents corruption or battery removal/power cycling from silently resetting accumulated running hours to zero.

### 5.3 Accuracy at unexpected power loss

This journal records completed 10-minute operating intervals. An unexpected total power failure can therefore lose up to the current uncommitted interval (<10 minutes).

For a maintenance running-hours meter this is normally acceptable.

If the same counter later becomes a commercial licensing meter where deliberate reset abuse must never provide free time, use **prepaid 10-minute quanta** as a separate policy: persist the next quantum before allowing that quantum of licensed operation. Do not silently change this maintenance counter to prepaid semantics in this test.

---

## 6. Journal geometry and endurance

### 6.1 Physical geometry

Running-hours area:

```text
128 KiB / 8 KiB = 16 erase sectors
```

Use eight sectors in Bank 0 and eight sectors in Bank 1.

Use 64-byte sector headers and 64-byte physical journal records.

Per sector:

```text
8192 - 64 = 8128 bytes for records
8128 / 64 = 127 record slots
```

The 64-byte record is intentionally four 16-byte flash program/change blocks.

### 6.2 Ring capacity

Ignoring one carry-forward checkpoint per sector transition, the physical capacity is:

```text
16 sectors × 127 slots = 2032 records
```

At one logical runtime record every ten minutes, a complete ring represents roughly:

```text
2032 × 10 min = 20,320 min = 338 h 40 min ≈ 14.1 days
```

A specific sector is therefore erased roughly once per complete ring circulation, not every time a record is written.

Approximate sector erase count under continuous 24/7 operation:

```text
10 years: 87,600 h / ~336-339 h ≈ 259-261 erases per sector
20 years: approximately 518-522 erases per sector
```

This is extremely modest for program flash. The qualification report must still cite the exact endurance limits from the MCXN947 datasheet revision used by the project.

---

## 7. Encrypted/authenticated record design

### 7.1 Do not use CRC as the security primitive

CRC may be used for non-secret structural metadata such as sector headers, but running-hours records must be protected with an authenticated-encryption algorithm.

Use:

```text
AES-256-GCM
128-bit authentication tag
96-bit unique nonce
```

Use NXP-supported EdgeLock/ELS cryptography. Do not introduce custom AES/GCM code.

### 7.2 Journal key

Create a dedicated device-specific journal key:

```text
K_RH = Running-Hours Journal Key
```

Requirements:

- 256 bits.
- Unique to the physical device.
- Never stored plaintext in Git, the firmware image, configuration files or host tooling.
- Not the secure-boot signing key.
- Not the SB3 update key.
- Not `CUST_MK_SK` directly.
- Domain-separated for running-hours use only.

Preferred implementation:

1. Use the MCXN947 PUF/EdgeLock-supported key-storage flow.
2. Generate or inject a random 256-bit `K_RH` once.
3. Convert/store it using an NXP-supported PUF key-code / wrapped-key mechanism so the persistent blob is device-bound and is useless when copied to another MCU.
4. Recover/load the key only when required for AES-GCM operations, ideally into an ELS-protected key slot or the narrowest practical secure/transient context.
5. Zeroize any plaintext transient key material after use.

If the SDK does not provide a clean supported path for this without disturbing the existing secure-boot/SB3 material, STOP and document the API/capability gap. Do not improvise a static compiled key.

### 7.3 Deterministic GCM nonce derivation

Use a deterministic 96-bit GCM nonce whose uniqueness follows directly from the journal state machine:

```text
nonce[0..7]  = encode_be64(sector_generation)
nonce[8..11] = encode_be32(record_slot_index)
```

AES-GCM requires nonce **uniqueness** for a given key; unpredictability is not required. This construction is preferred over a random sector nonce because it is easier to prove under reset/power-cut testing and has no collision probability.

Rules:

- `sector_generation` is 64-bit and strictly increases whenever a sector is prepared for a new lifetime.
- The active/latest sector is never erased before a new higher-generation sector is READY and contains an authenticated checkpoint, so the maximum generation can always be recovered.
- A physical record slot is never rewritten after any program attempt, even if the prior attempt was torn.
- Record slot indices are never reused within one sector generation.
- Generation wrap is treated as a terminal fault; it is practically unreachable.
- Any authorized full journal reset must also rotate `K_RH` or otherwise advance a separately preserved journal epoch; never restart generation at zero under the same key.
- GCM nonce reuse under the same key is a release blocker.

### 7.4 Sector header — 64 bytes

Suggested logical fields:

```text
magic                   32 bit   "RHS1"
format_version          16 bit
header_size             16 bit
sector_id               16 bit
reserved                16 bit
sector_generation       64 bit   // also forms nonce high 64 bits
created_boot_id         32 bit
header_crc32            32 bit
reserved/padding
ready_marker            128 bit  final 16-byte phrase
```

The exact binary layout must be frozen in `runhours_format.h` with compile-time size/alignment assertions.

The `ready_marker` phrase is programmed last. A sector header without an exact valid ready marker is not eligible to receive or contribute records.

### 7.5 Running-hours record — exactly 64 bytes

Suggested physical structure:

**Phrase 0 — public/authenticated metadata (16 bytes)**

```text
magic/version/type
record_seq              64-bit or equivalent packed representation
```

**Phrase 1 — encrypted payload (16 bytes)**

Example plaintext before encryption:

```text
runtime_quanta          uint64_t   // total completed 10-minute quanta
flags                   uint32_t
boot_id_low             uint32_t
```

`total_running_seconds = runtime_quanta × 600` can be derived and does not need duplicate storage.

**Phrase 2 — AES-GCM authentication tag (16 bytes)**

```text
GCM tag                 128 bit
```

**Phrase 3 — commit phrase (16 bytes)**

Suggested fields:

```text
commit_magic            64 bit
record_seq_complement   64 bit
```

The final exact format may differ, but these invariants MUST remain:

- Runtime value is ciphertext, not plaintext.
- Record sequence and physical placement are included in AES-GCM AAD.
- GCM tag authenticates the ciphertext and metadata.
- Commit phrase is the final flash programming operation.
- The commit phrase must match exactly before a record is considered valid.

### 7.6 AAD

At minimum authenticate:

```text
format version
record type
record_seq
sector_generation
sector physical ID/address
record slot index
```

This prevents an otherwise valid ciphertext/tag pair from being moved to a different logical position without detection.

---

## 8. Atomic record append protocol

For every new record:

```text
1. Locate next completely erased 64-byte record slot.
2. Build metadata and encrypted payload in RAM.
3. AES-GCM encrypt payload and produce tag.
4. Program phrase 0.
5. Read back phrase 0 and verify.
6. Program phrase 1.
7. Read back phrase 1 and verify.
8. Program phrase 2.
9. Read back phrase 2 and verify.
10. Reconstruct/decrypt/authenticate the not-yet-committed record from flash.
11. Only if all prior checks pass, program phrase 3: COMMIT.
12. Read back commit phrase.
13. Re-read and fully authenticate the completed flash record.
14. Publish the new in-RAM authoritative total only after step 13 passes.
```

A failure at steps 4–10 leaves the commit phrase erased and the slot invalid.

A reset/power cut while programming the commit phrase produces either:

- an invalid/torn commit phrase -> previous record remains authoritative; or
- a completely valid commit phrase -> all earlier phrases were already written and read-back verified, so the new record may be authoritative.

**Never retry programming the same damaged record slot.** Mark any non-erased invalid slot as consumed and move forward.

---

## 9. Boot recovery scanner

At every boot before the runtime task starts:

1. Scan all 16 sector headers.
2. Classify each sector as:
   - `ERASED`
   - `VALID_READY`
   - `DIRTY_OR_TORN`
3. For each `VALID_READY` sector, scan all record slots.
4. Classify each slot:
   - all `0xFF` -> free
   - non-erased but commit invalid -> consumed/torn, ignore
   - commit structurally valid but GCM invalid -> corrupt, ignore and raise diagnostic counter
   - fully authenticated -> candidate
5. Select the authenticated record with the highest `record_seq`.
6. If no valid records exist:
   - if the entire 128 KiB partition is erased -> initialize INITIAL record at zero;
   - otherwise -> `RUNHOURS_JOURNAL_CORRUPT`, do not reset to zero.
7. Resume from the selected record's `runtime_quanta`.
8. Find the next safe write location.

Do not trust sector generation, record sequence, CRC or commit marker alone; the final record must pass AES-GCM authentication.

---

## 10. Power-fail-safe sector recycling

This is the critical answer to the requirement that an erase must never destroy the only valid running-hours value.

### 10.1 Invariant

> **Never erase the sector containing the globally latest authenticated record until a newer authenticated checkpoint exists in another sector.**

### 10.2 Sector transition procedure

When the active sector has no free record slots:

```text
1. Determine global latest authenticated record L.
2. Select the oldest reclaimable victim sector V.
   V MUST NOT contain L.
3. Erase only V (8 KiB).
4. Verify V is completely erased according to the flash-driver criterion.
5. Set `new_generation = max(valid sector generations) + 1`; generation wrap is a terminal fault.
6. Write V sector header excluding READY marker.
7. Read back/validate header.
8. Write READY marker last.
9. Read back/validate complete header.
10. Append a CHECKPOINT record into V:
       record_seq = L.record_seq + 1
       runtime_quanta = L.runtime_quanta
       record_type = CHECKPOINT
11. Read back and authenticate CHECKPOINT.
12. Only after step 11 succeeds does V become the current write sector.
13. The previous sector remains untouched until a later recycling cycle.
```

The checkpoint advances the **physical `record_seq`** but does not add running time.

This is why `record_seq` and `runtime_quanta` are separate fields.

### 10.3 Reset/power-cut outcomes during erase/recycle

**Cut during victim erase:** victim becomes dirty or erased; previous latest record remains in another sector. On reboot, re-scan, find previous latest, and erase/reprepare the victim again when safe.

**Cut after erase, before header READY:** victim is erased or has an invalid header; previous latest remains authoritative.

**Cut during header:** header lacks exact READY marker; ignore victim; previous latest remains authoritative.

**Cut after header READY, before checkpoint:** sector has valid header but no newer valid record; previous latest remains authoritative. The recovery code may re-erase/reprepare this sector or write a checkpoint after proving slots are virgin.

**Cut during checkpoint:** checkpoint lacks a valid commit/tag; previous latest remains authoritative.

**Cut after valid checkpoint:** new checkpoint has higher `record_seq`; it is authoritative even though runtime total is unchanged. Continue appending there.

At no point does recovery need to erase every journal sector or rewrite history from the beginning.

---

## 11. Bank-aware flash operation

The MCXN947 has dual-bank flash and Read-While-Write support. Because the running-hours partition is intentionally split 64 KiB + 64 KiB across the two physical banks, normal background logging should use the **non-executing physical bank** whenever the current SWAP state can be resolved reliably. This avoids avoidable execution stalls and reduces interaction with instruction fetch.

Implementation requirements:

1. Determine the current flash-SWAP/remap state using the same supported mechanisms as the existing MCUboot/OTA implementation.
2. Map every logical journal sector to its physical bank before choosing the next sector.
3. During ordinary operation, append/recycle in the **non-executing physical bank**. If an A/B swap changes which physical bank executes the app, create the next authenticated checkpoint in the newly non-executing journal pool before normal appends continue.
4. Do not perform routine same-physical-bank erase/program merely for convenience. Same-bank behavior may be enabled only after a separate hardware proof shows bounded execution impact and no reliability issue.
5. Serialize all program/erase operations through a single flash arbiter/mutex shared with the application-side OTA service.
6. OTA has priority over background running-hours maintenance.
7. Never erase/program a journal sector while an OTA operation is using the flash controller unless the NXP driver explicitly guarantees the combination and a hardware test proves it.
8. Keep the existing `mflash_drv` RAM-function placement and cache/barrier discipline intact unless NXP's driver documentation requires a reviewed change.
9. Measure worst-case task scheduling/network latency during a 16-byte program and during an 8 KiB erase/recycle event.

If a 10-minute boundary arrives while OTA holds the flash arbiter, defer the journal append until OTA releases it. The accumulated interval remains in RAM until the durable append completes.

---

## 12. Files/modules to add

The exact paths may be adjusted to match project conventions, but responsibilities should remain separated.

Suggested new files:

```text
firmware/app/inc/memory_layout.h
firmware/app/inc/runhours_format.h
firmware/app/inc/runhours_journal.h
firmware/app/inc/runhours_crypto.h
firmware/app/inc/runhours_task.h

firmware/app/runhours/runhours_format.c
firmware/app/runhours/runhours_journal.c
firmware/app/runhours/runhours_crypto.c
firmware/app/runhours/runhours_flash_mcxn.c
firmware/app/runhours/runhours_task.c

firmware/app/test/runhours/
    test_runhours_format.c
    test_runhours_scan.c
    test_runhours_powercut.c
    test_runhours_recycle.c
    test_runhours_crypto.c

scripts/check_memory_layout.py
scripts/check_signed_image_size.py
scripts/check_cmpa_delta.py
scripts/runhours_dump_raw.py        # raw/encrypted structural diagnostic only
scripts/runhours_fault_campaign.py

docs/adr/ADR_RUNHOURS_JOURNAL_AND_512K_LAYOUT.md
docs/evidence/RH_*.md
```

`runhours_dump_raw.py` must never contain or retrieve the device's plaintext journal key. If a decrypted maintenance view is required later, design a separately authorized device-side export or company-only diagnostic workflow.

---

## 13. Single source of truth for memory addresses

Create one authoritative layout header/configuration and derive or verify every other representation from it.

Example constants:

```c
#define APP_SLOT_SIZE             0x00080000UL
#define APP_PRIMARY_BASE          0x00000000UL
#define APP_SECONDARY_BASE        0x00100000UL

#define PLATFORM_A_BASE           0x00080000UL
#define PLATFORM_A_SIZE           0x00020000UL
#define RUNHOURS_A_BASE           0x000A0000UL
#define RUNHOURS_A_SIZE           0x00010000UL
#define EVENTLOG_A_BASE           0x000B0000UL
#define EVENTLOG_A_SIZE           0x00050000UL

#define PLATFORM_B_BASE           0x00180000UL
#define PLATFORM_B_SIZE           0x00020000UL
#define RUNHOURS_B_BASE           0x001A0000UL
#define RUNHOURS_B_SIZE           0x00010000UL
#define EVENTLOG_B_BASE           0x001B0000UL
#define EVENTLOG_B_SIZE           0x00050000UL

#define FLASH_ERASE_SECTOR_SIZE   0x00002000UL
#define FLASH_PROGRAM_UNIT        16UL
```

Compile-time/static checks and host checks must prove:

- all starts/sizes are erase-sector aligned where erase is possible;
- slots are exactly 512 KiB;
- no partition overlaps another;
- no partition exceeds `0x001FFFFF`;
- journal is exactly 128 KiB total;
- update range never enters `0x00080000..0x000FFFFF` or `0x00180000..0x001FFFFF`;
- event-log/reserve ranges are never linked into application images;
- image signer uses the same slot size as MCUboot.

---

# 14. Agent execution plan

## M0 — Freeze baseline and create branch

### Goal

Create a recoverable, evidence-backed starting point before touching flash geometry.

### Steps

1. Inspect current repository state:

```bash
git status --short
git branch --show-current
git log --oneline --decorate -20
```

2. Determine whether the local workstation contains newer mTLS reliability/soak work that has not been pushed to GitHub.
3. If there are uncommitted changes, do not discard them. Commit/tag them appropriately or create a safety branch first.
4. Run baseline host tests.
5. Build the exact currently deployable mTLS image and save:
   - `.elf`
   - `.map`
   - raw binary
   - signed/padded image
   - `arm-none-eabi-size` output
   - SHA-256 of each artifact
6. Run baseline on-board smoke:
   - boot banner
   - ping
   - mTLS Hello/STATUS
   - raw TCP rejected
   - no client cert rejected
   - wrong CA rejected
   - valid update-service connection
7. Capture current security state before any PFR work:
   - CMPA binary and parsed view
   - CFPA binary and parsed view
   - current boot/remap setting
   - RoTKH
   - secure boot config
   - `CUST_MK_SK` presence/hashable non-secret representation if existing tooling supports it
   - lifecycle/debug configuration
   - IFR MCUboot reference hash/size where readable or already established
8. Tag the clean baseline, for example:

```bash
git tag pre-512k-layout-runhours
```

9. Create the branch:

```bash
git switch -c feat/512k-ab-encrypted-runhours
```

### Exit gate

Baseline reproducible, board healthy, all current features pass, security backups exist, repository clean.

---

## M1 — Safely reduce firmware below the 512 KiB slot ceiling

### Goal

Reduce the complete current-feature image while preserving security, reliability, performance, IPv4 and IPv6. This is a **measured allow-list exercise**, not feature deletion by trial and error.

### M1.0 — Capture the real baseline first

Before optimization, capture the latest locally-qualified build and do not assume the remote branch is current.

Record:

```text
Git commit / dirty-state
compiler + linker versions
SDK 26.06.00 LTS revision
ELF / MAP / BIN / signed image SHA-256
arm-none-eabi-size output
section sizes
largest 100 symbols
largest object files/libraries
configured Mbed TLS macros
configured PSA_WANT macros
configured MBEDTLS_PSA_ACCEL macros
negotiated TLS version + cipher on :5000 and :5555
IPv4 + IPv6 compile flags
RAM/heap/task-stack values
qualified stream throughput
reconnect/negative-cert results
```

The currently recorded GitHub evidence is approximately `m_text ~784 KiB / 798 KiB`; use the newly captured local value as authority.

### M1.1 — Create two build profiles

Keep a reproducible **BASELINE** profile and create a **LEAN_PROD_TEST** profile. Never overwrite the baseline configuration.

`BASELINE` must reproduce the qualified behavior.

`LEAN_PROD_TEST` may change only footprint-related build/configuration choices approved below.

Both profiles must use the same:

- application source/protocol behavior;
- certificates and key identities;
- secure boot signer;
- SB3 update authority;
- ports and timeout policies;
- lwIP dual-stack policy;
- FreeRTOS task model.

### M1.2 — Build/link optimization before deleting library features

Apply low-risk compiler/linker optimization first:

```text
-Os
-ffunction-sections
-fdata-sections
-Wl,--gc-sections
```

Keep warnings/errors and stack-usage checks.

Evaluate LTO only as a second step:

```text
-flto
```

LTO is accepted only if all runtime tests pass and no toolchain/ROM-API/section-placement assumption breaks. In particular, confirm the `mflash_drv` RAM placement remains correct.

Do **not** use unsafe speed/semantic flags such as `-ffast-math` as a size optimization.

After each step, record exact flash delta and performance delta.

### M1.3 — Remove non-product debug weight without losing diagnostics

Current code enables full debug console and `DPRINTF_ADVANCED_ENABLE=1`. The product messages currently require strings/integers/hex, not floating-point formatting.

Measure these individually:

1. Disable advanced printf formatting if no required code path uses it.
2. Prefer NXP lite/compact debug console only if UART behavior used by service/QA remains sufficient.
3. Keep machine-readable diagnostic counters/status fields even if verbose text strings are removed from the shipping profile.
4. Keep a separate DIAGNOSTIC build profile with verbose strings if useful; do not make verbose console code a requirement of the field image unless operationally needed.
5. Never remove fault/error counters merely to reduce flash.

Regression: boot banner, STATUS, fault counters, update diagnostics and QA tooling must continue to work.

### M1.4 — Freeze the required TLS profile before creating a custom config

The MCU is a TLS **server only** today. The host PC is the TLS client. The current product profile is:

```text
Role on MCU:               TLS server only
Peer auth:                 mutual X.509, client cert REQUIRED
MCU certificate:           ECDSA P-256 / SHA-256
Client certificate:        ECDSA P-256 / SHA-256
Trust model:               one private root CA, no intermediates required today
Key exchange:              ECDHE / P-256
Record protection:         AES-GCM
Protocol:                  TLS 1.2 + TLS 1.3 initially
Transport:                 TCP via custom lwIP BIO
Sessions:                  no tickets/resumption/0-RTT
Application extensions:    no ALPN, no SNI
DTLS:                      not used
PSK:                       not used
RSA certificates/keys:     not used
```

Do not prune anything until a test proves it is outside this allow-list.

### M1.5 — Introduce project-owned Mbed TLS and PSA configuration files

Do not patch SDK sources.

Add, for example:

```text
firmware/app/security/mbedtls_product_config.h
firmware/app/security/psa_crypto_product_config.h
```

Wire them using supported build definitions such as:

```text
MBEDTLS_CONFIG_FILE
MBEDTLS_PSA_CRYPTO_CONFIG_FILE
```

Enable the supported Mbed TLS PSA configuration path:

```text
MBEDTLS_PSA_CRYPTO_CONFIG
MBEDTLS_USE_PSA_CRYPTO
```

Use the pinned NXP ELS/PKC PSA driver. For each required primitive:

1. declare the corresponding `PSA_WANT_*` requirement;
2. determine whether the pinned MCXN947 driver advertises a complete `MBEDTLS_PSA_ACCEL_*` implementation;
3. remove the Mbed TLS software implementation **only when NXP's driver-only rules permit it**;
4. keep software fallback when acceleration is incomplete or required by X.509/TLS integration.

Generate an evidence table:

| Primitive | Required by | PSA_WANT | HW accelerated? | Software fallback retained? | Reason |
|---|---|---|---|---|---|
| P-256 ECDH | ECDHE | yes | measured | yes/no | ... |
| P-256 ECDSA verify/sign | mTLS | yes | measured | yes/no | ... |
| SHA-256 | TLS/X.509 | yes | measured | yes/no | ... |
| AES-GCM-128 | TLS | yes | measured | yes/no | ... |
| AES-GCM-256 | TLS/journal | yes | measured | yes/no | ... |
| HKDF/HMAC | TLS 1.3 | yes if TLS1.3 | measured | yes/no | ... |

The running-hours journal later requires AES-256-GCM even if TLS negotiates AES-128-GCM, so do not accidentally prune AES-256-GCM from the PSA application profile.

### M1.6 — Explicit crypto/protocol allow-list and safe-removal candidates

The following are **expected removable candidates**, subject to `check_config`/build and regression proof:

```text
REMOVE IF UNUSED:
- RSA key exchange, RSA certificates, RSA signatures
- finite-field DH / DHE / FFDHE
- PSK and PSK+ECDHE modes
- EC J-PAKE / SRP if present
- DTLS and DTLS-only cookie/replay/CID code
- TLS session cache
- TLS session tickets / resumption
- TLS 1.3 PSK resumption modes
- TLS 1.3 0-RTT / early data
- ALPN
- SNI
- TLS key exporter if unused
- renegotiation if unused
- CBC cipher suites
- CCM suites if unused
- ChaCha20-Poly1305 if unused
- DES/3DES/Camellia/ARIA/Blowfish and other non-profile ciphers
- elliptic curves other than secp256r1
- SHA-1/MD5 acceptance if certificates/profile do not require them
- SHA-384/SHA-512 only if no retained approved suite requires them
- certificate/CSR writing/generation code
- PKCS#12 / encrypted-key parsing if not used
- filesystem I/O support
- Mbed TLS `net_sockets` layer because product uses lwIP BIO callbacks
- Mbed TLS debug/self-test/error-string modules when production code does not call them
- TLS client code on the MCU
```

The following are **not removable** in the initial equivalent profile:

```text
KEEP:
- TLS server core
- TLS 1.2
- TLS 1.3
- X.509 certificate parsing and verification
- ASN.1/OID pieces required by the actual ECDSA certificates
- ECDSA P-256
- ECDH P-256
- SHA-256
- AES-GCM
- HKDF/HMAC primitives required by retained TLS versions
- PSA RNG / hardware-backed random generation
- peer-certificate verification
- MBEDTLS_SSL_KEEP_PEER_CERTIFICATE when required by TLS 1.3
- threading hooks required by FreeRTOS/concurrent services
```

Run Mbed TLS configuration validation after every profile change. Never bypass dependency checks.

### M1.7 — Restrict cipher suites without lowering system security

Initial approved set should be the smallest set that maintains today's ECDSA/P-256/AES-GCM profile and interoperability with the authorized PC.

Preferred initial compatibility profile:

```text
TLS 1.2:
  ECDHE-ECDSA-AES128-GCM-SHA256
  ECDHE-ECDSA-AES256-GCM-SHA384   [retain initially if currently negotiated/supported]

TLS 1.3:
  TLS_AES_128_GCM_SHA256
  TLS_AES_256_GCM_SHA384          [retain initially if currently negotiated/supported]

Key exchange group:
  secp256r1 only

Certificate signature:
  ECDSA secp256r1 SHA-256
```

Because P-256 itself provides approximately a 128-bit security level, AES-128-GCM is not the weak link in this chain. Nevertheless, **do not remove AES-256/SHA-384 automatically**. First measure its code-size cost and current negotiated behavior. If removing it becomes necessary, produce a specific owner-review item rather than silently changing the profile.

Explicitly reject legacy TLS <=1.1 and non-profile cipher suites.

### M1.8 — Convert embedded credentials from PEM to DER

The current implementation embeds PEM CA/server certificate/private key and parses them at boot.

Create DER artifacts from the **same existing credentials** and prove:

```text
CA public-key fingerprint unchanged
server certificate SHA-256 fingerprint unchanged
server public key unchanged
server private/public key pair matches
client trust behavior unchanged
```

Then switch the MCU build to DER inputs. If this lets the build remove PEM/Base64 parsing and encrypted-key parsing code, record the size reduction.

Do not rotate certificates/keys as part of this optimization.

If direct PSA import/opaque-key handling would save more code, treat that as a later optional subphase because it changes key handling and requires a separate reliability/security regression. DER conversion is the preferred low-risk step first.

### M1.9 — Preserve lwIP dual stack and network performance

Hard requirements:

```text
LWIP_IPV4 = 1
LWIP_IPV6 = 1
LWIP_TCP  = 1
LWIP_SOCKET = 1
```

Do not disable IPv6, TCP sockets, or the netconn pieces required by the socket API for footprint.

Do not reduce the following merely to save flash:

- `TCP_SND_BUF`;
- `TCP_WND`;
- pbuf pool sizing;
- TLS input/output record lengths;
- hello/update task stacks;
- lwIP heap;
- application heap.

Those are RAM/performance controls, not primary flash-size controls.

It is acceptable to compile out lwIP **debug-printing** paths in the lean production profile while keeping operational counters and fault reporting.

Dual-stack proof must include:

1. IPv4 interface/address comes up and current static IPv4 operation remains valid.
2. IPv6 is compiled/enabled and a link-local IPv6 address is formed.
3. ICMPv6 neighbor discovery/ping6 succeeds on the test network.
4. Existing mTLS services over IPv4 continue to work.
5. If the product currently exposes mTLS over IPv6, it must continue to work; if it is currently IPv4-socket-only, do not silently claim IPv6 service support merely because the stack is enabled.

### M1.10 — Optional LTO and library cleanup

Only after the crypto allow-list is stable:

- enable LTO and rerun all tests;
- remove NXP example/demo objects not actually referenced;
- confirm HTTP/HTTPS application code is absent;
- confirm test certificates/example crypto assets are absent;
- inspect duplicate libc/printf formatter code;
- use smaller formatter paths only if STATUS/UART behavior is preserved.

Do not rewrite working TLS or X.509 logic to save a few kilobytes.

### M1.11 — Size gates

Measure both **loadable flash content** and the final **signed/padded MCUboot image**.

Targets:

```text
Preferred loadable application <= 400 KiB
Preferred signed image         <= 448 KiB
Absolute signed-slot bound     < 512 KiB including required header/trailer
```

Decision:

```text
<=448 KiB signed: PASS size margin gate
449..511 KiB:     technically fits, but STOP for owner margin decision
>=512 KiB:        FAIL; no CMPA/layout change
```

### M1.12 — Security equivalence tests after every final config change

Mandatory on real hardware:

1. valid client certificate -> handshake PASS;
2. no client certificate -> reject;
3. wrong CA -> reject;
4. client cert signed by unauthorized CA -> reject;
5. raw plaintext TCP -> reject;
6. TLS 1.0/1.1 -> reject;
7. valid TLS 1.2 -> PASS while TLS1.2 retained;
8. valid TLS 1.3 -> PASS while TLS1.3 retained;
9. unauthorized cipher suite -> reject/no common cipher;
10. server certificate fingerprint on host -> exact expected value;
11. corrupt/invalid SB3 remains rejected independently of TLS;
12. wrong firmware signer remains rejected by MCUboot;
13. no change to RoTKH / `CUST_MK_SK` / CMPA / CFPA / IFR;
14. certificate time handling remains exactly as current design: only absent-trusted-clock time flags are narrowly ignored; signature/CA/key-usage/identity failures remain fatal.

### M1.13 — Reliability and performance equivalence tests

The lean image must pass at least:

```text
1000 valid mTLS reconnects
100 invalid/no/wrong certificate attempts
50 mid-session TCP/TLS aborts
20 Ethernet link cycles (manual/fixture as available)
Hello/STATUS/ECHO regression
mTLS SB3 update N -> N+1
corrupt SB3 rejection
streaming soak using the existing QA stream path
```

Performance acceptance:

```text
sustained stream throughput >= 95% of the qualified baseline
no persistent increase in verify_fail / exchange errors
no heap-growth trend
no task-stack regression below approved margin
handshake/reconnect behavior remains bounded
```

Do not trade throughput for flash size by reducing buffers unless separately approved after measurement.

### M1.14 — TLS 1.3-only fallback is not automatic

If the complete safe-pruned TLS1.2+TLS1.3 image still cannot reach the size gate, stop and produce a report with:

```text
size with TLS1.2+1.3
incremental size attributable to TLS1.2
incremental size attributable to TLS1.3
interoperability impact
security impact
host Python/OpenSSL compatibility result
```

TLS 1.3-only may then be proposed because it is not a cryptographic downgrade, but it **does remove protocol-version compatibility**. It requires explicit owner approval and a fresh reconnect/update/soak matrix.

### M1 exit gate

Proceed to M2 only when:

- all current product/security semantics are preserved;
- IPv4 and IPv6 remain enabled;
- the final signed image meets the approved size margin;
- current stream throughput is within 5% of baseline;
- mTLS negative tests, reconnect tests and secure update pass;
- no security/PFR state was modified during slimming.

### STOP

If the 512 KiB target requires removing a required security control, disabling IPv6, reducing required throughput/reliability, or making an undocumented crypto fallback assumption, stop and propose a larger A/B slot instead.

---

## M2 — Implement 512 KiB layout in code, build-only first

### Goal

Change software geometry without yet changing live CMPA.

### Actions

1. Add `memory_layout.h` and host layout checker.
2. Update application linker geometry to 512 KiB.
3. Remove stale 1 MiB assumptions.
4. In `firmware/app/flash_partitioning/flash_partitioning.c`, do **not** calculate slot size as:

```c
BOOT_FLASH_CAND_APP - BOOT_FLASH_ACT_APP
```

because bases remain `0x00000000` and `0x00100000`, whose difference is 1 MiB.

Instead introduce an explicit slot-size constant/config:

```c
.fa_size = APP_SLOT_SIZE;   /* 0x80000 */
```

for both primary and secondary areas.

5. Keep secondary slot base at `0x00100000`.
6. Update every `imgtool`/MCUboot slot-size input to 512 KiB.
7. Update SB3 generation so erase/load ranges cover only the secondary 512 KiB firmware slot.
8. Add hard update-range guards that reject any attempt to erase/program outside the candidate firmware range.
9. Add a CI/build gate that parses SB3 commands and fails if an erase/load overlaps shared storage.
10. Build both firmware variants and inspect map/binary/signing output.

### Exit gate

No live writes. Every host/build artifact agrees on 512 KiB slots; update package cannot touch shared storage.

---

## M3 — Implement journal core with host fault injection

### Goal

Prove power-fail correctness before touching real flash.

### Architecture

Make journal logic platform-independent behind narrow operations:

```c
struct runhours_ops {
    read(...);
    program_16(...);
    erase_8k(...);
    random(...);
    aead_encrypt(...);
    aead_decrypt(...);
};
```

### Host model

Create a fake flash model enforcing:

- erase changes a complete 8 KiB sector to `0xFF`;
- programming may only change 1 bits to 0 bits;
- program granularity is 16 bytes;
- injected cut can occur before/after or partway through every program/erase operation;
- torn erase may result in arbitrary partially erased bytes;
- torn program may result in arbitrary subset of intended 1->0 transitions.

### Mandatory tests

Test at least:

1. Virgin initialization -> authenticated 0-hour record.
2. Reboot after initial record.
3. Normal append at 10 min.
4. Hundreds of appends.
5. Record-sequence wrap logic analysis (64-bit practical non-issue, still test comparisons).
6. Cut during phrase 0/1/2/3.
7. Bit corruption in metadata.
8. Bit corruption in ciphertext.
9. Bit corruption in GCM tag.
10. Bit corruption in commit phrase.
11. Non-erased torn slot followed by later valid slot.
12. Sector full -> transition.
13. Cut during victim erase.
14. Cut after erase before header.
15. Cut during header.
16. Cut during READY marker.
17. Cut before/during/after checkpoint.
18. Dirty sector from prior boot.
19. Multiple dirty sectors with at least one valid latest record.
20. Full ring wrap.
21. Multiple ring wraps.
22. Copy a valid record to a different sector/slot -> GCM must reject due to AAD/nonce context.
23. Copy encrypted journal from unit A to simulated unit B with a different key -> reject.
24. No valid records + non-virgin bytes -> CORRUPT, never initialize zero.
25. Across power cuts and multiple ring wraps, `(sector_generation, slot_index)` is never reused under the same `K_RH`.

### Exhaustive cut-point property

For every persistent transition, automatically inject a reset/cut at every primitive operation boundary and assert:

```text
recovered runtime == previous committed runtime
OR
recovered runtime == newly fully committed runtime
```

Never:

```text
recovered runtime < previous committed runtime
recovered runtime == 0 because of corruption
ambiguous two different latest values
```

### Exit gate

All host fault-injection tests pass deterministically and under randomized seeded campaigns.

---

## M4 — Integrate PUF/EdgeLock key and AES-GCM

### Goal

Encrypt/authenticate the runtime value with a device-specific key without modifying existing secure-boot/update secrets.

### Actions

1. Study the exact MCUXpresso 26.06 PUF/ELS examples available in the pinned workspace.
2. Implement a minimal dedicated journal-key lifecycle using NXP-supported APIs.
3. Keep journal key purpose separate from mTLS and SB3.
4. Store only a device-bound PUF key-code/wrapped representation in the platform-reserved area if persistent key material is required.
5. Add redundant/authenticated metadata for the wrapped key so a torn first provisioning does not brick the journal.
6. Use ELS-supported AES-256-GCM.
7. Use deterministic `sector_generation || slot_index` 96-bit GCM nonces; do not depend on random nonce generation for routine journal writes.
8. Zeroize transient secret buffers.
9. Add tests proving copied wrapped key/journal cannot be used on another device if a second board is available; otherwise host-model this and record the hardware limitation.

### STOP

Do not write a new PFR/CMPA secret and do not reuse `CUST_MK_SK` directly merely for convenience. If a new one-time security provisioning step is required, document it and obtain owner approval before executing it.

### Exit gate

On-target encrypt/decrypt/tag verification works and existing mTLS/SB3 functionality is unchanged.

---

## M5 — Controlled CMPA migration to 512 KiB remap

### Goal

Change only the flash remap size while preserving every existing security property.

### Critical value

For 512 KiB:

```text
FLASH_REMAP_SIZE = 15
(15 + 1) × 32 KiB = 512 KiB
```

### Rules

1. **Never reuse the old stock `cmpa.bin`.** The live CMPA now contains secure-boot/root-key/security state established after initial provisioning.
2. Read the live CMPA through the supported ISP/SPSDK flow.
3. Parse to a human-readable form.
4. Generate candidate CMPA from the **live/current** settings, changing only the intended remap field.
5. Use `scripts/check_cmpa_delta.py` to fail if any other semantic field changes.
6. Specifically prove unchanged:
   - boot source;
   - secure-boot enable/mode;
   - RoTKH;
   - `CUST_MK_SK` blob/data;
   - IFR protection;
   - lifecycle;
   - debug configuration;
   - all unrelated CMPA security fields.
7. Back up CMPA/CFPA again immediately before the write.
8. Prepare and verify the existing USB ISP recovery procedure before changing the field.
9. Require an explicit owner-controlled write gate before the actual CMPA programming command.
10. Program only the reviewed CMPA change.
11. Reset and read back CMPA.
12. Re-parse and re-run exact semantic-delta check.

### Exit gate

Only the remap size changed; secure boot chain remains valid; board is recoverable.

---

## M6 — Hardware proof of 512 KiB A/B remap and fixed shared regions

### Goal

Prove the hardware mapping before trusting persistent logs.

### Actions

1. Install a signed 512 KiB-layout firmware image in both A and B as required by the DIRECT_XIP/SWAP migration procedure.
2. Place known test patterns in several addresses outside the remap window, including running-hours and future event-log areas.
3. Boot A; read/hash those patterns.
4. Perform a secure mTLS/SB3 update to B using the new geometry.
5. Boot/swap to B; read/hash the same shared addresses.
6. Perform another B->A update/swap.
7. Prove shared addresses retain identical content through both swap directions.
8. Prove SB3 erase/load never touches upper-half regions.
9. Deliberately create a test package with an out-of-range erase and prove host build/gate rejects it before issuance.

### Important migration note

Do not claim that an old 1 MiB-layout field firmware can be seamlessly OTA-migrated to the new 512 KiB remap geometry until a separate migration path has been designed and proven. For this board-level experiment, an ISP/service migration is acceptable. After migration, qualify OTA only between new-layout images.

### Exit gate

512 KiB A/B swap proven; upper-half shared storage proven stable; existing secure update works.

---

## M7 — Provision initial 0-hour journal

### Goal

Create the first durable running-hours state exactly once.

### Steps

1. Verify the full 128 KiB running-hours partition is erased.
2. If not erased and this is a first-time controlled test board, archive its contents and require explicit provisioning action; never silently erase unknown field data.
3. Erase/verify the first selected sector.
4. Create valid sector header with fresh nonce base.
5. Write INITIAL authenticated/encrypted record with:

```text
record_seq = 0
runtime_quanta = 0
record_type = INITIAL
```

6. Read back and authenticate.
7. Reset board.
8. Boot scanner must report exactly zero and next free slot.
9. Remove VBAT if desired, power-cycle completely, and verify zero record remains because authority is main flash, not backup RAM.

### Exit gate

Initial zero survives full power removal and normal reboot.

---

## M8 — FreeRTOS 10-minute runtime task

### Goal

Append running-hours records during normal operation without disturbing network/update workloads.

### Task behavior

1. Low-priority task starts only after application initialization.
2. Read recovered `runtime_quanta` from journal.
3. Accumulate monotonic runtime using FreeRTOS ticks in a wrap-safe manner.
4. Every 600 seconds of operating time:
   - acquire flash arbiter;
   - if OTA is active, defer;
   - append next runtime record;
   - release flash arbiter;
   - update diagnostics.
5. Never block mTLS networking for unbounded periods.
6. Expose read-only runtime diagnostics through existing STATUS or a narrowly defined new mTLS diagnostic command.

Suggested STATUS additions:

```text
runhours_quanta
runhours_seconds
runhours_record_seq
runhours_sector
runhours_slot
runhours_recovery_status
runhours_auth_fail_count
runhours_torn_slot_count
runhours_sector_erase_count_min/max
```

Do not expose encryption keys, PUF key codes beyond what is necessary, or plaintext sensitive internals unrelated to running-hours status.

### Exit gate

At least three real 10-minute transitions observed; mTLS Hello/STATUS and network remain healthy.

---

## M9 — Real hardware reset/power-cut campaign

### Goal

Confirm host-model guarantees on real flash.

### Record-write cases

Inject NRST and, where practical, true power removal around:

- before phrase 0;
- during/after phrase 0;
- during/after phrase 1;
- during/after phrase 2;
- immediately before commit;
- during commit phrase;
- immediately after commit;
- during final readback/authentication.

Expected result after every reboot:

```text
last valid record = old record OR fully committed new record
```

Never a lower historical value and never a reset to zero.

### Sector-recycle cases

Force a sector transition using a test-only accelerated build or pre-filled journal image, then cut/reset:

- during victim erase;
- immediately after erase;
- during sector header;
- during READY phrase;
- before checkpoint;
- during checkpoint phrases;
- during checkpoint commit;
- after checkpoint before next normal record.

After every case:

- scanner finds previous or new checkpoint;
- dirty victim is recognized;
- erase may be safely retried;
- latest authenticated runtime is preserved.

### Production-code hygiene

Any accelerated interval or deterministic fault hook must be compile-time test-only and MUST be absent from the production 600-second build. Add a release gate proving it is absent.

### Exit gate

All defined reset and true-power-cut cases pass.

---

## M10 — Full regression of existing functionality

After journal and new geometry are active, rerun at least:

1. Secure ROM -> IFR MCUboot -> application boot.
2. IPv4 ping/static-IP operation.
3. IPv6 link-local address + ping6/neighbor-discovery proof.
4. Confirm build has `LWIP_IPV4=1` and `LWIP_IPV6=1`.
5. mTLS Hello/STATUS.
6. Raw TCP rejection.
5. Missing client certificate rejection.
6. Wrong CA rejection.
7. Wrong server fingerprint rejection on host.
8. At least 100 valid mTLS reconnects; use the existing larger reliability matrix if available.
9. mTLS SB3 update from new-layout version N to N+1.
10. Corrupt SB3 rejection.
11. Wrong-key/signature rejection.
12. Update-window behavior.
13. Verify running-hours value survives OTA.
14. Verify existing encrypted running-hours records remain decryptable after A/B swap.
15. Verify OTA changes no shared-sector bytes except legitimate running-hours appends occurring during the test.
16. Verify future event-log and platform-reserve regions remain untouched.
17. Verify no security state (RoTKH, secure boot, `CUST_MK_SK`, lifecycle/debug) changed unexpectedly.
18. Re-run the qualified streaming workload and prove throughput is >=95% of the baseline.
19. Confirm both IPv4 and IPv6 remain enabled after the final lean configuration.

### Exit gate

All baseline behavior remains equivalent and shared storage survives multiple secure updates.

---

## M11 — Accelerated ring/endurance functional test

This is not an endurance-to-failure test; it validates ring logic.

1. Build a test-only image with a short commit interval, e.g. 1 second.
2. Fill and recycle the complete 16-sector ring multiple times.
3. Confirm:
   - no sequence regression;
   - no GCM nonce reuse;
   - erase distribution is balanced;
   - sector generation increases as designed;
   - checkpoint transitions preserve runtime;
   - mTLS remains usable during background record programming;
   - no OTA/shared-flash collision.
4. Restore production 600-second interval and prove test build flag is absent.

### Exit gate

At least several complete ring wraps pass with zero authentication/recovery errors.

---

## M12 — Evidence and branch freeze

Create a qualification package including:

```text
docs/evidence/RH_BASELINE.md
docs/evidence/RH_SIZE_REDUCTION.md
docs/evidence/RH_MEMORY_LAYOUT.md
docs/evidence/RH_CMPA_REMAP_DELTA.md
docs/evidence/RH_CRYPTO_KEY_LIFECYCLE.md
docs/evidence/RH_HOST_FAULT_MATRIX.md
docs/evidence/RH_HARDWARE_POWERCUT.md
docs/evidence/RH_MTLS_OTA_REGRESSION.md
docs/evidence/RH_RING_WRAP.md
```

Record:

- Git commit/tag;
- toolchain/SDK/SPSDK versions;
- exact flash map;
- actual final firmware size;
- signed-image size;
- CMPA before/after semantic diff;
- RoTKH and secure-boot proof;
- journal key mechanism;
- record-format version;
- power-cut outcomes;
- sector erase count calculations;
- OTA regression results;
- all deviations/open risks.

If all gates pass, tag the test branch, for example:

```text
layout512-runhours-qualified-test-v1
```

Do not merge to `main` automatically. Owner reviews the evidence and separately approves production migration.

---

# 15. Explicit safety / STOP conditions for the AI agent

The agent MUST stop and report rather than improvise if any of these occur:

1. Current complete firmware cannot fit safely in 512 KiB without feature/security removal.
2. Live CMPA differs from expected inventory before migration.
3. Candidate CMPA changes anything other than the approved remap field.
4. RoTKH or secure-boot configuration would change unexpectedly.
5. `CUST_MK_SK` would be regenerated, cleared, altered or exposed.
6. IFR MCUboot would be erased/reprogrammed without a specific reviewed need and recovery plan.
7. PUF/ELS journal-key implementation requires undocumented behavior or reuse of updater secrets.
8. A journal write/erase range overlaps either firmware slot, platform reserve outside its ownership, or future event log.
9. SB3 package would erase more than the 512 KiB candidate slot.
10. Boot recovery finds non-virgin journal contents but no valid authenticated record.
11. GCM nonce uniqueness cannot be proved.
12. Any fault-injection case recovers a lower runtime than the last committed value.
13. Any A/B update changes shared journal/log regions unexpectedly.
14. mTLS or secure-update negative tests regress.
15. A real board behaves differently from the documented flash/remap model.
16. IPv4 or IPv6 would need to be disabled to meet the image-size target.
17. TLS/mTLS security profile would need to be weakened without explicit owner approval.
18. Streaming throughput falls more than 5% from the qualified baseline and cannot be recovered without undoing the footprint change.

---

# 16. Acceptance criteria

This experiment is successful only when all of the following are true:

- Complete secure mTLS firmware fits the 512 KiB slot with approved margin.
- MCUboot stays valid in IFR.
- Remap size is 512 KiB and only the two firmware regions swap.
- 128 KiB running-hours partition is shared and stable across A/B updates.
- Initial 0-hour record is durable and authenticated.
- Runtime total is encrypted at rest.
- Records are authenticated with AES-256-GCM using a dedicated device-specific key.
- Record writes are power-fail safe.
- Sector erase/recycling is power-fail safe.
- Journal never needs whole-region erase/rewrite.
- Recovery always chooses the highest fully authenticated committed record.
- Invalid/torn slots are skipped, never rewritten in place.
- A dirty/torn erased sector can be safely reclaimed later.
- Complete battery removal does not reset running hours.
- Secure boot, mTLS Hello/STATUS, FreeRTOS/lwIP and mTLS SB3 OTA all continue to pass.
- Both IPv4 and IPv6 remain enabled and verified.
- Mutual certificate authentication, ECDHE/ECDSA/AES-GCM profile, host fingerprint validation and no-plaintext-fallback behavior remain intact.
- Final sustained stream throughput is at least 95% of the qualified baseline.
- Secure OTA never erases or overwrites shared storage.
- Existing security keys/configuration remain unchanged except the explicitly approved remap-size field.
- Hardware reset/power-cut matrix passes.
- Multiple full journal ring wraps pass.

---

# 17. Recommended later work, not part of this test

The 640 KiB event/maintenance-log region should be reserved now and left erased/unowned by normal firmware except for explicit range protection. A later project can reuse the same principles for event logs:

- compact binary records rather than text;
- aggregation counters for repeated events;
- authenticated/encrypted records;
- separate journal/key domain from running hours;
- crash snapshots;
- encrypted export package for third-party maintenance where the technician acts only as a courier.

Do not combine event logging with this first flash-layout migration. Prove one persistent journal and the A/B geometry first.

---

# 18. Primary technical references

Use the exact revisions installed/pinned in the project and archive them in the evidence package.

1. NXP MCXN947/946/547/... Datasheet, current project-approved revision.
2. NXP MCX N Reference Manual and MCX N Security Reference Manual.
3. NXP MCUXpresso SDK `eeprom_emulation` example — reports 8192-byte flash sectors and 16-byte change-block size.
   - https://mcuxpresso.nxp.com/mcuxsdk/latest/html/examples/driver_examples/eeprom_emulation/readme.html
4. NXP MCUXpresso SDK `MCUboot and flash remapping feature` documentation — FRDM-MCXN947 uses SWAP remap.
   - https://mcuxpresso.nxp.com/mcuxsdk/latest/html/examples/ota_examples/_doc/flash_remap_readme.html
5. NXP SPSDK MCXN9xx CMPA description — `FLASH_REMAP_SIZE` end address = `(value + 1) × 32 KiB`.
   - https://spsdk.readthedocs.io/en/v2.6.1/examples/dat/mcxn9xx/mcxn9xx_debug_auth.html
6. NXP MCUXpresso PUF v3 example — FRDM-MCXN947 supported; PUF key-code lifecycle.
   - https://mcuxpresso.nxp.com/mcuxsdk/26.06.00/html/examples/driver_examples/puf_v3/readme.html
7. NXP AN14687, *Ease CRA Compliance with MCX N* — EdgeLock secure storage and AES-GCM/ECC crypto capabilities.
   - https://www.nxp.com/docs/en/application-note/AN14687.pdf
8. NXP Mbed TLS 3.x Brief Driver-Only Configuration Guide — custom `MBEDTLS_CONFIG_FILE`, `MBEDTLS_PSA_CRYPTO_CONFIG_FILE`, `PSA_WANT_*`, and `MBEDTLS_PSA_ACCEL_*` guidance.
   - https://mcuxpresso.nxp.com/mcuxsdk/26.03.00/html/middleware/mbedtls3x/mcux_sdk/brief_config_guide.html
9. NXP/Mbed TLS driver-only build guidance — `MBEDTLS_USE_PSA_CRYPTO` and removing software crypto only when PSA acceleration is complete.
   - https://mcuxpresso.nxp.com/mcuxsdk/latest/html/middleware/mbedtls3x/docs/driver-only-builds.html
10. Mbed TLS footprint reduction guidance.
   - https://mbed-tls.readthedocs.io/en/latest/kb/how-to/reduce-polarssl-memory-and-storage-footprint/
11. NXP lwIP HTTPS/mBedTLS example documentation — confirms dual IPv4/IPv6 builds are supported when enabled.
   - https://docs.mcuxpresso.nxp.com/mcuxsdk/latest/html/examples/lwip_examples/lwip_httpssrv_mbedTLS/freertos/readme.html
12. Current repository evidence:
   - `docs/evidence/M2_M3_MTLS_PROOF.md`
   - `docs/dev-log.md`
   - `firmware/app/flash_partitioning/flash_partitioning.h`
   - `firmware/app/flash_partitioning/flash_partitioning.c`
   - active linker/map/build configuration as proven in M0.

---

## Final architecture judgment

**GO for an experimental branch, conditional on M1 size closure.**

The MCXN947 flash geometry supports the proposed 512 KiB remapped A/B regions and fixed upper-half shared storage. The 8 KiB erase sector and 16-byte programming granularity are well suited to a 128 KiB append-only encrypted journal. The proposed commit-last record format and checkpoint-before-reclaim ring ensure that a power failure during either record programming or sector erase cannot destroy the last committed running-hours value.

The only major current mismatch is firmware footprint: the last proven mTLS build is approximately 784 KiB of `m_text`, so 512 KiB slots are not yet viable. The agent must solve and prove this first, or stop and propose a larger remap size.
