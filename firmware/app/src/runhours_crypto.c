/*
 * Run-hours journal key:
 *   v1 (legacy): HMAC-SHA256(domain, SILICONID UUID) + mbedTLS AES-GCM (plaintext in RAM)
 *   v2: PSA/ELS opaque AES-256 at location 0xc00401 (RFC3394), blob in platform reserve
 *
 * Never logs or dumps key material.
 */
#include "runhours_crypto.h"
#include "runhours_keystore.h"

#include "diagnostics.h"

#include "mbedtls/gcm.h"
#include "mbedtls/md.h"
#include "psa/crypto.h"
#include "mcux_psa_defines.h"
#include "mcuxClPsaDriver_Oracle_Interface_key_locations.h"

/* Capture RFC3394 key_buffer after generate (psa_export_key unsupported for ELS COPRO). */
#include "psa_crypto_slot_management.h"

#include "fsl_debug_console.h"

#include <string.h>

#ifndef PSA_KEY_LOCATION_S50_RFC3394_STORAGE
#define PSA_KEY_LOCATION_S50_RFC3394_STORAGE ((psa_key_location_t)0xc00401u)
#endif

typedef enum {
    RH_CRYPTO_NONE = 0,
    RH_CRYPTO_V1,
    RH_CRYPTO_V2
} rh_crypto_mode_t;

static rh_crypto_mode_t s_mode;
static uint8_t s_v1_key[32];
static int s_v1_ready;
static psa_key_id_t s_v2_key_id;
static int s_v2_ready;
static uint16_t s_key_version = RH_KEY_VERSION_V1;
static uint16_t s_key_id;
static uint8_t s_ks_state;

static const char k_domain[] = "MCXN947-K_RH-v1";

static psa_key_lifetime_t rh_v2_lifetime(void)
{
    return PSA_KEY_LIFETIME_FROM_PERSISTENCE_AND_LOCATION(PSA_KEY_PERSISTENCE_VOLATILE,
                                                         PSA_KEY_LOCATION_S50_RFC3394_STORAGE);
}

static void v1_zeroize(void)
{
    memset(s_v1_key, 0, sizeof(s_v1_key));
    s_v1_ready = 0;
}

static void v2_destroy(void)
{
    if (s_v2_ready && s_v2_key_id != 0)
    {
        (void)psa_destroy_key(s_v2_key_id);
    }
    s_v2_key_id = 0;
    s_v2_ready = 0;
}

static int v1_derive(const uint8_t *device_uuid16)
{
    const mbedtls_md_info_t *md;
    int rc;

    v1_zeroize();
    if (device_uuid16 == NULL)
    {
        return -1;
    }
    md = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
    if (md == NULL)
    {
        return -1;
    }
    rc = mbedtls_md_hmac(md, (const unsigned char *)k_domain, sizeof(k_domain) - 1u, device_uuid16, 16u,
                         s_v1_key);
    if (rc != 0)
    {
        v1_zeroize();
        return -1;
    }
    s_v1_ready = 1;
    s_mode = RH_CRYPTO_V1;
    s_key_version = RH_KEY_VERSION_V1;
    return 0;
}

static int v2_import_blob(const uint8_t *blob, size_t blob_len)
{
    psa_key_attributes_t attr = PSA_KEY_ATTRIBUTES_INIT;
    psa_status_t st;

    v2_destroy();
    psa_set_key_usage_flags(&attr, PSA_KEY_USAGE_ENCRYPT | PSA_KEY_USAGE_DECRYPT);
    psa_set_key_algorithm(&attr, PSA_ALG_GCM);
    psa_set_key_type(&attr, PSA_KEY_TYPE_AES);
    psa_set_key_bits(&attr, 256);
    psa_set_key_lifetime(&attr, rh_v2_lifetime());

    st = psa_import_key(&attr, blob, blob_len, &s_v2_key_id);
    psa_reset_key_attributes(&attr);
    if (st != PSA_SUCCESS)
    {
        PRINTF("rh: psa_import_key %d\r\n", (int)st);
        s_v2_key_id = 0;
        return -1;
    }
    s_v2_ready = 1;
    s_mode = RH_CRYPTO_V2;
    s_key_version = RH_KEY_VERSION_V2;
    return 0;
}

