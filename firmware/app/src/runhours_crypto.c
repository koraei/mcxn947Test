/*
 * K_RH: device-bound AES-256 key via HMAC-SHA256(domain || SILICONID UUID).
 * Not CUST_MK_SK / imgtool / SB3 keys. No plaintext key in Git.
 * AES-GCM via NXP-backed mbedTLS (ELS/PSA path as configured).
 */
#include "runhours_crypto.h"

#include "diagnostics.h"

#include "mbedtls/gcm.h"
#include "mbedtls/md.h"

#include <string.h>

static uint8_t s_key[32];
static int s_ready;

static const char k_domain[] = "MCXN947-K_RH-v1";

int rh_crypto_init(const uint8_t *device_uuid16)
{
    const mbedtls_md_info_t *md;
    int rc;

    memset(s_key, 0, sizeof(s_key));
    s_ready = 0;

    if (device_uuid16 == NULL)
    {
        return -1;
    }

    md = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
    if (md == NULL)
    {
        return -1;
    }

    /* HMAC-SHA256(key=domain, msg=uuid) → 32-byte K_RH */
    rc = mbedtls_md_hmac(md, (const unsigned char *)k_domain, sizeof(k_domain) - 1u, device_uuid16, 16u, s_key);
    if (rc != 0)
    {
        memset(s_key, 0, sizeof(s_key));
        return -1;
    }
    s_ready = 1;
    return 0;
}

void rh_crypto_zeroize(void)
{
    memset(s_key, 0, sizeof(s_key));
    s_ready = 0;
}

void rh_nonce_build(uint8_t out12[12], uint64_t sector_gen, uint32_t slot)
{
    /* be64(generation) || be32(slot) — plan §7.3 */
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
    /* Match tools/runhours_host_model.py aad_for: <BHIQQHH */
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
    mbedtls_gcm_context ctx;
    int rc;

    if (!s_ready)
    {
        return -1;
    }
    mbedtls_gcm_init(&ctx);
    rc = mbedtls_gcm_setkey(&ctx, MBEDTLS_CIPHER_ID_AES, s_key, 256);
    if (rc == 0)
    {
        rc = mbedtls_gcm_crypt_and_tag(&ctx, MBEDTLS_GCM_ENCRYPT, 16, nonce, 12, aad, aad_len, plain, ct, 16, tag);
    }
    mbedtls_gcm_free(&ctx);
    return rc;
}

int rh_aes_gcm_decrypt(const uint8_t nonce[12], const uint8_t *aad, size_t aad_len, const uint8_t ct[16],
                       const uint8_t tag[16], uint8_t plain[16])
{
    mbedtls_gcm_context ctx;
    int rc;

    if (!s_ready)
    {
        return -1;
    }
    mbedtls_gcm_init(&ctx);
    rc = mbedtls_gcm_setkey(&ctx, MBEDTLS_CIPHER_ID_AES, s_key, 256);
    if (rc == 0)
    {
        rc = mbedtls_gcm_auth_decrypt(&ctx, 16, nonce, 12, aad, aad_len, tag, 16, ct, plain);
    }
    mbedtls_gcm_free(&ctx);
    return rc;
}

uint32_t rh_crc32(const uint8_t *data, size_t len)
{
    /* zlib-compatible CRC-32 */
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
