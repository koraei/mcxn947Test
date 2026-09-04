/*
 * On-device encrypted running-hours journal (AES-256-GCM).
 * Protocol matches tools/runhours_host_model.py / Rev B §§7–10.
 */
#include "runhours_journal.h"
#include "runhours_crypto.h"
#include "runhours_keystore.h"
#include "flash_arbiter.h"
#include "flash_range_guard.h"
#include "memory_layout.h"

#if defined(APP_RH_ENDURANCE_TEST) && (APP_RH_ENDURANCE_TEST)
#include "runhours_stress.h"
#endif

#include "diagnostics.h"
#include "mcuboot_app_support.h"
#include "mflash_drv.h"

#include "fsl_debug_console.h"
#include "fsl_common.h"

#include "FreeRTOS.h"
#include "task.h"

#include <stdint.h>
#include <string.h>

#if !defined(APP_FLASH_LAYOUT_512K)

rh_status_t rh_journal_init(void)
{
    return RH_ERR_NOT_PROVISIONED;
}
rh_status_t rh_journal_get_quanta(uint64_t *out)
{
    if (out)
    {
        *out = 0;
    }
    return RH_ERR_NOT_PROVISIONED;
}
rh_status_t rh_journal_append_quanta(uint64_t q)
{
    (void)q;
    return RH_ERR_NOT_PROVISIONED;
}
uint64_t rh_journal_seconds(void)
{
    return 0;
}
void rh_journal_get_diag(rh_diag_t *out)
{
    if (out)
    {
        memset(out, 0, sizeof(*out));
    }
}
rh_status_t rh_journal_force_next_quantum(void)
{
    return RH_ERR_NOT_PROVISIONED;
}
void rh_journal_arm_fault(rh_fault_stage_t s)
{
    (void)s;
}
rh_fault_stage_t rh_journal_fault_armed(void)
{
    return RH_FAULT_NONE;
}
rh_status_t rh_journal_wipe_and_init(void)
{
    return RH_ERR_NOT_PROVISIONED;
}

#else /* APP_FLASH_LAYOUT_512K */

static uint64_t s_seq;
static uint64_t s_quanta;
static int s_ready;
static uint16_t s_write_sector;
static uint64_t s_write_gen;
static uint32_t s_boot_id;
static rh_diag_t s_diag;
static volatile rh_fault_stage_t s_fault = RH_FAULT_NONE;

static void fault_hit(rh_fault_stage_t stage)
{
    if (s_fault == stage)
    {
        PRINTF("rh: FAULT wait stage=%u (reset me)\r\n", (unsigned)stage);
        for (;;)
        {
            /* Host issues LinkServer/power cut */
        }
    }
}

static uint32_t sector_base(uint16_t sid)
{
    if (sid < RH_POOL_A_SECTORS)
    {
        return ML_RUNHOURS_POOL_A + (uint32_t)sid * RH_SECTOR_SIZE;
    }
    return ML_RUNHOURS_POOL_B + (uint32_t)(sid - RH_POOL_A_SECTORS) * RH_SECTOR_SIZE;
}

static int sector_is_exec_bank(uint16_t sid)
{
    const int sid_in_b = (sid >= RH_POOL_A_SECTORS) ? 1 : 0;
    const int exec_b   = bl_flash_remap_active() ? 1 : 0;
    return sid_in_b == exec_b;
}

static void rh_flash_invalidate(uint32_t addr, uint32_t len)
{
    (void)addr;
    (void)len;
    /* Match mflash FMU flash_cache_clear — avoid stale speculative/cached reads. */
    if ((SYSCON->NVM_CTRL & SYSCON_NVM_CTRL_DIS_FLASH_CACHE_MASK) == 0U)
    {
        SYSCON->NVM_CTRL |= SYSCON_NVM_CTRL_CLR_FLASH_CACHE_MASK;
        SYSCON->NVM_CTRL &= ~SYSCON_NVM_CTRL_CLR_FLASH_CACHE_MASK;
    }
    __DSB();
    __ISB();
}

static int region_all_ff(uint32_t addr, uint32_t len)
{
    rh_flash_invalidate(addr, len);
    const uint8_t *p = (const uint8_t *)addr;
    for (uint32_t i = 0; i < len; i++)
    {
        if (p[i] != 0xFFu)
        {
            return 0;
        }
    }
    return 1;
}

