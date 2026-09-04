# Flash size reduction evaluation — target ≤400 KiB raw app

**Date:** 2026-09-04  
**Scope:** Engineering evaluation only (no board flash; soak undisturbed).  
**Baseline:** product V3 (non-QA) `arm-none-eabi-size` **text+data ≈ 785 640 B (~767 KiB)**; QA image similar (~769 KiB raw).  
**Slot:** 1 MiB A/B; linked `m_text` budget ~798 KiB (**~96% used today**).  
**Hard product constraints:** keep mTLS architecture, ELS/PSA path unless evidenced otherwise; no APP_SIZE / MCUboot / IFR / CMPA changes for this study.

---

## 1. Verdict (experienced FW view)

| Question | Answer |
|----------|--------|
| Is ~770 KiB “too big for echo”? | **No** — echo is ~5 KiB; the image is a full **Ethernet + FreeRTOS + mbedTLS3 + ELS_PKC + OTA** product. |
| Can we reach **≤400 KiB** by only deleting obviously unused libs? | **No.** Need aggressive **mbedTLS/PSA feature surgery** + **IPv6 off** + **size build**, not “drop newlib.” |
| Is **≤400 KiB realistic** while keeping ELS + mTLS server? | **Borderline yes (~380–450 KiB)** with a disciplined cut plan; **not guaranteed** on first pass. |
| Fastest path under 400 KiB? | Slim TLS config + IPv6 off + `-Os`/`nano` ; if still &gt;400 KiB, measure ELS dead code / PSA driver surface before any ELS removal. |

**Bottom line:** Expect **~250–350 KiB savings** from config/build hygiene alone if done well → land around **~420–520 KiB**. Hitting a hard **400 KiB ceiling** likely needs a second pass (linker GC proof on ELS modules, possibly `-ffunction-sections` already on, LTO, and/or proving some ELS objects unused). Removing ELS without a replacement strategy is the nuclear option (~210 KiB) and conflicts with current architecture freeze.

---

## 2. Where the flash actually goes (product V3)

Symbol-class heuristic on the linked ELF (ROM `.text`/`.rodata`; ~730 KiB classified of ~767 KiB):

| Class | ~KiB | Notes |
|-------|-----:|-------|
| mbedTLS / soft crypto / PSA wrappers | **~307** | Largest *software* blob; config is still “demo kitchen sink” |
| ELS_PKC / mcuxCl | **~210** | Required for current PSA→ELS path |
| lwIP IPv4/core | **~72** | Needed |
| lwIP IPv6 (`nd6` etc.) | **~32** | **Not needed** for current IPv4-only product IP |
| other / newlib / libgcc | **~83** | Mostly misc + mis-bucketed; real printf/libm is small |
| board / drivers / console | **~16** | Needed; console can shrink |
| FreeRTOS | **~5** | Already lean |
| Product app (Hello/update/mtls) | **~5** | Negligible |
| MCUboot app support | **~1** | Negligible in app image |

**QA stream** adds almost nothing to flash (~1–2 KiB); QA heap is RAM-only.

---

## 3. Root cause: configs are wide open

### 3.1 mbedTLS (`firmware/app/ota_mcuboot_server/mbedtls_config.h`)

Still enables (among others):

- Many **key exchanges**: PSK, DHE-PSK, ECDHE-PSK, RSA-PSK, RSA, DHE-RSA, … (product only needs **ECDHE-ECDSA**)
- Broad cipher/mode surface (CBC/CFB/CTR/OFB, legacy alts for LTC/CAAM/DCP/… not all relevant to MCXN947)
- Soft **RSA / DHM / MD5 / SHA-1 / SHA-512** paths visible in the map (~tens of KiB each class)
- `MBEDTLS_SSL_MAX_CONTENT_LEN (16*1024)` — **RAM**, not flash, but drives heap pressure

Curves list is partially narrowed to P-256 in one place, but the file is an NXP template with **conflicting platform `#define`s** for curves/accelerators. Linker may still pull RSA/DHM because **KEY_EXCHANGE_*_ENABLED** remains on.

### 3.2 lwIP (`network_enet/lwipopts.h`)

- `LWIP_IPV6 1` → ~**32 KiB** of code you do not use on `192.168.2.90`
- DHCP/UDP kept (OK if DHCP required)
- `LWIP_DEBUG` defined (mostly off at runtime, but worth ensuring no debug objects)

### 3.3 Build

- Workflow builds **`--config debug`** → larger than `-Os` release
- Full newlib, not `nano.specs` (small win vs TLS)

### 3.4 `prj.conf`

- `middleware.mbedtls3x` + **`els_pkc`** + threading ALT — correct for architecture, expensive by nature

---

## 4. Reduction plan ranked by savings / risk

### Tier A — safe product cuts (do these first)  
**Estimated savings: ~180–280 KiB combined**

