#include "app.h"
#include "app_config.h"
#include "board.h"
#include "diagnostics.h"
#include "hello_service.h"
#include "led_task.h"
#include "update_service.h"

#include "fsl_debug_console.h"
#include "mflash_drv.h"

#include "lwip/tcpip.h"
#include "lwip/sys.h"

#include "FreeRTOS.h"
#include "task.h"

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

    led_task_start();

    if (initNetwork() != 0)
    {
        PRINTF("Network init failed\r\n");
        vTaskDelete(NULL);
        return;
    }

    hello_service_start();
    update_service_start();

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
