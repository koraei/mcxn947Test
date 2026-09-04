/*
 * Running-hours journal on-wire / on-flash format (plan §§7.3–7.5).
 * Host model: tools/runhours_host_model.py must stay in sync.
 */
#ifndef RUNHOURS_FORMAT_H_
#define RUNHOURS_FORMAT_H_

#include <stdint.h>
#include "memory_layout.h"

#define RH_SECTOR_SIZE           (8192u)
#define RH_PHRASE_SIZE           (16u)
#define RH_HEADER_SIZE           (64u)
#define RH_RECORD_SIZE           (64u)
#define RH_SLOTS_PER_SECTOR      ((RH_SECTOR_SIZE - RH_HEADER_SIZE) / RH_RECORD_SIZE) /* 127 */
#define RH_SECTOR_COUNT          (16u)
#define RH_POOL_A_SECTORS        (8u)
#define RH_POOL_B_SECTORS        (8u)

#define RH_MAGIC_HDR             (0x31534852u) /* 'RHS1' */
#define RH_MAGIC_REC             (0x31524852u) /* 'RHR1' */
#define RH_COMMIT_MAGIC          (0x54494D4D4F430001ull)
#define RH_FORMAT_VER            (1u)
#define RH_RECORD_TYPE           (1u)
#define RH_QUANTUM_SECONDS       (600u)

#if defined(APP_FLASH_LAYOUT_512K)
_Static_assert(ML_RUNHOURS_POOL_A_SZ == (RH_POOL_A_SECTORS * RH_SECTOR_SIZE), "pool A");
_Static_assert(ML_RUNHOURS_POOL_B_SZ == (RH_POOL_B_SECTORS * RH_SECTOR_SIZE), "pool B");
_Static_assert(ML_RUNHOURS_TOTAL_SZ == (RH_SECTOR_COUNT * RH_SECTOR_SIZE), "128KiB");
_Static_assert(APP_SLOT_SIZE == 0x00080000u, "512KiB slots");
_Static_assert(APP_SLOT_SIZE + ML_PLATFORM_RESERVE_A_SZ + ML_RUNHOURS_POOL_A_SZ + ML_EVENT_LOG_POOL_A_SZ ==
                   0x00100000u,
               "bank0 map");
#endif

#endif /* RUNHOURS_FORMAT_H_ */
