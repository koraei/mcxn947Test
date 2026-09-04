#include "runhours_keystore.h"
#include "flash_arbiter.h"
#include "flash_range_guard.h"
#include "memory_layout.h"

#include "mflash_drv.h"

#include "fsl_common.h"
#include "fsl_debug_console.h"

#include <string.h>

#if defined(APP_FLASH_LAYOUT_512K)

#define RH_KS_SLOT_SIZE       (8192u)
#define RH_KS_SLOT0           (ML_PLATFORM_RESERVE_A)
#define RH_KS_SLOT1           (ML_PLATFORM_RESERVE_A + RH_KS_SLOT_SIZE)
#define RH_KS_REC_OFF         (0u)
#define RH_KS_HDR_BYTES       (32u)
#define RH_KS_BLOB_OFF        (32u)
#define RH_KS_STAGE_OFF       (96u)
#define RH_KS_COMMIT_OFF      (112u)
#define RH_KS_LAYOUT_VER      (1u)

static const uint8_t k_stage_mark[16] = {'B', 'L', 'O', 'B', '_', 'S', 'T', 'A',
                                         'G', 'E', 'D', '_', 'v', '1', 0, 0};
static const uint8_t k_commit_mark[16] = {'R', 'H', '_', 'K', 'E', 'Y', '_', 'V',
                                          'E', 'R', '=', '2', 0, 0, 0, 0};

uint32_t rh_keystore_crc32(const uint8_t *data, size_t len)
{
    uint32_t crc = 0xffffffffu;
    for (size_t i = 0; i < len; i++)
    {
        crc ^= data[i];
        for (int b = 0; b < 8; b++)
        {
            uint32_t mask = -(crc & 1u);
            crc = (crc >> 1) ^ (0xedb88320u & mask);
        }
    }
    return ~crc;
}

static void flash_invalidate(uint32_t addr, uint32_t len)
{
    (void)addr;
    (void)len;
    if ((SYSCON->NVM_CTRL & SYSCON_NVM_CTRL_DIS_FLASH_CACHE_MASK) == 0U)
    {
        SYSCON->NVM_CTRL |= SYSCON_NVM_CTRL_CLR_FLASH_CACHE_MASK;
        SYSCON->NVM_CTRL &= ~SYSCON_NVM_CTRL_CLR_FLASH_CACHE_MASK;
    }
    __DSB();
    __ISB();
}

static int phrase_program(uint32_t addr, const uint8_t data[16])
{
    uint32_t words[4];
    if (!flash_guard_platform_reserve_ok(addr, 16u))
    {
        return -1;
    }
    memcpy(words, data, 16);
    if (mflash_drv_phrase_program(addr, words) != 0)
    {
        return -1;
    }
    flash_invalidate(addr, 16u);
    return 0;
}

static int sector_erase(uint32_t addr)
{
    if (!flash_guard_platform_reserve_ok(addr, RH_KS_SLOT_SIZE))
    {
        return -1;
    }
    if (mflash_drv_sector_erase(addr) != 0)
    {
        return -1;
    }
    flash_invalidate(addr, RH_KS_SLOT_SIZE);
    return 0;
}

static int region_eq(uint32_t addr, const uint8_t *ref, size_t len)
{
    flash_invalidate(addr, (uint32_t)len);
    return memcmp((const void *)addr, ref, len) == 0;
}

static int region_all_ff(uint32_t addr, size_t len)
{
    flash_invalidate(addr, (uint32_t)len);
    const uint8_t *p = (const uint8_t *)addr;
    for (size_t i = 0; i < len; i++)
    {
        if (p[i] != 0xFFu)
        {
            return 0;
        }
    }
    return 1;
}