static int phrase_program(uint32_t addr, const uint8_t data[16])
{
    uint32_t words[4];
    int32_t rc;

    if (!flash_guard_runhours_range_ok(addr, 16u))
    {
        s_diag.flash_errors++;
        return -1;
    }
    memcpy(words, data, 16);
    rc = mflash_drv_phrase_program(addr, words);
    if (rc != 0)
    {
        s_diag.flash_errors++;
        return -1;
    }
    rh_flash_invalidate(addr, 16);
    if (memcmp((const void *)addr, data, 16) != 0)
    {
        s_diag.flash_errors++;
        return -1;
    }
    s_diag.write_count++;
    return 0;
}

static int sector_erase(uint16_t sid)
{
    uint32_t addr = sector_base(sid);
    int32_t rc;

    if (!flash_guard_runhours_range_ok(addr, RH_SECTOR_SIZE))
    {
        s_diag.flash_errors++;
        return -1;
    }
    fault_hit(RH_FAULT_DURING_ERASE);
    rc = mflash_drv_sector_erase(addr);
    rh_flash_invalidate(addr, RH_SECTOR_SIZE);
    /*
     * Re-erase of an already-erased sector often returns fail on MCXN FMU.
     * CPU blank-verify is also unreliable (CACHE64/speculation). Trust later
     * phrase programs + AES-GCM auth; count only successful erase statuses.
     */
    if (rc == 0)
    {
        s_diag.erase_count++;
#if defined(APP_RH_ENDURANCE_TEST) && (APP_RH_ENDURANCE_TEST)
        rh_erase_note(addr, sid, 1, s_seq, s_quanta,
                      (uint8_t)(bl_flash_remap_active() ? 1 : 0));
#endif
    }
    else
    {
        PRINTF("rh: erase rc=%ld @0x%08lx (ignored if virgin)\r\n", (long)rc, (unsigned long)addr);
#if defined(APP_RH_ENDURANCE_TEST) && (APP_RH_ENDURANCE_TEST)
        rh_erase_note(addr, sid, 0, s_seq, s_quanta,
                      (uint8_t)(bl_flash_remap_active() ? 1 : 0));
#endif
    }
    return 0;
}

static int header_ready(uint16_t sid, uint64_t *out_gen)
{
    const uint8_t *hdr = (const uint8_t *)sector_base(sid);
    uint32_t magic;
    uint16_t ver, hsz, id, rsv;
    uint64_t gen;
    uint32_t crc_stored, crc;

    memcpy(&magic, hdr, 4);
    if (magic != RH_MAGIC_HDR)
    {
        return 0;
    }
    memcpy(&ver, hdr + 4, 2);
    memcpy(&hsz, hdr + 6, 2);
    memcpy(&id, hdr + 8, 2);
    memcpy(&rsv, hdr + 10, 2);
    (void)rsv;
    if (ver != RH_FORMAT_VER || hsz != RH_HEADER_SIZE || id != sid)
    {
        return 0;
    }
    memcpy(&gen, hdr + 12, 8);
    if (gen == 0ull || gen == ~0ull)
    {
        return 0;
    }
    memcpy(&crc_stored, hdr + 24, 4);
    crc = rh_crc32(hdr, 24);
    if (crc != crc_stored)
    {
        return 0;
    }
    if (memcmp(hdr + 48, RH_READY_MARKER_BYTES, 16) != 0)
    {
        return 0;
    }
    if (out_gen)
    {
        *out_gen = gen;
    }
    return 1;
}

static int record_committed(const uint8_t *rec, uint64_t *out_seq)
{
    uint32_t magic, ver;
    uint64_t seq, cm, comp;

    memcpy(&magic, rec, 4);
    memcpy(&ver, rec + 4, 4);
    memcpy(&seq, rec + 8, 8);
    if (magic != RH_MAGIC_REC || ver != RH_FORMAT_VER)
    {
        return 0;
    }
    memcpy(&cm, rec + 48, 8);
    memcpy(&comp, rec + 56, 8);
    if (cm != RH_COMMIT_MAGIC || comp != (seq ^ ~0ull))
    {
        return 0;
    }
    if (out_seq)
    {
        *out_seq = seq;
    }
    return 1;
}

