/*
 * Copyright 2022 NXP
 * All rights reserved.
 *
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#ifndef _FLASH_PARTITIONING_H_
#define _FLASH_PARTITIONING_H_

#include "mcux_config.h"
#include "sblconfig.h"
#include "mflash_drv.h"
#include "memory_layout.h"

#define BOOT_FLASH_BASE     0x00000000

#if defined(CONFIG_BOOT_CUSTOM_DEVICE_SETUP)
/* Layout setup from Kconfig */

#define BOOT_FLASH_ACT_APP                CONFIG_BOOT_FLASH_ACT_APP_ADDRESS
#define BOOT_FLASH_CAND_APP               CONFIG_BOOT_FLASH_CAND_APP_ADDRESS
#define BOOT_FLASH_SLOT0_ENC_CFG_ADDRESS  CONFIG_BOOT_FLASH_SLOT0_ENC_CFG_ADDRESS

#else
/*
 * Slot bases and APP_SLOT_SIZE come from memory_layout.h
 * (legacy 1 MiB or APP_FLASH_LAYOUT_512K).
 * Do NOT derive fa_size as (CAND - ACT); that is always 1 MiB bank stride.
 */
#if defined(CONFIG_MCXN_CUSTOM_CFG_MAIN_FLASH_ONLY)
/*
  Custom configuration - see readme file
  Bootloader located in main flash
*/
#undef BOOT_FLASH_ACT_APP
#undef BOOT_FLASH_CAND_APP
#define BOOT_FLASH_ACT_APP  0x00040000
#define BOOT_FLASH_CAND_APP 0x00120000

#if defined(CONFIG_BOOT_MODE_ENCRYPTED_XIP_OVERWRITE)
#define BOOT_FLASH_SLOT0_ENC_CFG_ADDRESS (BOOT_FLASH_ACT_APP - 8192U)
#endif

#endif /* CONFIG_MCXN_CUSTOM_CFG_MAIN_FLASH_ONLY */

#endif /* CONFIG_BOOT_CUSTOM_DEVICE_SETUP */
#endif /* _FLASH_PARTITIONING_H_ */
