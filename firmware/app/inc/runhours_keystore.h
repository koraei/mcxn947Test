/*
 * Run-hours keystore: device-bound RFC3394 blob in platform reserve.
 * Dual 8 KiB slots; STAGED→COMMITTED is phrase-only (no erase) for power-fail safety.
 */
#ifndef RUNHOURS_KEYSTORE_H_
#define RUNHOURS_KEYSTORE_H_

#include <stddef.h>
#include <stdint.h>

#define RH_KEY_VERSION_V1           (1u)
#define RH_KEY_VERSION_V2           (2u)
#define RH_KS_BLOB_MAX              (64u)
#define RH_KS_MAGIC                 (0x324B4852u) /* 'RHK2' */

typedef enum {
    RH_KS_EMPTY       = 0,
    RH_KS_BLOB_STAGED = 1,
    RH_KS_COMMITTED   = 2
} rh_ks_state_t;

typedef struct {
    rh_ks_state_t state;
    uint16_t      key_version; /* RH_KEY_VERSION_V2 when committed */
    uint16_t      key_id;
    uint16_t      blob_len;
    uint32_t      epoch;
    uint64_t      quanta_snap;
    uint64_t      seq_snap;
    uint8_t       blob[RH_KS_BLOB_MAX];
} rh_ks_record_t;

/* Load best valid copy (highest epoch, prefer COMMITTED). */
int rh_keystore_load(rh_ks_record_t *out);

/*
 * Write STAGED blob to the inactive slot (erase that slot only).
 * Does not erase a slot that holds the sole valid blob.
 */
int rh_keystore_write_staged(const rh_ks_record_t *rec);

/* Phrase-program commit marker on the active staged copy (no sector erase). */
int rh_keystore_commit_version(void);

uint32_t rh_keystore_crc32(const uint8_t *data, size_t len);

#endif /* RUNHOURS_KEYSTORE_H_ */
