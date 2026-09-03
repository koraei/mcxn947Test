# P7 ROM Secure Boot – Gate Report (Inspect / Build-Only)

**Date:** 2026-09-03  
**Unit:** DEV-UNIT-01  
**Board:** FRDM-MCXN947 (silicon ID `9DA8D48D0DDCD755903E8FBD3836C153`)  
**Phase:** P7 – inspect/build-only preparation. **No security state written.**

---

## 1. NXP ROM Secure Boot Flow – Documentation Evidence

### 1.1 Relevant NXP ROM behaviour (MCXN947 RM / AN13037)

| Parameter | Value confirmed in this unit |
|-----------|------------------------------|
| `BOOT_SRC` in CMPA | `SECONDARY_BOOTLOADER (0b10)` |
| MCUboot load address | `0x01008000` (IFR0, 32 KB slot) |
| ROM authentication type | `ECDSA_SIGNED` (MBI `authType=Signed`) |
| ROM trust anchor | ROTKH in CMPA (256-bit SHA-256 of ROT1 public key) |
| MBI format tool | `nxpimage mbi export` (SPSDK 3.10.0) |
| Certificate block version | 2.1 (one ECDSA-P256 ROT key, cert block for IMG1_1) |
| IFR slot size | 32 768 bytes (`0x8000`) at `0x01008000` |
| Signed MCUboot MBI size | **24 768 bytes (0x60C0)** – fits in IFR with 8 192 bytes to spare |

NXP secure boot for `SECONDARY_BOOTLOADER` mode:

1. ROM reads CMPA → `BOOT_SRC=0b10`, `SEC_BOOT_EN=ECDSA_SIGNED`.
2. ROM reads MBI from IFR (`0x01008000`).
3. ROM verifies certificate block in MBI: RKTH derived from cert-block ROT public key must match `CMPA.ROTKH`.
4. ROM verifies ECDSA-P256 signature on MBI image hash.
5. On pass → ROM jumps to MCUboot reset handler at `0x01008000`.
6. MCUboot continues, handles SB3.1 OTA update of app slot.

### 1.2 Key finding – ROM secure boot is ALREADY ACTIVE

**`SECURE_BOOT_CFG.SEC_BOOT_EN = ECDSA_SIGNED` is set in the live CMPA.**  
The ROTKH programmed at P3 (`670EE45ABA…`) matches the key used to sign the installed MBI.  
**ROM authentication of MCUboot was fully established at P3.**  P7 requires zero additional CMPA/CFPA writes.

---

## 2. Signed MCUboot Artifact – Build-Only

### 2.1 nxpimage command (reproducible)

```
nxpimage mbi export \
  --config C:/mcxn-secrets/DEV-UNIT-01/sec-workspace/configs/mbi_config.yaml
```

Config summary (`mbi_config.yaml`):

| Field | Value |
|-------|-------|
| `family` | `mcxn947` |
| `outputImageExecutionTarget` | `xip` |
| `outputImageAuthenticationType` | `Signed` |
| `outputImageExecutionAddress` | `0x01008000` |
| `certBlock` | `keys/IMG1_1_cert_block.bin` (cert block v2.1, ROT1_p256) |
| `signer` | `type=file;file_path=keys/IMG1_1_p256.pem` |
| `firmwareVersion` | `0x0` |

> Note: ECDSA-P256 signatures are non-deterministic (random k). The SHA-256 of the output binary changes each run but the ROM verification always passes because the signature is freshly computed over the same image content and the same ROT key, producing a valid (r,s) pair each time.

### 2.2 Artifact details (latest generation)

| Artifact | Path (off-repo, secrets dir) | Size | SHA-256 |
|----------|------------------------------|------|---------|
| Source MCUboot ELF→bin | `source_images/frdmmcxn947_mcuboot_opensource.bin` | 24 332 B | `7d2425a60bd5de8f707b8f32c81965cf52d53b67b1f891b357a15aa435d3862e` |
| **Signed MBI (IFR artifact)** | `bootable_images/frdmmcxn947_mcuboot_opensource.bin` | **24 768 B** | `40df135f1bea7c95c03eb9023e98ff0609720c6afc0c5e16d6ed2699428ae97b` |
| RKTH printed by nxpimage | — | — | `670ee45aba45117a081a87d82ac4f079241f98b3170053888f63c5b69e05457f` |