static int v2_gcm_roundtrip_ok(void)
{
    uint8_t nonce[12];
    uint8_t aad[4] = {0x52, 0x48, 0x76, 0x32};
    uint8_t plain[16] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15};
    uint8_t ct[16], tag[16], out[16];

    memset(nonce, 0xA5, sizeof(nonce));
    if (rh_aes_gcm_encrypt(nonce, aad, sizeof(aad), plain, ct, tag) != 0)
    {
        return -1;
    }
    if (rh_aes_gcm_decrypt(nonce, aad, sizeof(aad), ct, tag, out) != 0)
    {
        return -1;
    }
    if (memcmp(plain, out, 16) != 0)
    {
        return -1;
    }
    /* Wrong-key negative check (ephemeral volatile opaque). */
    {
        psa_key_attributes_t attr = PSA_KEY_ATTRIBUTES_INIT;
        psa_key_id_t wrong = 0;
        psa_status_t st;
        uint8_t junk[16];

        psa_set_key_usage_flags(&attr, PSA_KEY_USAGE_ENCRYPT | PSA_KEY_USAGE_DECRYPT);
        psa_set_key_algorithm(&attr, PSA_ALG_GCM);
        psa_set_key_type(&attr, PSA_KEY_TYPE_AES);
        psa_set_key_bits(&attr, 256);
        psa_set_key_lifetime(&attr, rh_v2_lifetime());
        st = psa_generate_key(&attr, &wrong);
        psa_reset_key_attributes(&attr);
        if (st == PSA_SUCCESS)
        {
            psa_key_id_t saved = s_v2_key_id;
            int saved_ready = s_v2_ready;
            s_v2_key_id = wrong;
            s_v2_ready = 1;
            st = (rh_aes_gcm_decrypt(nonce, aad, sizeof(aad), ct, tag, junk) == 0) ? PSA_ERROR_GENERIC_ERROR
                                                                                    : PSA_SUCCESS;
            (void)psa_destroy_key(wrong);
            s_v2_key_id = saved;
            s_v2_ready = saved_ready;
            if (st != PSA_SUCCESS)
            {
                PRINTF("rh: wrong-key check FAILED (accepted)\r\n");
                return -1;
            }
        }
    }
    return 0;
}

static int v2_generate_and_export(uint8_t *blob, size_t blob_cap, size_t *blob_len, uint16_t key_id)
{
    psa_key_attributes_t attr = PSA_KEY_ATTRIBUTES_INIT;
    psa_key_id_t kid = 0;
    psa_status_t st;
    psa_key_slot_t *slot = NULL;

    (void)key_id;
    /*
     * NXP StoreKey (RFC3394 location) writes the DIE_KEK-wrapped container into
     * the PSA key buffer at generate time. psa_export_key() returns
     * PSA_ERROR_NOT_SUPPORTED for ELS COPRO-resident keys (mcuxClPsaDriver), so
     * capture that buffer via the slot API instead — still no plaintext AES key.
     */
    psa_set_key_usage_flags(&attr, PSA_KEY_USAGE_ENCRYPT | PSA_KEY_USAGE_DECRYPT);
    psa_set_key_algorithm(&attr, PSA_ALG_GCM);
    psa_set_key_type(&attr, PSA_KEY_TYPE_AES);
    psa_set_key_bits(&attr, 256);
    psa_set_key_lifetime(&attr, rh_v2_lifetime());

    st = psa_generate_key(&attr, &kid);
    psa_reset_key_attributes(&attr);
    if (st != PSA_SUCCESS)
    {
        PRINTF("rh: psa_generate_key %d\r\n", (int)st);
        return -1;
    }

    st = psa_get_and_lock_key_slot(kid, &slot);
    if (st != PSA_SUCCESS || slot == NULL || slot->key.data == NULL || slot->key.bytes == 0u ||
        slot->key.bytes > blob_cap)
    {
        PRINTF("rh: rfc3394 slot capture %d len=%u\r\n", (int)st,
               (unsigned)(slot ? slot->key.bytes : 0u));
        (void)psa_destroy_key(kid);
        return -1;
    }
    memcpy(blob, slot->key.data, slot->key.bytes);
    *blob_len = slot->key.bytes;
    (void)psa_unregister_read_under_mutex(slot);

    (void)psa_destroy_key(kid);
    return 0;
}

