/*
 * Single source of truth for flash map (Rev B).
 * APP_FLASH_LAYOUT_512K selects 512 KiB slots + shared pools (build-only until CMPA).
 * Default: legacy 1 MiB slots matching current field remap.
 */
#ifndef MEMORY_LAYOUT_H_
#define MEMORY_LAYOUT_H_

#include <stdint.h>

#define ML_FLASH_BASE              (0x00000000u)
#define ML_FLASH_SIZE              (0x00200000u)

#define ML_IFR_MCUBOOT_BASE        (0x01008000u)
#define ML_IFR_MCUBOOT_SIZE        (0x00008000u)

#define BOOT_FLASH_ACT_APP         (0x00000000u)
#define BOOT_FLASH_CAND_APP        (0x00100000u)

#if defined(APP_FLASH_LAYOUT_512K)

#define APP_SLOT_SIZE              (0x00080000u) /* 512 KiB */

#define ML_PLATFORM_RESERVE_A      (0x00080000u)
#define ML_PLATFORM_RESERVE_A_SZ   (0x00020000u)
#define ML_RUNHOURS_POOL_A         (0x000A0000u)
#define ML_RUNHOURS_POOL_A_SZ      (0x00010000u)
#define ML_EVENT_LOG_POOL_A        (0x000B0000u)
#define ML_EVENT_LOG_POOL_A_SZ     (0x00050000u)

#define ML_PLATFORM_RESERVE_B      (0x00180000u)
#define ML_PLATFORM_RESERVE_B_SZ   (0x00020000u)
#define ML_RUNHOURS_POOL_B         (0x001A0000u)
#define ML_RUNHOURS_POOL_B_SZ      (0x00010000u)
#define ML_EVENT_LOG_POOL_B        (0x001B0000u)
#define ML_EVENT_LOG_POOL_B_SZ     (0x00050000u)

#define ML_RUNHOURS_TOTAL_SZ       (0x00020000u)
#define ML_PLATFORM_RESERVE_TOTAL  (0x00040000u)
#define ML_FLASH_REMAP_SIZE_FIELD  (15u)

#else

#define APP_SLOT_SIZE              (0x00100000u) /* 1 MiB legacy */

#endif

_Static_assert((BOOT_FLASH_CAND_APP - BOOT_FLASH_ACT_APP) == 0x00100000u, "slot bases");
_Static_assert(APP_SLOT_SIZE == 0x00080000u || APP_SLOT_SIZE == 0x00100000u, "APP_SLOT_SIZE");

#if defined(APP_FLASH_LAYOUT_512K)
_Static_assert(APP_SLOT_SIZE == 0x00080000u, "512K slots");
_Static_assert(ML_RUNHOURS_TOTAL_SZ == 0x00020000u, "128KiB journal");
_Static_assert(ML_PLATFORM_RESERVE_A >= (BOOT_FLASH_ACT_APP + APP_SLOT_SIZE), "shared after A");
_Static_assert(ML_PLATFORM_RESERVE_B >= (BOOT_FLASH_CAND_APP + APP_SLOT_SIZE), "shared after B");
#endif

static inline int ml_addr_in_candidate_slot(uint32_t addr, uint32_t len)
{
    const uint32_t lo = BOOT_FLASH_CAND_APP;
    const uint32_t hi = BOOT_FLASH_CAND_APP + APP_SLOT_SIZE;
    if (len == 0u || addr < lo || (addr + len) < addr)
    {
        return 0;
    }
    return (addr + len) <= hi;
}

static inline int ml_addr_in_runhours(uint32_t addr, uint32_t len)
{
#if defined(APP_FLASH_LAYOUT_512K)
    if (len == 0u || (addr + len) < addr)
    {
        return 0;
    }
    const int in_a =
        (addr >= ML_RUNHOURS_POOL_A) && ((addr + len) <= (ML_RUNHOURS_POOL_A + ML_RUNHOURS_POOL_A_SZ));
    const int in_b =
        (addr >= ML_RUNHOURS_POOL_B) && ((addr + len) <= (ML_RUNHOURS_POOL_B + ML_RUNHOURS_POOL_B_SZ));
    return in_a || in_b;
#else
    (void)addr;
    (void)len;
    return 0;
#endif
}

#endif /* MEMORY_LAYOUT_H_ */