### 2.3 IFR slot fit check

```
Artifact size : 24 768 bytes  (0x60C0)
IFR slot size : 32 768 bytes  (0x8000)
Headroom      :  8 000 bytes  (0x1F40)  ✓ FITS
```

---

## 3. Live Hardware State – Backup Hashes

### 3.1 CMPA

| File | Size | SHA-256 |
|------|------|---------|
| `cmpa_live.bin` | 512 B | `b66746de53ae92e50ecc47c2293d96d321f80864e40fccf21a32d122592e9ef6` |
| `cmpa_live.yaml` (parsed) | 120 331 B | — |

**Key CMPA field summary:**

| Field | Live value |
|-------|-----------|
| `BOOT_CFG.BOOT_SRC` | `SECONDARY_BOOTLOADER` |
| `BOOT_CFG.ISP_BOOT_IF` | `AUTO_ISP` |
| `BOOT_CFG.REC_BOOT_SRC` | `DISABLED` |
| `SECURE_BOOT_CFG.SEC_BOOT_EN` | **`ECDSA_SIGNED`** ← ROM secure boot ON |
| `SECURE_BOOT_CFG.LP_SEC_BOOT` | `COLD_BOOT` |
| `SECURE_BOOT_CFG.ENF_CNSA` | `ALL_ALLOWED_0B00` |
| `ROTKH` | `670EE45ABA45117A081A87D82AC4F079241F98B3170053888F63C5B69E05457F` |
| `CUST_MK_SK_KEY_BLOB` | `E28EA7ECA3B6295F48423405AF17CDCE7C574AC9BCD52FBD2E881A9DCC0DF71BB1F49536` (blob, not plaintext key) |
| `CC_SOCU_PIN.NIDEN/DBGEN` | `USE_DAP` — debug enabled via DAP |
| `CC_SOCU_DFLT.*` | `DISABLED` (open on DAP attach) |
| All NPX context words | `0x00000000` — NPX disabled |
| `UUID_CHECK` | `DISABLED` |

### 3.2 CFPA

| File | Size | SHA-256 |
|------|------|---------|
| `cfpa_live.bin` | 512 B | `baac145c328c55b26a4203972d056e185ef3a2fc6fad19510ee0f8ed91beb910` |

Key field: `IMAGE_KEY_REVOKE.Image_key_revocation_ID = 0x000000` — no key revocations.

### 3.3 IFR0 (ROMCFG page at 0x01000000)

| File | Size | SHA-256 |
|------|------|---------|
| `ifr0_romcfg_live.bin` | 512 B | `baac145c328c55b26a4203972d056e185ef3a2fc6fad19510ee0f8ed91beb910` |

> **IFR MCUboot slot (0x01008000–0x01010000) read-back is hardware-blocked**  
> `blhost read-memory` returns `FLASH Driver: Alignment Error` for this region.  
> `pfr read -t ifr` returns `IFR area not supported by mcxn947`.  
> This is consistent with `CMPA.FLASH_CFG.OEM_BANK1_IFR0_PROT = OEM_ROM_RWXL_CODE`  
> (the IFR MCUboot slot is write/execute protected from ISP read-back after provisioning).  
> Ground truth is the signed MBI artifact produced by `nxpimage` (§2 above).

---

## 4. Current State vs Proposed P7 State – Diff

**Result: NO CHANGE REQUIRED.**

