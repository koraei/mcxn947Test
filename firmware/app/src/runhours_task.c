/*
 * Background cadence: one durable quantum every RH_QUANTUM_SECONDS (600 s).
 * Does not accelerate flash writes for testing — use Hello RHFORCE for qual.
 */
#include "runhours_task.h"
#include "runhours_journal.h"
#include "runhours_format.h"

#include "fsl_debug_console.h"

#include "FreeRTOS.h"
#include "task.h"

#if defined(APP_FLASH_LAYOUT_512K)

static void runhours_task(void *arg)
{
    TickType_t last = xTaskGetTickCount();
    (void)arg;

    for (;;)
    {
        vTaskDelayUntil(&last, pdMS_TO_TICKS(RH_QUANTUM_SECONDS * 1000u));
        {
            uint64_t q = 0;
            if (rh_journal_get_quanta(&q) != RH_OK)
            {
                continue;
            }
            rh_status_t st = rh_journal_append_quanta(q + 1ull);
            if (st == RH_ERR_BUSY)
            {
                PRINTF("rh: append deferred (OTA owns flash)\r\n");
                /* Retry soon without advancing wall cadence permanently — keep interval. */
            }
            else if (st != RH_OK)
            {
                PRINTF("rh: append failed %d\r\n", (int)st);
            }
        }
    }
}

void runhours_task_start(void)
{
    if (xTaskCreate(runhours_task, "runhours", 1024, NULL, tskIDLE_PRIORITY + 1, NULL) != pdPASS)
    {
        PRINTF("rh: task create failed\r\n");
    }
}

#else

void runhours_task_start(void)
{
}

#endif
