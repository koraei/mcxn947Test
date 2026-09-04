/*
 * Copyright 2022 NXP
 * Copyright 2026 — 512 KiB application slots for IFR MCUboot
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#ifndef _FLASH_PARTITIONING_H_
#define _FLASH_PARTITIONING_H_

#include "mcux_config.h"
#include "sblconfig.h"
#include "mflash_drv.h"

#define BOOT_FLASH_BASE     0x00000000

#if defined(CONFIG_BOOT_CUSTOM_DEVICE_SETUP)
#define BOOT_FLASH_ACT_APP                CONFIG_BOOT_FLASH_ACT_APP_ADDRESS
#define BOOT_FLASH_CAND_APP               CONFIG_BOOT_FLASH_CAND_APP_ADDRESS
#define BOOT_FLASH_SLOT0_ENC_CFG_ADDRESS  CONFIG_BOOT_FLASH_SLOT0_ENC_CFG_ADDRESS
#else
#ifndef CONFIG_MCXN_CUSTOM_CFG_MAIN_FLASH_ONLY
/*
 * IFR MCUboot + flash remap — 512 KiB A/B slots (shared pools above each slot).
 *
 * 0x0000_0000  Slot A / primary remap     512 KiB
 * 0x0008_0000  Shared (platform/journal…) 512 KiB (not remapped when LIM=15)
 * 0x0010_0000  Slot B / secondary remap   512 KiB
 * 0x0018_0000  Shared                     512 KiB
 * 0x0100_8000  MCUboot IFR                 32 KiB
 */
#define BOOT_FLASH_ACT_APP  0x00000000
#define BOOT_FLASH_CAND_APP 0x00100000
#define APP_SLOT_SIZE       0x00080000u /* 512 KiB — must match imgtool --slot-size */
#else
#define BOOT_FLASH_ACT_APP  0x00040000
#define BOOT_FLASH_CAND_APP 0x00120000
#define APP_SLOT_SIZE       (BOOT_FLASH_CAND_APP - BOOT_FLASH_ACT_APP)
#if defined(CONFIG_BOOT_MODE_ENCRYPTED_XIP_OVERWRITE)
#define BOOT_FLASH_SLOT0_ENC_CFG_ADDRESS (BOOT_FLASH_ACT_APP - 8192U)
#endif
#endif /* !CONFIG_MCXN_CUSTOM_CFG_MAIN_FLASH_ONLY */
#endif /* CONFIG_BOOT_CUSTOM_DEVICE_SETUP */

#ifndef APP_SLOT_SIZE
#define APP_SLOT_SIZE (BOOT_FLASH_CAND_APP - BOOT_FLASH_ACT_APP)
#endif

#if !defined(CONFIG_MCXN_CUSTOM_CFG_MAIN_FLASH_ONLY) && !defined(CONFIG_BOOT_CUSTOM_DEVICE_SETUP)
_Static_assert(APP_SLOT_SIZE == 0x00080000u, "IFR MCUboot 512KiB slots");
_Static_assert(BOOT_FLASH_CAND_APP == 0x00100000u, "slot B base");
_Static_assert(BOOT_FLASH_ACT_APP == 0x00000000u, "slot A base");
#endif

#endif /* _FLASH_PARTITIONING_H_ */
