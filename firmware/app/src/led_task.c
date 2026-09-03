#include "led_task.h"
#include "app_config.h"

#include "board.h"
#include "fsl_debug_console.h"

#include "FreeRTOS.h"
#include "task.h"

#ifndef APP_LED_COLOR_GREEN
#define APP_LED_COLOR_GREEN 1
#endif
#ifndef APP_LED_COLOR_BLUE
#define APP_LED_COLOR_BLUE 2
#endif
#ifndef APP_LED_COLOR_RED
#define APP_LED_COLOR_RED 3
#endif

#if !defined(APP_LED_COLOR_ID)
#if defined(APP_VARIANT_IS_V3)
#define APP_LED_COLOR_ID APP_LED_COLOR_RED
#elif defined(APP_VARIANT_IS_V2)
#define APP_LED_COLOR_ID APP_LED_COLOR_BLUE
#else
#define APP_LED_COLOR_ID APP_LED_COLOR_GREEN
#endif
#endif

static void led_task(void *arg)
{
    (void)arg;

    /* First action: clear bootloader LED (red). */
    LED_RED_INIT(LOGIC_LED_OFF);
    LED_RED_OFF();
    LED_GREEN_INIT(LOGIC_LED_OFF);
    LED_BLUE_INIT(LOGIC_LED_OFF);
    LED_GREEN_OFF();
    LED_BLUE_OFF();

    PRINTF("LED task start variant=%s on=%u off=%u\r\n", APP_VARIANT, (unsigned)APP_LED_ON_MS,
           (unsigned)APP_LED_OFF_MS);

    for (;;)
    {
#if (APP_LED_COLOR_ID == APP_LED_COLOR_RED)
        /* Double-pulse heartbeat */
        LED_RED_ON();
        vTaskDelay(pdMS_TO_TICKS(APP_LED_ON_MS));
        LED_RED_OFF();
        vTaskDelay(pdMS_TO_TICKS(APP_LED_ON_MS));
        LED_RED_ON();
        vTaskDelay(pdMS_TO_TICKS(APP_LED_ON_MS));
        LED_RED_OFF();
        vTaskDelay(pdMS_TO_TICKS(APP_LED_OFF_MS));
#elif (APP_LED_COLOR_ID == APP_LED_COLOR_BLUE)
        LED_BLUE_ON();
        vTaskDelay(pdMS_TO_TICKS(APP_LED_ON_MS));
        LED_BLUE_OFF();
        vTaskDelay(pdMS_TO_TICKS(APP_LED_OFF_MS));
#else
        LED_GREEN_ON();
        vTaskDelay(pdMS_TO_TICKS(APP_LED_ON_MS));
        LED_GREEN_OFF();
        vTaskDelay(pdMS_TO_TICKS(APP_LED_OFF_MS));
#endif
    }
}

void led_task_start(void)
{
    if (xTaskCreate(led_task, "led", 512, NULL, tskIDLE_PRIORITY + 1, NULL) != pdPASS)
    {
        PRINTF("LED task create failed\r\n");
    }
}
