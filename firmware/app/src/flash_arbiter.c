#include "flash_arbiter.h"

#include "FreeRTOS.h"
#include "semphr.h"

static SemaphoreHandle_t s_mtx;
static flash_owner_t s_owner = FLASH_OWNER_NONE;
static uint32_t s_journal_deferred;

void flash_arbiter_init(void)
{
    if (s_mtx == NULL)
    {
        s_mtx = xSemaphoreCreateMutex();
    }
    s_owner = FLASH_OWNER_NONE;
}

int flash_arbiter_acquire(flash_owner_t owner, uint32_t timeout_ms)
{
    TickType_t ticks = (timeout_ms == UINT32_MAX) ? portMAX_DELAY : pdMS_TO_TICKS(timeout_ms);

    if (s_mtx == NULL)
    {
        flash_arbiter_init();
    }
    if (xSemaphoreTake(s_mtx, ticks) != pdTRUE)
    {
        return -1;
    }
    s_owner = owner;
    return 0;
}

void flash_arbiter_release(flash_owner_t owner)
{
    if (s_mtx == NULL)
    {
        return;
    }
    if (s_owner == owner || owner == FLASH_OWNER_NONE)
    {
        s_owner = FLASH_OWNER_NONE;
        (void)xSemaphoreGive(s_mtx);
    }
}

flash_owner_t flash_arbiter_owner(void)
{
    return s_owner;
}

uint32_t flash_arbiter_journal_deferred_count(void)
{
    return s_journal_deferred;
}

void flash_arbiter_note_journal_deferred(void)
{
    s_journal_deferred++;
}