static int decrypt_record(const uint8_t *rec, uint64_t gen, uint16_t sid, uint16_t slot, int require_commit,
                          uint64_t *out_quanta, uint64_t *out_seq)
{
    uint32_t magic, ver;
    uint64_t seq;
    uint8_t nonce[12];
    uint8_t aad[32];
    size_t aad_len = 0;
    uint8_t plain[16];

    if (require_commit && !record_committed(rec, &seq))
    {
        if (!region_all_ff((uint32_t)(uintptr_t)rec, RH_RECORD_SIZE))
        {
            /* non-erased invalid → torn */
            s_diag.torn_recoveries++;
        }
        return -1;
    }
    memcpy(&magic, rec, 4);
    memcpy(&ver, rec + 4, 4);
    memcpy(&seq, rec + 8, 8);
    if (magic != RH_MAGIC_REC || ver != RH_FORMAT_VER)
    {
        return -1;
    }

    rh_nonce_build(nonce, gen, slot);
    rh_aad_build(aad, &aad_len, seq, gen, sid, slot);
    if (rh_aes_gcm_decrypt(nonce, aad, aad_len, rec + 16, rec + 32, plain) != 0)
    {
        s_diag.auth_fail++;
        return -1;
    }
    if (out_quanta)
    {
        memcpy(out_quanta, plain, 8);
    }
    if (out_seq)
    {
        *out_seq = seq;
    }
    return 0;
}

static int write_sector_header(uint16_t sid, uint64_t generation)
{
    uint8_t hdr[RH_HEADER_SIZE];
    uint32_t base = sector_base(sid);
    uint32_t crc;
    uint16_t ver = RH_FORMAT_VER;
    uint16_t hsz = RH_HEADER_SIZE;
    uint16_t rsv = 0;
    uint32_t magic = RH_MAGIC_HDR;

    memset(hdr, 0xFF, sizeof(hdr));
    memcpy(hdr + 0, &magic, 4);
    memcpy(hdr + 4, &ver, 2);
    memcpy(hdr + 6, &hsz, 2);
    memcpy(hdr + 8, &sid, 2);
    memcpy(hdr + 10, &rsv, 2);
    memcpy(hdr + 12, &generation, 8);
    memcpy(hdr + 20, &s_boot_id, 4);
    crc = rh_crc32(hdr, 24);
    memcpy(hdr + 24, &crc, 4);

    fault_hit(RH_FAULT_BEFORE_READY);
    for (uint32_t i = 0; i < 48; i += 16)
    {
        if (phrase_program(base + i, hdr + i) != 0)
        {
            return -1;
        }
    }
    if (phrase_program(base + 48, RH_READY_MARKER_BYTES) != 0)
    {
        return -1;
    }
    if (!header_ready(sid, NULL))
    {
        return -1;
    }
    return 0;
}

static int find_free_slot(uint16_t sid, uint16_t *out_slot)
{
    uint32_t off = sector_base(sid) + RH_HEADER_SIZE;
    for (uint16_t slot = 0; slot < RH_SLOTS_PER_SECTOR; slot++)
    {
        if (region_all_ff(off + (uint32_t)slot * RH_RECORD_SIZE, RH_RECORD_SIZE))
        {
            *out_slot = slot;
            return 0;
        }
    }
    return -1;
}