int rh_crypto_init(const uint8_t *device_uuid16)
{
    rh_ks_record_t ks;

    rh_crypto_zeroize();
    if (psa_crypto_init() != PSA_SUCCESS)
    {
        /* Already initialized by mTLS is fine; retry once for ordering races. */
        if (psa_crypto_init() != PSA_SUCCESS)
        {
            PRINTF("rh: psa_crypto_init failed\r\n");
            return -1;
        }
    }

    if (rh_keystore_load(&ks) != 0)
    {
        ks.state = RH_KS_EMPTY;
    }
    s_ks_state = (uint8_t)ks.state;
    s_key_id = ks.key_id;

    if (ks.state == RH_KS_COMMITTED)
    {
        if (v2_import_blob(ks.blob, ks.blob_len) != 0)
        {
            return -1;
        }
        s_key_id = ks.key_id;
        s_ks_state = (uint8_t)RH_KS_COMMITTED;
        PRINTF("rh: crypto v2 committed id=%u\r\n", (unsigned)s_key_id);
        return 0;
    }

    if (ks.state == RH_KS_BLOB_STAGED)
    {
        /* Caller may probe journal with v2; we import and leave staged. */
        if (v2_import_blob(ks.blob, ks.blob_len) != 0)
        {
            /* Fall back to v1 below */
            v2_destroy();
        }
        else
        {
            s_key_id = ks.key_id;
            s_ks_state = (uint8_t)RH_KS_BLOB_STAGED;
            PRINTF("rh: crypto v2 staged id=%u (probe)\r\n", (unsigned)s_key_id);
            return 0;
        }
    }

    if (v1_derive(device_uuid16) != 0)
    {
        return -1;
    }
    s_ks_state = (uint8_t)ks.state;
    PRINTF("rh: crypto v1 legacy\r\n");
    return 0;
}

int rh_crypto_init_v1_only(const uint8_t *device_uuid16)
{
    rh_crypto_zeroize();
    return v1_derive(device_uuid16);
}

int rh_crypto_activate_staged_v2(void)
{
    rh_ks_record_t ks;
    if (rh_keystore_load(&ks) != 0 || ks.state < RH_KS_BLOB_STAGED)
    {
        return -1;
    }
    if (v2_import_blob(ks.blob, ks.blob_len) != 0)
    {
        return -1;
    }
    s_key_id = ks.key_id;
    s_ks_state = (uint8_t)ks.state;
    v1_zeroize();
    return 0;
}

int rh_crypto_fallback_v1(const uint8_t *device_uuid16)
{
    v2_destroy();
    return v1_derive(device_uuid16);
}

uint16_t rh_crypto_key_version(void)
{
    return s_key_version;
}

uint16_t rh_crypto_key_id(void)
{
    return s_key_id;
}

uint8_t rh_crypto_ks_state(void)
{
    return s_ks_state;
}

int rh_crypto_is_v2(void)
{
    return s_mode == RH_CRYPTO_V2 && s_v2_ready;
}

void rh_crypto_zeroize(void)
{
    v1_zeroize();
    v2_destroy();
    s_mode = RH_CRYPTO_NONE;
    s_key_version = RH_KEY_VERSION_V1;
    s_key_id = 0;
    s_ks_state = 0;
}

