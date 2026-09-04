/*
 * Address-range guards: OTA must stay in candidate slot; journal in runhours pools.
 */
#ifndef FLASH_RANGE_GUARD_H_
#define FLASH_RANGE_GUARD_H_

#include "memory_layout.h"

static inline int flash_guard_ota_range_ok(uint32_t addr, uint32_t len)
{
    return ml_addr_in_candidate_slot(addr, len);
}

static inline int flash_guard_runhours_range_ok(uint32_t addr, uint32_t len)
{
    return ml_addr_in_runhours(addr, len);
}

static inline int flash_guard_platform_reserve_ok(uint32_t addr, uint32_t len)
{
#if defined(APP_FLASH_LAYOUT_512K)
    if (len == 0u || (addr + len) < addr)
    {
        return 0;
    }
    const int in_a = (addr >= ML_PLATFORM_RESERVE_A) &&
                     ((addr + len) <= (ML_PLATFORM_RESERVE_A + ML_PLATFORM_RESERVE_A_SZ));
    const int in_b = (addr >= ML_PLATFORM_RESERVE_B) &&
                     ((addr + len) <= (ML_PLATFORM_RESERVE_B + ML_PLATFORM_RESERVE_B_SZ));
    return in_a || in_b;
#else
    (void)addr;
    (void)len;
    return 0;
#endif
}

static inline int flash_guard_not_security_region(uint32_t addr, uint32_t len)
{
    /* IFR / MCUboot and out-of-main-flash */
    if (addr >= ML_IFR_MCUBOOT_BASE && addr < (ML_IFR_MCUBOOT_BASE + ML_IFR_MCUBOOT_SIZE))
    {
        return 0;
    }
    if ((addr + len) < addr)
    {
        return 0;
    }
    return 1;
}

#endif /* FLASH_RANGE_GUARD_H_ */