static int append_record(uint16_t sid, uint64_t generation, uint64_t quanta)
{
    uint16_t slot;
    uint32_t base;
    uint64_t seq;
    uint8_t plain[16];
    uint8_t ct[16];
    uint8_t tag[16];
    uint8_t nonce[12];
    uint8_t aad[32];
    size_t aad_len = 0;
    uint8_t ph0[16], ph3[16];
    uint32_t magic = RH_MAGIC_REC;
    uint32_t ver = RH_FORMAT_VER;
    uint64_t cm = RH_COMMIT_MAGIC;
    uint64_t comp;
    uint8_t pre[64];

    if (find_free_slot(sid, &slot) != 0)
    {
        return -2; /* full */
    }

    fault_hit(RH_FAULT_BEFORE_RECORD);

    seq = s_seq + 1ull;
    memset(plain, 0, sizeof(plain));
    memcpy(plain, &quanta, 8);
    memcpy(plain + 8, &s_boot_id, 4); /* flags=0 already; boot_id_low at +12 would overlap — match host <QII */
    {
        uint32_t flags = 0;
        memcpy(plain + 8, &flags, 4);
        memcpy(plain + 12, &s_boot_id, 4);
    }

    rh_nonce_build(nonce, generation, slot);
    rh_aad_build(aad, &aad_len, seq, generation, sid, slot);
    if (rh_aes_gcm_encrypt(nonce, aad, aad_len, plain, ct, tag) != 0)
    {
        s_diag.crypto_errors++;
        return -1;
    }

    memset(ph0, 0, sizeof(ph0));
    memcpy(ph0 + 0, &magic, 4);
    memcpy(ph0 + 4, &ver, 4);
    memcpy(ph0 + 8, &seq, 8);
    comp = seq ^ ~0ull;
    memcpy(ph3 + 0, &cm, 8);
    memcpy(ph3 + 8, &comp, 8);

    base = sector_base(sid) + RH_HEADER_SIZE + (uint32_t)slot * RH_RECORD_SIZE;

    fault_hit(RH_FAULT_DURING_PHRASE0);
    if (phrase_program(base + 0, ph0) != 0)
    {
        return -1;
    }
    fault_hit(RH_FAULT_DURING_PHRASE1);
    if (phrase_program(base + 16, ct) != 0)
    {
        return -1;
    }
    fault_hit(RH_FAULT_DURING_PHRASE2);
    if (phrase_program(base + 32, tag) != 0)
    {
        return -1;
    }

    memcpy(pre, (const void *)base, 48);
    memset(pre + 48, 0xFF, 16);
    if (decrypt_record(pre, generation, sid, slot, 0, NULL, NULL) != 0)
    {
        s_diag.crypto_errors++;
        return -1;
    }

    fault_hit(RH_FAULT_BEFORE_COMMIT);
    if (phrase_program(base + 48, ph3) != 0)
    {
        return -1;
    }
    fault_hit(RH_FAULT_AFTER_COMMIT);

    if (decrypt_record((const uint8_t *)base, generation, sid, slot, 1, NULL, NULL) != 0)
    {
        return -1;
    }

    s_seq = seq;
    s_quanta = quanta;
    s_write_sector = sid;
    s_write_gen = generation;
    s_diag.seq = seq;
    s_diag.quanta = quanta;
    s_diag.active_sector = sid;
    return 0;
}

static int recycle_and_append(uint64_t quanta)
{
    uint16_t cur = s_write_sector;
    uint64_t cur_gen = s_write_gen;
    uint16_t victim = 0xFFFF;
    uint64_t new_gen;
    int pass;

    /*
     * Prefer a victim on the non-executing physical bank (plan §11).
     * Never erase the sector that holds the latest authenticated record (cur).
     */
    for (pass = 0; pass < 2 && victim == 0xFFFF; pass++)
    {
        for (uint16_t i = 1; i < RH_SECTOR_COUNT; i++)
        {
            uint16_t v = (uint16_t)((cur + i) % RH_SECTOR_COUNT);
            uint64_t vgen = 0;
            if (v == cur)
            {
                continue;
            }
            if (pass == 0 && sector_is_exec_bank(v))
            {
                continue; /* prefer opposite bank first */
            }
            if (header_ready(v, &vgen) && vgen >= cur_gen)
            {
                continue;
            }
            victim = v;
            break;
        }
    }
    if (victim == 0xFFFF)
    {
        return -1;
    }

    new_gen = cur_gen + 1ull;
    if (new_gen < cur_gen)
    {
        return -1; /* wrap terminal */
    }

    PRINTF("rh: recycle cur=%u -> victim=%u gen=%lu\r\n", (unsigned)cur, (unsigned)victim,
           (unsigned long)new_gen);

    if (sector_erase(victim) != 0)
    {
        PRINTF("rh: recycle erase fail\r\n");
        return -1;
    }
    if (write_sector_header(victim, new_gen) != 0)
    {
        PRINTF("rh: recycle header fail\r\n");
        return -1;
    }
    fault_hit(RH_FAULT_AFTER_READY_BEFORE_CKPT);
    if (append_record(victim, new_gen, quanta) != 0)
    {
        PRINTF("rh: recycle append fail\r\n");
        return -1;
    }
    fault_hit(RH_FAULT_AFTER_CHECKPOINT);
    return 0;
}