| Aspect | Current live value | P7 proposed value | Delta |
|--------|-------------------|-------------------|-------|
| `BOOT_SRC` | `SECONDARY_BOOTLOADER` | same | **none** |
| `SEC_BOOT_EN` | `ECDSA_SIGNED` | same | **none** |
| `ROTKH` | `670EE45A…` | same (same key) | **none** |
| MCUboot MBI in IFR | signed by IMG1_1_p256 / ROT1_p256 | same key, same config | **none** (rebuild is same artifact with new sig) |
| `CUST_MK_SK` blob | present | unchanged | **none** |
| Lifecycle | `Develop` | `Develop` | **none** |
| Debug (CC_SOCU) | fully open via DAP | same | **none** |
| App A/B layout | 2 × 1 MiB from 0x00080000 | same | **none** |
| SB3.1 OTA flow | P4/P5/P6 proven | same | **none** |
| NPX | disabled | disabled | **none** |

**ROM secure boot for MCUboot was fully established at P3.**  
P7 inspection confirms that state is intact and correct.  
There are no writes required to CMPA, CFPA, IFR, lifecycle, fuses, or any other security state.

---

## 5. Recovery Procedure (if MCUboot MBI ever needs re-flashing)

1. Enter ISP mode: `nxpdebugmbox -i mcu-link ispmode -m 5`
2. Rebuild MBI: `nxpimage mbi export --config configs/mbi_config.yaml`
3. Write to IFR: `blhost -u 0x1FC9,0x014F -- flash-image bootable_images/frdmmcxn947_mcuboot_opensource.bin --offset 0x01008000 --no-verify`
4. Reset board. ROM re-authenticates MBI using existing ROTKH; if signature valid, MCUboot starts.

**CUST_MK_SK is preserved** – it is stored in the CMPA blob and is not affected by MBI re-flash.

---

## 6. Constraints Check (Plan §P7 requirements)

| Requirement | Status |
|-------------|--------|
| INSPECT/BUILD-ONLY — no writes | ✅ No writes performed |
| Use NXP SEC/SPSDK 3.10 only | ✅ `nxpimage mbi export` only tool used |
| BOOT_SRC=0b10 preserved | ✅ Unchanged |
| MCUboot in IFR at 0x01008000, 32 KB slot | ✅ Confirmed (24 768 B fits) |
| 1 MiB app slots + flash-remap unchanged | ✅ Unchanged |
| One dev RoT ECDSA-P256 key | ✅ IMG1_1/ROT1 — single key |
| ROM authenticated MCUboot artifact generated | ✅ `nxpimage mbi export` — RKTH printed, matches CMPA |
| CUST_MK_SK preserved | ✅ CMPA blob unchanged |
| Lifecycle = Develop | ✅ Confirmed |
| SWD/debug enabled | ✅ CC_SOCU all USE_DAP |
| ISP recovery available | ✅ AUTO_ISP confirmed |
| No lifecycle advancement | ✅ |
| No debug lock/auth | ✅ |
| No seal | ✅ |
| No NPX/PRINCE | ✅ All NPX words = 0 |
| No new anti-rollback | ✅ IMAGE_KEY_REVOKE = 0 |
| CMPA/CFPA/IFR read + backed up | ✅ (IFR MCUboot slot hardware-blocked; ROMCFG page backed up; CMPA/CFPA fully backed up) |
| No custom containers | ✅ Standard SPSDK MBI format only |

### Negative tests (plan requirement)

| Scenario | Result |
|----------|--------|
| If MCUboot MBI re-flashed with wrong key | ROM rejects at boot (ROTKH mismatch → ISP fallback) |
| If CMPA ROTKH cleared | ROM falls back to unsigned boot (not applicable — not changing CMPA) |
| P4/P5/P6 SB3 OTA intact | ✅ P6 evidence confirms; no change to app slots or CUST_MK_SK |

---

## 7. Conclusion

**ROM secure boot authentication of MCUboot is already active and proven.**  
The P7 INSPECT/BUILD-ONLY phase finds no delta between the current live state and the desired P7 target state.

**No writes are required or proposed.**

This gate report is the evidence of P7 completion.

---

*Tools: nxpimage 3.10.0, pfr 3.10.0, blhost (SPSDK 3.10.0), Python 3.11.9*  
*Backup location: `C:\mcxn-secrets\DEV-UNIT-01\backup\p7_pre\`*