void rh_nonce_build(uint8_t out12[12], uint64_t sector_gen, uint32_t slot)
{
    out12[0]  = (uint8_t)(sector_gen >> 56);
    out12[1]  = (uint8_t)(sector_gen >> 48);
    out12[2]  = (uint8_t)(sector_gen >> 40);
    out12[3]  = (uint8_t)(sector_gen >> 32);
    out12[4]  = (uint8_t)(sector_gen >> 24);
    out12[5]  = (uint8_t)(sector_gen >> 16);
    out12[6]  = (uint8_t)(sector_gen >> 8);
    out12[7]  = (uint8_t)(sector_gen);
    out12[8]  = (uint8_t)(slot >> 24);
    out12[9]  = (uint8_t)(slot >> 16);
    out12[10] = (uint8_t)(slot >> 8);
    out12[11] = (uint8_t)(slot);
}

void rh_aad_build(uint8_t *out, size_t *out_len, uint64_t seq, uint64_t sector_gen, uint16_t sector_id,
                  uint16_t slot)
{
    size_t o = 0;
    out[o++] = (uint8_t)RH_FORMAT_VER;
    out[o++] = (uint8_t)(RH_RECORD_TYPE & 0xff);
    out[o++] = (uint8_t)((RH_RECORD_TYPE >> 8) & 0xff);
    out[o++] = 0;
    out[o++] = 0;
    out[o++] = 0;
    out[o++] = 0;
    memcpy(&out[o], &seq, 8);
    o += 8;
    memcpy(&out[o], &sector_gen, 8);
    o += 8;
    memcpy(&out[o], &sector_id, 2);
    o += 2;
    memcpy(&out[o], &slot, 2);
    o += 2;
    *out_len = o;
}

int rh_aes_gcm_encrypt(const uint8_t nonce[12], const uint8_t *aad, size_t aad_len, const uint8_t plain[16],
                       uint8_t ct[16], uint8_t tag[16])
{
    if (s_mode == RH_CRYPTO_V2 && s_v2_ready)
    {
        uint8_t out[32];
        size_t out_len = 0;
        psa_status_t st = psa_aead_encrypt(s_v2_key_id, PSA_ALG_GCM, nonce, 12, aad, aad_len, plain, 16, out,
                                           sizeof(out), &out_len);
        if (st != PSA_SUCCESS || out_len != 32u)
        {
            return -1;
        }
        memcpy(ct, out, 16);
        memcpy(tag, out + 16, 16);
        return 0;
    }
    if (s_mode == RH_CRYPTO_V1 && s_v1_ready)
    {
        mbedtls_gcm_context ctx;
        int rc;
        mbedtls_gcm_init(&ctx);
        rc = mbedtls_gcm_setkey(&ctx, MBEDTLS_CIPHER_ID_AES, s_v1_key, 256);
        if (rc == 0)
        {
            rc = mbedtls_gcm_crypt_and_tag(&ctx, MBEDTLS_GCM_ENCRYPT, 16, nonce, 12, aad, aad_len, plain, ct, 16,
                                           tag);
        }
        mbedtls_gcm_free(&ctx);
        return rc;
    }
    return -1;
}

int rh_aes_gcm_decrypt(const uint8_t nonce[12], const uint8_t *aad, size_t aad_len, const uint8_t ct[16],
                       const uint8_t tag[16], uint8_t plain[16])
{
    if (s_mode == RH_CRYPTO_V2 && s_v2_ready)
    {
        uint8_t in[32];
        size_t out_len = 0;
        psa_status_t st;
        memcpy(in, ct, 16);
        memcpy(in + 16, tag, 16);
        st = psa_aead_decrypt(s_v2_key_id, PSA_ALG_GCM, nonce, 12, aad, aad_len, in, 32, plain, 16, &out_len);
        return (st == PSA_SUCCESS && out_len == 16u) ? 0 : -1;
    }
    if (s_mode == RH_CRYPTO_V1 && s_v1_ready)
    {
        mbedtls_gcm_context ctx;
        int rc;
        mbedtls_gcm_init(&ctx);
        rc = mbedtls_gcm_setkey(&ctx, MBEDTLS_CIPHER_ID_AES, s_v1_key, 256);
        if (rc == 0)
        {
            rc = mbedtls_gcm_auth_decrypt(&ctx, 16, nonce, 12, aad, aad_len, tag, 16, ct, plain);
        }
        mbedtls_gcm_free(&ctx);
        return rc;
    }
    return -1;
}

