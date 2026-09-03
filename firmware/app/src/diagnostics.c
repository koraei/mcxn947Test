/*
 * Product diagnostics — UUID via NXP SILICONID (MCXN UUID @ 0x01100000).
 */
#include "diagnostics.h"
#include "app_config.h"

#include <stdio.h>
#include <string.h>

#include "fsl_debug_console.h"
#include "fsl_silicon_id.h"

#include "FreeRTOS.h"
#include "task.h"

volatile uint32_t g_hello_accept_count;
volatile uint32_t g_hello_error_count;
volatile uint32_t g_update_accept_count;
volatile uint32_t g_update_success_count;
volatile uint32_t g_update_failure_count;
volatile uint32_t g_sb3_failure_count;
volatile uint32_t g_link_down_count;

static char s_uuid_hex[33];
static uint8_t s_uuid_bytes[16];
static TickType_t s_app_start_tick;

void diagnostics_init(void)
{
    uint8_t id[SILICONID_MAX_LENGTH] = {0};
    uint32_t len                     = sizeof(id);

    if (SILICONID_GetID(id, &len) != kStatus_Success)
    {
        PRINTF("WARN: SILICONID_GetID failed\r\n");
        for (int i = 0; i < 16; i++)
        {
            id[i] = 0;
        }
        len = 16;
    }

    memset(s_uuid_bytes, 0, sizeof(s_uuid_bytes));
    for (uint32_t i = 0; i < len && i < 16U; i++)
    {
        s_uuid_bytes[i] = id[i];
        (void)sprintf(&s_uuid_hex[i * 2], "%02X", id[i]);
    }
    s_uuid_hex[32] = '\0';

    PRINTF("UUID=%s\r\n", s_uuid_hex);
}

void diagnostics_mark_app_start(void)
{
    s_app_start_tick = xTaskGetTickCount();
}

const char *diagnostics_uuid_hex(void)
{
    return s_uuid_hex;
}

const uint8_t *diagnostics_uuid_bytes(void)
{
    return s_uuid_bytes;
}

uint32_t diagnostics_uptime_s(void)
{
    TickType_t now = xTaskGetTickCount();
    return (uint32_t)((now - s_app_start_tick) / configTICK_RATE_HZ);
}

uint32_t diagnostics_update_window_remaining_s(void)
{
    uint32_t up = diagnostics_uptime_s();
    if (up >= UPDATE_WINDOW_S)
    {
        return 0;
    }
    return UPDATE_WINDOW_S - up;
}
