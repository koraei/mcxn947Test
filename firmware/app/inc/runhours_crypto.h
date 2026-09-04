#ifndef RUNHOURS_CRYPTO_H_
#define RUNHOURS_CRYPTO_H_

#include <stddef.h>
#include <stdint.h>

#include "runhours_format.h"

int rh_crypto_init(const uint8_t *device_uuid16);
int rh_crypto_init_v1_only(const uint8_t *device_uuid16);
int rh_crypto_activate_staged_v2(void);
int rh_crypto_fallback_v1(const uint8_t *device_uuid16);
void rh_crypto_zeroize(void);

uint16_t rh_crypto_key_version(void);
uint16_t rh_crypto_key_id(void);
uint8_t rh_crypto_ks_state(void);
int rh_crypto_is_v2(void);

/*
 * Value-preserving migration. append_same_quanta must write one journal record
 * under the already-activated v2 key with the preserved quanta (seq advances).
 */
int rh_crypto_migrate_to_v2(uint64_t quanta_snap, uint64_t seq_snap,
                            int (*append_same_quanta)(uint64_t quanta, void *ctx), void *ctx);
int rh_crypto_try_commit_if_ready(void);

void rh_nonce_build(uint8_t out12[12], uint64_t sector_gen, uint32_t slot);
void rh_aad_build(uint8_t *out, size_t *out_len, uint64_t seq, uint64_t sector_gen, uint16_t sector_id,
                  uint16_t slot);

int rh_aes_gcm_encrypt(const uint8_t nonce[12], const uint8_t *aad, size_t aad_len, const uint8_t plain[16],
                       uint8_t ct[16], uint8_t tag[16]);
int rh_aes_gcm_decrypt(const uint8_t nonce[12], const uint8_t *aad, size_t aad_len, const uint8_t ct[16],
                       const uint8_t tag[16], uint8_t plain[16]);

uint32_t rh_crc32(const uint8_t *data, size_t len);

#endif /* RUNHOURS_CRYPTO_H_ */