int rh_crypto_migrate_to_v2(uint64_t quanta_snap, uint64_t seq_snap,
                            int (*append_same_quanta)(uint64_t quanta, void *ctx), void *ctx)
{
    rh_ks_record_t ks;
    rh_ks_record_t staged;
    uint8_t blob[RH_KS_BLOB_MAX];
    size_t blob_len = 0;
    uint16_t new_id = 1;

    if (append_same_quanta == NULL)
    {
        return -1;
    }
    if (rh_keystore_load(&ks) != 0)
    {
        ks.state = RH_KS_EMPTY;
    }
    if (ks.state == RH_KS_COMMITTED)
    {
        s_ks_state = (uint8_t)RH_KS_COMMITTED;
        return 0;
    }

    if (ks.state != RH_KS_BLOB_STAGED)
    {
        if (ks.key_id != 0)
        {
            new_id = (uint16_t)(ks.key_id + 1u);
        }
        memset(blob, 0, sizeof(blob));
        if (v2_generate_and_export(blob, sizeof(blob), &blob_len, new_id) != 0)
        {
            return -1;
        }
        memset(&staged, 0, sizeof(staged));
        staged.state = RH_KS_BLOB_STAGED;
        staged.key_id = new_id;
        staged.key_version = RH_KEY_VERSION_V2;
        staged.blob_len = (uint16_t)blob_len;
        staged.quanta_snap = quanta_snap;
        staged.seq_snap = seq_snap;
        memcpy(staged.blob, blob, blob_len);
        memset(blob, 0, sizeof(blob));
        if (rh_keystore_write_staged(&staged) != 0)
        {
            memset(staged.blob, 0, sizeof(staged.blob));
            return -1;
        }
        memset(staged.blob, 0, sizeof(staged.blob));
        if (rh_keystore_load(&ks) != 0 || ks.state != RH_KS_BLOB_STAGED)
        {
            return -1;
        }
    }

    /* Import staged blob (no EXPORT on runtime key). */
    if (v2_import_blob(ks.blob, ks.blob_len) != 0)
    {
        return -1;
    }
    v1_zeroize();
    s_key_id = ks.key_id;
    s_ks_state = (uint8_t)RH_KS_BLOB_STAGED;

    if (v2_gcm_roundtrip_ok() != 0)
    {
        PRINTF("rh: v2 GCM prove fail\r\n");
        return -1;
    }

    /* Value-preserving v2 journal record (same quanta). */
    {
        uint64_t q = ks.quanta_snap;
        (void)quanta_snap;
        (void)seq_snap;
        if (append_same_quanta(q, ctx) != 0)
        {
            PRINTF("rh: v2 journal append fail\r\n");
            return -1;
        }
    }

    if (rh_keystore_commit_version() != 0)
    {
        PRINTF("rh: keystore commit fail\r\n");
        return -1;
    }
    s_ks_state = (uint8_t)RH_KS_COMMITTED;
    s_key_version = RH_KEY_VERSION_V2;
    PRINTF("rh: migrated to v2 key_id=%u quanta_snap preserved\r\n", (unsigned)s_key_id);
    return 0;
}

int rh_crypto_try_commit_if_ready(void)
{
    rh_ks_record_t ks;
    if (rh_keystore_load(&ks) != 0)
    {
        return -1;
    }
    if (ks.state == RH_KS_COMMITTED)
    {
        s_ks_state = (uint8_t)RH_KS_COMMITTED;
        return 0;
    }
    if (ks.state == RH_KS_BLOB_STAGED && s_mode == RH_CRYPTO_V2)
    {
        if (rh_keystore_commit_version() != 0)
        {
            return -1;
        }
        s_ks_state = (uint8_t)RH_KS_COMMITTED;
        return 0;
    }
    return -1;
}

uint32_t rh_crc32(const uint8_t *data, size_t len)
{
    return rh_keystore_crc32(data, len);
}
