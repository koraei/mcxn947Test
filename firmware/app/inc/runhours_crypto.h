#ifndef RUNHOURS_CRYPTO_H_
#define RUNHOURS_CRYPTO_H_

#include <stddef.h>
#include <stdint.h>

#include "runhours_format.h"

int rh_crypto_init(const uint8_t *device_uuid16);
void rh_crypto_zeroize(void);

void rh_nonce_build(uint8_t out12[12], uint64_t sector_gen, uint32_t slot);
void rh_aad_build(uint8_t *out, size_t *out_len, uint64_t seq, uint64_t sector_gen, uint16_t sector_id,
                  uint16_t slot);

/* Encrypt 16-byte plaintext → ct[16] + tag[16]. */
int rh_aes_gcm_encrypt(const uint8_t nonce[12], const uint8_t *aad, size_t aad_len, const uint8_t plain[16],
                       uint8_t ct[16], uint8_t tag[16]);

/* Decrypt/authenticate; returns 0 on success. */
int rh_aes_gcm_decrypt(const uint8_t nonce[12], const uint8_t *aad, size_t aad_len, const uint8_t ct[16],
                       const uint8_t tag[16], uint8_t plain[16]);

uint32_t rh_crc32(const uint8_t *data, size_t len);

#endif /* RUNHOURS_CRYPTO_H_ */