static int parse_slot(uint32_t base, rh_ks_record_t *out)
{
    uint8_t hdr[RH_KS_HDR_BYTES];
    uint32_t magic, crc_stored, crc_calc;
    uint16_t layout, key_id, key_ver, blob_len;
    uint32_t epoch;
    uint64_t qsnap, ssnap;

    flash_invalidate(base, 128u);
    if (region_all_ff(base, 128u))
    {
        return -1;
    }
    memcpy(hdr, (const void *)base, sizeof(hdr));
    memcpy(&magic, hdr + 0, 4);
    memcpy(&layout, hdr + 4, 2);
    memcpy(&key_id, hdr + 6, 2);
    memcpy(&key_ver, hdr + 8, 2);
    memcpy(&blob_len, hdr + 10, 2);
    memcpy(&epoch, hdr + 12, 4);
    memcpy(&qsnap, hdr + 16, 8);
    memcpy(&ssnap, hdr + 24, 8);
    /* crc at end of packed header area before blob — use bytes 0..27 + blob */
    if (magic != RH_KS_MAGIC || layout != RH_KS_LAYOUT_VER)
    {
        return -1;
    }
    if (blob_len == 0u || blob_len > RH_KS_BLOB_MAX)
    {
        return -1;
    }
    memcpy(&crc_stored, (const void *)(base + 28), 4);
    /* CRC over header[0..27] || blob */
    {
        uint8_t tmp[28 + RH_KS_BLOB_MAX];
        memcpy(tmp, (const void *)base, 28);
        memcpy(tmp + 28, (const void *)(base + RH_KS_BLOB_OFF), blob_len);
        crc_calc = rh_keystore_crc32(tmp, 28u + blob_len);
    }
    if (crc_calc != crc_stored)
    {
        return -1;
    }
    if (!region_eq(base + RH_KS_STAGE_OFF, k_stage_mark, 16))
    {
        return -1;
    }

    memset(out, 0, sizeof(*out));
    out->key_id = key_id;
    out->key_version = key_ver;
    out->blob_len = blob_len;
    out->epoch = epoch;
    out->quanta_snap = qsnap;
    out->seq_snap = ssnap;
    memcpy(out->blob, (const void *)(base + RH_KS_BLOB_OFF), blob_len);
    if (region_eq(base + RH_KS_COMMIT_OFF, k_commit_mark, 16))
    {
        out->state = RH_KS_COMMITTED;
        out->key_version = RH_KEY_VERSION_V2;
    }
    else if (region_all_ff(base + RH_KS_COMMIT_OFF, 16))
    {
        out->state = RH_KS_BLOB_STAGED;
    }
    else
    {
        return -1; /* torn commit marker */
    }
    return 0;
}

int rh_keystore_load(rh_ks_record_t *out)
{
    rh_ks_record_t a, b;
    int ok_a, ok_b;

    if (out == NULL)
    {
        return -1;
    }
    memset(out, 0, sizeof(*out));
    out->state = RH_KS_EMPTY;

    ok_a = parse_slot(RH_KS_SLOT0, &a) == 0;
    ok_b = parse_slot(RH_KS_SLOT1, &b) == 0;
    if (!ok_a && !ok_b)
    {
        return 0;
    }
    if (ok_a && !ok_b)
    {
        *out = a;
        return 0;
    }
    if (!ok_a && ok_b)
    {
        *out = b;
        return 0;
    }
    /* Prefer higher epoch; tie → prefer COMMITTED */
    if (b.epoch > a.epoch || (b.epoch == a.epoch && b.state == RH_KS_COMMITTED && a.state != RH_KS_COMMITTED))
    {
        *out = b;
    }
    else
    {
        *out = a;
    }
    return 0;
}

static uint32_t inactive_slot(const rh_ks_record_t *cur, int have)
{
    if (!have)
    {
        return RH_KS_SLOT0;
    }
    /* If current lives in slot0, write slot1 and vice versa — detect by re-parse */
    rh_ks_record_t t;
    if (parse_slot(RH_KS_SLOT0, &t) == 0 && t.epoch == cur->epoch && t.state == cur->state)
    {
        return RH_KS_SLOT1;
    }
    return RH_KS_SLOT0;
}