/* Returns 1 if a valid record was found, 0 if none, -1 on hard failure. */
static int scan_find_best(int *out_any_non_ff)
{
    uint64_t best_seq = 0;
    uint64_t best_q = 0;
    int found = 0;
    int any_non_ff = 0;
    uint16_t best_sid = 0;
    uint64_t best_gen = 0;

    for (uint16_t sid = 0; sid < RH_SECTOR_COUNT; sid++)
    {
        uint32_t base = sector_base(sid);
        uint64_t gen = 0;

        if (!region_all_ff(base, RH_SECTOR_SIZE))
        {
            any_non_ff = 1;
        }
        if (!header_ready(sid, &gen))
        {
            continue;
        }
        for (uint16_t slot = 0; slot < RH_SLOTS_PER_SECTOR; slot++)
        {
            const uint8_t *rec = (const uint8_t *)(base + RH_HEADER_SIZE + (uint32_t)slot * RH_RECORD_SIZE);
            uint64_t q = 0, seq = 0;

            if (region_all_ff((uint32_t)(uintptr_t)rec, RH_RECORD_SIZE))
            {
                continue;
            }
            if (decrypt_record(rec, gen, sid, slot, 1, &q, &seq) != 0)
            {
                continue;
            }
            if (!found || seq >= best_seq)
            {
                found = 1;
                best_seq = seq;
                best_q = q;
                best_sid = sid;
                best_gen = gen;
            }
        }
    }

    if (out_any_non_ff)
    {
        *out_any_non_ff = any_non_ff;
    }
    if (!found)
    {
        return 0;
    }
    s_seq = best_seq;
    s_quanta = best_q;
    s_write_sector = best_sid;
    s_write_gen = best_gen;
    s_ready = 1;
    s_diag.provisioned = 1;
    s_diag.seq = best_seq;
    s_diag.quanta = best_q;
    s_diag.active_sector = best_sid;
    return 1;
}

static int scan_recover(void)
{
    int any_non_ff = 0;
    int found = scan_find_best(&any_non_ff);

    if (found < 0)
    {
        return -1;
    }
    if (found)
    {
        return 0;
    }
    if (!any_non_ff)
    {
        uint16_t sid0 = sector_is_exec_bank(0) ? RH_POOL_A_SECTORS : 0;
        if (sector_erase(sid0) != 0 || write_sector_header(sid0, 1) != 0)
        {
            return -1;
        }
        s_seq = 0;
        s_quanta = 0;
        if (append_record(sid0, 1, 0) != 0)
        {
            return -1;
        }
        s_ready = 1;
        s_diag.provisioned = 1;
        return 0;
    }
    PRINTF("rh: JOURNAL CORRUPT (non-virgin, no valid record)\r\n");
    return -1;
}

static int migrate_append_cb(uint64_t quanta, void *ctx)
{
    int rc;
    (void)ctx;
    if (flash_arbiter_acquire(FLASH_OWNER_JOURNAL, 5000) != 0)
    {
        return -1;
    }
    if (sector_is_exec_bank(s_write_sector))
    {
        rc = recycle_and_append(quanta);
    }
    else
    {
        rc = append_record(s_write_sector, s_write_gen, quanta);
        if (rc == -2)
        {
            rc = recycle_and_append(quanta);
        }
    }
    flash_arbiter_release(FLASH_OWNER_JOURNAL);
    return (rc == 0) ? 0 : -1;
}

static void diag_fill_key(void)
{
    s_diag.key_version = (uint8_t)rh_crypto_key_version();
    s_diag.key_id = rh_crypto_key_id();
    s_diag.key_ks_state = rh_crypto_ks_state();
}

