#include "app.h"
#include "app_config.h"
#include "board.h"
#include "diagnostics.h"
#include "hello_service.h"
#include "led_task.h"
#include "mtls_socket.h"
#include "qa_stream.h"
#include "update_service.h"
#include "runhours_journal.h"
#include "runhours_task.h"
#include "flash_arbiter.h"
#if defined(APP_RH_ENDURANCE_TEST) && (APP_RH_ENDURANCE_TEST)
#include "runhours_stress.h"
#endif

#include "fsl_common.h"
#include "fsl_debug_console.h"
#include "mflash_drv.h"

#include "lwip/tcpip.h"
#include "lwip/sys.h"
#include "mcuboot_app_support.h"

#include "FreeRTOS.h"
#include "task.h"

static void confirm_image_if_testing(void)
{
    uint32_t imgstate = 0;

    if (bl_get_image_state(0, &imgstate) != kStatus_Success)
    {
        return;
    }
    if (imgstate == kSwapType_Testing)
    {
        if (bl_update_image_state(0, kSwapType_Permanent) == kStatus_Success)
        {
            PRINTF("MCUboot image confirmed (was Testing)\r\n");
        }
        else
        {
            PRINTF("MCUboot confirm failed\r\n");
        }
    }
}

int initNetwork(void);

#ifndef MAIN_THREAD_STACK
#define MAIN_THREAD_STACK 2048
#endif

static void main_thread(void *arg)
{
    (void)arg;

    diagnostics_mark_app_start();
    diagnostics_init();

    PRINTF("App %s version=%s\r\n", APP_VARIANT, APP_VERSION_STRING);
    confirm_image_if_testing();

    led_task_start();

    if (initNetwork() != 0)
    {
        PRINTF("Network init failed\r\n");
        vTaskDelete(NULL);
        return;
    }

    if (mtls_global_init() != 0)
    {
        PRINTF("mTLS init failed\r\n");
        vTaskDelete(NULL);
        return;
    }

#if defined(APP_FLASH_LAYOUT_512K)
    {
        rh_status_t rhs = rh_journal_init();
        PRINTF("rh_journal_init: %d\r\n", (int)rhs);
        if (rhs == RH_OK)
        {
#if defined(APP_RH_ENDURANCE_TEST) && (APP_RH_ENDURANCE_TEST)
            rh_stress_task_start();
#else
            runhours_task_start();
#endif
        }
    }
#endif

    hello_service_start();
    update_service_start();
    qa_stream_service_start();

    vTaskDelete(NULL);
}

int main(void)
{
    BOARD_InitHardware();
    mflash_drv_init();

    PRINTF("\r\n=== %s ===\r\n", EXAMPLE_BANNER);

    if (sys_thread_new("main", main_thread, NULL, MAIN_THREAD_STACK, DEFAULT_THREAD_PRIO) == NULL)
    {
        LWIP_ASSERT("main thread", 0);
    }

    vTaskStartScheduler();
    for (;;)
    {
    }
}