int rh_keystore_write_staged(const rh_ks_record_t *rec)
{
    rh_ks_record_t cur;
    uint8_t page[128];
    uint32_t slot;
    uint32_t crc;
    uint16_t layout = RH_KS_LAYOUT_VER;
    uint32_t magic = RH_KS_MAGIC;
    int have;
    uint32_t epoch;

    if (rec == NULL || rec->blob_len == 0u || rec->blob_len > RH_KS_BLOB_MAX)
    {
        return -1;
    }
    if (flash_arbiter_acquire(FLASH_OWNER_JOURNAL, 5000) != 0)
    {
        return -1;
    }

    have = (rh_keystore_load(&cur) == 0 && cur.state != RH_KS_EMPTY);
    epoch = have ? (cur.epoch + 1u) : 1u;
    slot = inactive_slot(have ? &cur : NULL, have);

    /* Never erase the only committed/staged blob slot until the other is written.
     * inactive_slot always picks the other when have==1. */
    if (sector_erase(slot) != 0)
    {
        flash_arbiter_release(FLASH_OWNER_JOURNAL);
        return -1;
    }

    memset(page, 0xFF, sizeof(page));
    memcpy(page + 0, &magic, 4);
    memcpy(page + 4, &layout, 2);
    memcpy(page + 6, &rec->key_id, 2);
    {
        uint16_t kv = RH_KEY_VERSION_V2;
        memcpy(page + 8, &kv, 2);
    }
    memcpy(page + 10, &rec->blob_len, 2);
    memcpy(page + 12, &epoch, 4);
    memcpy(page + 16, &rec->quanta_snap, 8);
    memcpy(page + 24, &rec->seq_snap, 8);
    memcpy(page + RH_KS_BLOB_OFF, rec->blob, rec->blob_len);
    {
        uint8_t tmp[28 + RH_KS_BLOB_MAX];
        memcpy(tmp, page, 28);
        memcpy(tmp + 28, page + RH_KS_BLOB_OFF, rec->blob_len);
        crc = rh_keystore_crc32(tmp, 28u + rec->blob_len);
    }
    memcpy(page + 28, &crc, 4);
    memcpy(page + RH_KS_STAGE_OFF, k_stage_mark, 16);
    /* commit marker remains 0xFF */

    for (uint32_t off = 0; off < 128; off += 16)
    {
        if (phrase_program(slot + off, page + off) != 0)
        {
            flash_arbiter_release(FLASH_OWNER_JOURNAL);
            return -1;
        }
    }

    {
        rh_ks_record_t verify;
        if (parse_slot(slot, &verify) != 0 || verify.state != RH_KS_BLOB_STAGED ||
            verify.blob_len != rec->blob_len || memcmp(verify.blob, rec->blob, rec->blob_len) != 0)
        {
            flash_arbiter_release(FLASH_OWNER_JOURNAL);
            PRINTF("rhks: staged verify fail\r\n");
            return -1;
        }
    }

    flash_arbiter_release(FLASH_OWNER_JOURNAL);
    PRINTF("rhks: staged epoch=%lu id=%u len=%u\r\n", (unsigned long)epoch, (unsigned)rec->key_id,
           (unsigned)rec->blob_len);
    return 0;
}

int rh_keystore_commit_version(void)
{
    rh_ks_record_t cur;
    uint32_t slot = 0;
    rh_ks_record_t t0, t1;
    int ok0, ok1;

    if (flash_arbiter_acquire(FLASH_OWNER_JOURNAL, 5000) != 0)
    {
        return -1;
    }
    if (rh_keystore_load(&cur) != 0 || cur.state == RH_KS_EMPTY)
    {
        flash_arbiter_release(FLASH_OWNER_JOURNAL);
        return -1;
    }
    if (cur.state == RH_KS_COMMITTED)
    {
        flash_arbiter_release(FLASH_OWNER_JOURNAL);
        return 0;
    }

    ok0 = parse_slot(RH_KS_SLOT0, &t0) == 0;
    ok1 = parse_slot(RH_KS_SLOT1, &t1) == 0;
    if (ok0 && t0.epoch == cur.epoch && t0.state == RH_KS_BLOB_STAGED)
    {
        slot = RH_KS_SLOT0;
    }
    else if (ok1 && t1.epoch == cur.epoch && t1.state == RH_KS_BLOB_STAGED)
    {
        slot = RH_KS_SLOT1;
    }
    else
    {
        flash_arbiter_release(FLASH_OWNER_JOURNAL);
        return -1;
    }

    if (phrase_program(slot + RH_KS_COMMIT_OFF, k_commit_mark) != 0)
    {
        flash_arbiter_release(FLASH_OWNER_JOURNAL);
        return -1;
    }
    {
        rh_ks_record_t v;
        if (parse_slot(slot, &v) != 0 || v.state != RH_KS_COMMITTED)
        {
            flash_arbiter_release(FLASH_OWNER_JOURNAL);
            return -1;
        }
    }
    flash_arbiter_release(FLASH_OWNER_JOURNAL);
    PRINTF("rhks: COMMITTED key_ver=2 id=%u\r\n", (unsigned)cur.key_id);
    return 0;
}

#else /* !APP_FLASH_LAYOUT_512K */

uint32_t rh_keystore_crc32(const uint8_t *data, size_t len)
{
    (void)data;
    (void)len;
    return 0;
}
int rh_keystore_load(rh_ks_record_t *out)
{
    if (out)
    {
        memset(out, 0, sizeof(*out));
    }
    return -1;
}
int rh_keystore_write_staged(const rh_ks_record_t *rec)
{
    (void)rec;
    return -1;
}
int rh_keystore_commit_version(void)
{
    return -1;
}

#endif
