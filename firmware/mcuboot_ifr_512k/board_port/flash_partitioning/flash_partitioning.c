/*
 * Copyright 2022 NXP
 * Copyright 2026 — fa_size = APP_SLOT_SIZE (512 KiB), not bank stride
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#include "flash_partitioning.h"
#include "flash_map.h"
#include "mcuboot_config.h"
#include "sysflash/sysflash.h"

const char *boot_image_names[MCUBOOT_IMAGE_NUMBER] = {"APP"};

struct flash_area boot_flash_map[MCUBOOT_IMAGE_SLOT_NUMBER] = {
    {.fa_id        = 0,
     .fa_device_id = FLASH_DEVICE_ID,
     .fa_off       = BOOT_FLASH_ACT_APP - BOOT_FLASH_BASE,
     .fa_size      = APP_SLOT_SIZE,
     .fa_name      = "APP_PRIMARY"},

    {.fa_id        = 1,
     .fa_device_id = FLASH_DEVICE_ID,
     .fa_off       = BOOT_FLASH_CAND_APP - BOOT_FLASH_BASE,
     .fa_size      = APP_SLOT_SIZE,
     .fa_name      = "APP_SECONDARY"}};

#ifdef CONFIG_BOOT_MODE_ENCRYPTED_XIP_OVERWRITE
struct flash_area boot_flash_meta_map[1] = {
    {.fa_id        = 0,
     .fa_device_id = FLASH_DEVICE_ID,
     .fa_off       = BOOT_FLASH_SLOT0_ENC_CFG_ADDRESS - BOOT_FLASH_BASE,
     .fa_size      = MFLASH_SECTOR_SIZE,
     .fa_name      = "METADATA"}};
#endif