rh_status_t rh_journal_init(void)
{
    int any_non_ff = 0;
    int found;

    memset(&s_diag, 0, sizeof(s_diag));
    s_ready = 0;
    s_boot_id = (uint32_t)xTaskGetTickCount() ^ 0xA5A5u;
    s_diag.remap_active = (uint8_t)(bl_flash_remap_active() ? 1 : 0);

    flash_arbiter_init();

    if (rh_crypto_init(diagnostics_uuid_bytes()) != 0)
    {
        s_diag.crypto_errors++;
        return RH_ERR_IO;
    }

    if (flash_arbiter_acquire(FLASH_OWNER_JOURNAL, 5000) != 0)
    {
        return RH_ERR_BUSY;
    }

    if (rh_crypto_is_v2())
    {
        found = scan_find_best(&any_non_ff);
        if (found == 1)
        {
            /* Staged blob + authenticable v2 record → commit version. */
            if (rh_crypto_ks_state() == (uint8_t)RH_KS_BLOB_STAGED)
            {
                flash_arbiter_release(FLASH_OWNER_JOURNAL);
                if (rh_crypto_try_commit_if_ready() != 0)
                {
                    s_diag.crypto_errors++;
                    rh_crypto_zeroize();
                    return RH_ERR_IO;
                }
                if (flash_arbiter_acquire(FLASH_OWNER_JOURNAL, 5000) != 0)
                {
                    return RH_ERR_BUSY;
                }
            }
            flash_arbiter_release(FLASH_OWNER_JOURNAL);
            diag_fill_key();
            PRINTF("rh: ready v2 seq=%lu quanta=%lu key_id=%u\r\n", (unsigned long)s_seq,
                   (unsigned long)s_quanta, (unsigned)s_diag.key_id);
            return RH_OK;
        }

        /* No v2 record yet: fall back to v1 value, keep staged blob. */
        flash_arbiter_release(FLASH_OWNER_JOURNAL);
        if (rh_crypto_fallback_v1(diagnostics_uuid_bytes()) != 0)
        {
            s_diag.crypto_errors++;
            return RH_ERR_IO;
        }
        if (flash_arbiter_acquire(FLASH_OWNER_JOURNAL, 5000) != 0)
        {
            return RH_ERR_BUSY;
        }
        if (scan_recover() != 0)
        {
            flash_arbiter_release(FLASH_OWNER_JOURNAL);
            rh_crypto_zeroize();
            return RH_ERR_CORRUPT;
        }
        flash_arbiter_release(FLASH_OWNER_JOURNAL);

        if (rh_crypto_migrate_to_v2(s_quanta, s_seq, migrate_append_cb, NULL) != 0)
        {
            s_diag.crypto_errors++;
            diag_fill_key();
            PRINTF("rh: migrate fail (v1 still usable)\r\n");
            /* Keep v1 operational if migrate interrupted before commit. */
            if (!rh_crypto_is_v2())
            {
                if (rh_crypto_fallback_v1(diagnostics_uuid_bytes()) != 0)
                {
                    return RH_ERR_IO;
                }
            }
            diag_fill_key();
            return RH_OK;
        }
        diag_fill_key();
        PRINTF("rh: ready migrated seq=%lu quanta=%lu key_id=%u\r\n", (unsigned long)s_seq,
               (unsigned long)s_quanta, (unsigned)s_diag.key_id);
        return RH_OK;
    }

    /* Fresh v1 path (no committed/staged opaque key). */
    if (scan_recover() != 0)
    {
        flash_arbiter_release(FLASH_OWNER_JOURNAL);
        rh_crypto_zeroize();
        return RH_ERR_CORRUPT;
    }
    flash_arbiter_release(FLASH_OWNER_JOURNAL);

    if (rh_crypto_migrate_to_v2(s_quanta, s_seq, migrate_append_cb, NULL) != 0)
    {
        s_diag.crypto_errors++;
        /* Stay on v1 so board remains usable; next boot retries. */
        if (rh_crypto_fallback_v1(diagnostics_uuid_bytes()) != 0)
        {
            return RH_ERR_IO;
        }
        diag_fill_key();
        PRINTF("rh: ready v1 (migrate pending) seq=%lu quanta=%lu\r\n", (unsigned long)s_seq,
               (unsigned long)s_quanta);
        return RH_OK;
    }

    diag_fill_key();
    PRINTF("rh: ready seq=%lu quanta=%lu sector=%u remap=%u key_ver=%u\r\n", (unsigned long)s_seq,
           (unsigned long)s_quanta, (unsigned)s_write_sector, (unsigned)s_diag.remap_active,
           (unsigned)s_diag.key_version);
    return RH_OK;
}

