/*
 * Copyright (c) 2013 - 2015, Freescale Semiconductor, Inc.
 * Copyright 2016-2021 NXP
 * Copyright 2026 — 512 KiB A/B remap (LIM=15); from FRDM-MCXN947 mcuboot_opensource
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#include "fsl_device_registers.h"
#include "fsl_debug_console.h"
#include "pin_mux.h"
#include "clock_config.h"
#include "board.h"
#include "boot.h"

/*******************************************************************************
 * Definitions
 ******************************************************************************/
#define BOARD_SERIAL_RECOVERY_GPIO_PORT  BOARD_SW2_GPIO
#define BOARD_SERIAL_RECOVERY_GPIO_PIN   BOARD_SW2_GPIO_PIN

/* NPX remap window: (LIM+1) * 32 KiB. 15 → 512 KiB (was 31 → 1 MiB). */
#define MCUBOOT_NPX_REMAP_LIM  (15u)

/*******************************************************************************
 * Code
 ******************************************************************************/

int main(void)
{
    BOARD_InitBootPins();
    BOARD_InitBootClocks();
    CLOCK_EnableClock(kCLOCK_Flexspi);
    BOARD_InitDebugConsole();

    CLOCK_EnableClock(kCLOCK_Gpio0);
    CLOCK_EnableClock(kCLOCK_Gpio1);

    SYSCON->NVM_CTRL |= SYSCON_NVM_CTRL_DIS_MBECC_ERR_INST_MASK | SYSCON_NVM_CTRL_DIS_MBECC_ERR_DATA_MASK;
    SYSCON->NVM_CTRL |= SYSCON_NVM_CTRL_DIS_FLASH_SPEC_MASK | SYSCON_NVM_CTRL_DIS_DATA_SPEC_MASK;
    SYSCON->LPCAC_CTRL |= SYSCON_LPCAC_CTRL_DIS_LPCAC_MASK;

    PRINTF("hello sbl.\n");
    PRINTF("MCUboot 512K remap LIM=%u\n", (unsigned)MCUBOOT_NPX_REMAP_LIM);

    (void)sbl_boot_main();

    return 0;
}

void SBL_DisablePeripherals(void)
{
}

void SBL_EnableRemap(uint32_t start_addr, uint32_t end_addr, uint32_t off)
{
    (void)start_addr;
    (void)end_addr;
    (void)off;

    /* Remapping size: 512 KiB = (15+1)*32 KiB */
    NPX0->REMAP = (MCUBOOT_NPX_REMAP_LIM << NPX_REMAP_LIM_SHIFT) | 0x5A5A;
    NPX0->REMAP = (MCUBOOT_NPX_REMAP_LIM << NPX_REMAP_LIMDP_SHIFT) | 0xA5A5;
}

void SBL_DisableRemap(void)
{
    NPX0->REMAP = 0x5A5A;
    NPX0->REMAP = 0xA5A5;
}

int SBL_SerialRecovery_gpio_check(void)
{
    if (GPIO_PinRead(BOARD_SERIAL_RECOVERY_GPIO_PORT, BOARD_SERIAL_RECOVERY_GPIO_PIN) == 0U)
    {
        return 1;
    }
    return 0;
}