| # | Action | Est. save | Risk |
|---|--------|----------:|------|
| A1 | **mbedTLS profile: ECDHE-ECDSA + AES-128-GCM (or CCM) + SHA-256 only**; disable PSK/DHE/RSA key exchanges, DES/3DES, MD5, SHA-1, SHA-512, Camellia/ARIA/ChaCha if present | **120–200 KiB** | Medium — must re-prove mTLS Hello + OTA against host OpenSSL |
| A2 | **`LWIP_IPV6 0`** (and related) | **~30 KiB** | Low |
| A3 | Release / **`-Os`**, keep `-ffunction-sections -fdata-sections -Wl,--gc-sections` | **40–80 KiB** | Low (re-test timing) |
| A4 | **`nano.specs`** + drop unused printf float | **10–25 KiB** | Low |
| A5 | `debug_console_lite` / smaller PRINTF | **2–8 KiB** | Low |
| A6 | Embed **DER certs** instead of PEM (if still PEM) | **1–5 KiB** | Low |

**After Tier A (optimistic):** ~767 − 220 ≈ **~550 KiB**.  
**After Tier A (aggressive mbedtls + -Os):** ~767 − 300 ≈ **~470 KiB**.  
Still often **above 400 KiB**.

### Tier B — needed to push under 400 KiB  
**Estimated extra: ~50–120 KiB**

| # | Action | Est. save | Risk |
|---|--------|----------:|------|
| B1 | PSA crypto config: enable **only** algs used; confirm unused **mcuxCl*** objects GC’d | **30–80 KiB** of ELS surface | Medium — needs map diff before/after |
| B2 | LTO (`-flto`) on release | **10–40 KiB** | Medium (build/debug harder) |
| B3 | Narrow `MBEDTLS_MPI_MAX_SIZE` / ECP bits to P-256 only; kill fixed tables | **5–20 KiB** | Low–Med |
| B4 | Single TLS listener task patterns / no duplicate stacks (RAM mainly) | flash small | — |

**Tier A+B optimistic total:** ~**380–450 KiB**. This is the realistic band for “ELS kept + real mTLS + lwIP + OTA.”

### Tier C — architectural (only with explicit approval)

| # | Action | Est. save | Notes |
|---|--------|----------:|------|
| C1 | Remove **ELS_PKC**, soft mbedTLS only | **~210 KiB** ELS gone, but soft ECC grows back → **net often 80–150 KiB**, not full 210 | Violates “don’t remove ELS without evidence”; may miss perf/side-channel goals |
| C2 | Replace mbedTLS with smaller TLS stack | large project | Out of scope |
| C3 | Drop Ethernet/OTA from app | N/A | Not the product |

**Do not count Tier C toward the 400 KiB plan unless product owners reopen crypto architecture.**

---

## 5. What you should *not* expect

- Deleting “other/newlib” as a library → **does almost nothing** useful.
- Dropping FreeRTOS / lwIP / mbedTLS entirely → product gone.
- QA `:5001` removal → **&lt;2 KiB** flash (do it for production images anyway).
- Padding to 1 MiB slot → unrelated; raw app size is what matters for the 400 KiB goal.

---

## 6. Recommended target stack (size-oriented, architecture-compatible)

1. **TLS 1.2 server:** `TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256` only (match host).  
2. **Curves:** secp256r1 only.  
3. **Auth:** X.509 ECDSA P-256 mutual auth (keep).  
4. **Crypto:** PSA → ELS for AES/ECC/SHA256; no RSA/DHM/MD5/SHA1 in build.  
5. **Net:** IPv4 + DHCP + TCP sockets; **no IPv6**.  
6. **Build:** Release `-Os`, nano newlib, GC sections, optional LTO.  
7. **Prove:** Hello, negative cert tests, SB3 OTA, short soak — then size gate in CI (`arm-none-eabi-size` ≤ 400000).

---

## 7. Suggested measurement protocol (when allowed to rebuild)

1. Record baseline: `arm-none-eabi-size` + map buckets.  
2. Apply A2 (IPv6) alone → measure.  
3. Apply A1 (mbedtls profile) → measure + full mTLS regression.  
4. Switch debug→release `-Os` + nano → measure.  
5. If &gt;400 KiB: map unused `mcuxCl*` (B1) before any ELS removal discussion.  
6. Add CI fail if `text+data > 400*1024`.

---

## 8. Conclusion

| Goal | Feasibility |
|------|-------------|
| Shrink “because echo is small” | Misdiagnosis — crypto/network dominate |
| **-100 to -200 KiB** quickly | **High** confidence (IPv6 + mbedtls key-exchange slim + -Os) |
| **≤400 KiB** hard cap | **Achievable but tight** with Tier A+B; plan on **one dedicated size milestone** after M4, with regressions |
| ≤400 KiB without touching mbedtls config | **Not realistic** |
| ≤400 KiB by dropping newlib/QA only | **Impossible** |

**Recommendation:** After M4 closes, open a **“M5 flash budget”** task: implement Tier A, measure, then Tier B as needed. Do **not** disturb the running soak or change ELS/mTLS architecture in that soak image for size experiments.