rh_status_t rh_journal_get_quanta(uint64_t *out_quanta)
{
    if (out_quanta == NULL)
    {
        return RH_ERR_IO;
    }
    if (!s_ready)
    {
        return RH_ERR_NOT_PROVISIONED;
    }
    *out_quanta = s_quanta;
    return RH_OK;
}

rh_status_t rh_journal_append_quanta(uint64_t quanta)
{
    int rc;

    if (!s_ready)
    {
        return RH_ERR_NOT_PROVISIONED;
    }
    if (flash_arbiter_acquire(FLASH_OWNER_JOURNAL, 0) != 0)
    {
        flash_arbiter_note_journal_deferred();
        s_diag.deferred_ota = flash_arbiter_journal_deferred_count();
        return RH_ERR_BUSY;
    }

    /* If active sector is on the executing bank, checkpoint to the other bank first. */
    if (sector_is_exec_bank(s_write_sector))
    {
        if (recycle_and_append(s_quanta) != 0)
        {
            flash_arbiter_release(FLASH_OWNER_JOURNAL);
            return RH_ERR_IO;
        }
    }

    rc = append_record(s_write_sector, s_write_gen, quanta);
    if (rc == -2)
    {
        rc = recycle_and_append(quanta);
    }
    flash_arbiter_release(FLASH_OWNER_JOURNAL);
    s_diag.deferred_ota = flash_arbiter_journal_deferred_count();

    if (rc != 0)
    {
        return RH_ERR_IO;
    }
    return RH_OK;
}

uint64_t rh_journal_seconds(void)
{
    uint64_t q = 0;
    if (rh_journal_get_quanta(&q) != RH_OK)
    {
        return 0;
    }
    return q * (uint64_t)RH_QUANTUM_SECONDS;
}

void rh_journal_get_diag(rh_diag_t *out)
{
    if (out == NULL)
    {
        return;
    }
    *out = s_diag;
    out->deferred_ota = flash_arbiter_journal_deferred_count();
    out->remap_active = (uint8_t)(bl_flash_remap_active() ? 1 : 0);
    out->key_version = (uint8_t)rh_crypto_key_version();
    out->key_id = rh_crypto_key_id();
    out->key_ks_state = rh_crypto_ks_state();
}

rh_status_t rh_journal_force_next_quantum(void)
{
    if (!s_ready)
    {
        return RH_ERR_NOT_PROVISIONED;
    }
    return rh_journal_append_quanta(s_quanta + 1ull);
}

void rh_journal_arm_fault(rh_fault_stage_t stage)
{
    s_fault = stage;
}

rh_fault_stage_t rh_journal_fault_armed(void)
{
    return s_fault;
}

rh_status_t rh_journal_wipe_and_init(void)
{
    if (flash_arbiter_acquire(FLASH_OWNER_JOURNAL, 5000) != 0)
    {
        return RH_ERR_BUSY;
    }
    for (uint16_t sid = 0; sid < RH_SECTOR_COUNT; sid++)
    {
        if (sector_erase(sid) != 0)
        {
            flash_arbiter_release(FLASH_OWNER_JOURNAL);
            return RH_ERR_IO;
        }
    }
    s_seq = 0;
    s_quanta = 0;
    s_ready = 0;
    {
        uint16_t sid0 = sector_is_exec_bank(0) ? RH_POOL_A_SECTORS : 0;
        if (write_sector_header(sid0, 1) != 0 || append_record(sid0, 1, 0) != 0)
        {
            flash_arbiter_release(FLASH_OWNER_JOURNAL);
            return RH_ERR_IO;
        }
    }
    s_ready = 1;
    s_diag.provisioned = 1;
    flash_arbiter_release(FLASH_OWNER_JOURNAL);
    return RH_OK;
}

#endif /* APP_FLASH_LAYOUT_512K */
