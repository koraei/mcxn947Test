/*
 * QA-only 4 Hz durable journal stress writer (APP_RH_ENDURANCE_TEST).
 * Uses production rh_journal_append_quanta path only. Waits for host START.
 */
#include "runhours_stress.h"

#if defined(APP_RH_ENDURANCE_TEST) && (APP_RH_ENDURANCE_TEST)

#include "runhours_journal.h"
#include "runhours_crypto.h"
#include "runhours_format.h"
#include "memory_layout.h"

#include "mcuboot_app_support.h"
#include "fsl_debug_console.h"

#include "FreeRTOS.h"
#include "task.h"

#include <string.h>

static volatile uint8_t s_running;
static volatile uint8_t s_complete;
static volatile uint8_t s_armed;
static uint64_t s_target;
static uint64_t s_start_boot_q;
static uint32_t s_attempts;
static uint32_t s_commits_ok;
static uint32_t s_commit_fail;
static uint32_t s_deadline_miss;

static rh_erase_event_t s_erase_ring[RH_ERASE_RING_CAP];
static uint32_t s_erase_next_id = 1;
static uint32_t s_erase_head; /* next write index */
static uint32_t s_erase_count_in_ring;
static uint32_t s_erase_total;
static uint32_t s_erase_fail;
static uint32_t s_erase_overflow;
static uint32_t s_erase_host_last_id; /* highest id host has acknowledged via RHERASE */
static uint32_t s_sector_erase_count[RH_SECTOR_COUNT];

void rh_stress_boot_banner(void)
{
    PRINTF("\r\n*** QA RUN-HOURS ENDURANCE MODE ***\r\n");
    PRINTF("period_ms=%u\r\n", (unsigned)RH_STRESS_PERIOD_MS);
    PRINTF("production_quantum_s=%u\r\n", (unsigned)RH_QUANTUM_SECONDS);
    PRINTF("target_delta=%lu\r\n", (unsigned long)RH_STRESS_TARGET_DELTA);
    PRINTF("NOT FOR PRODUCTION\r\n\r\n");
}

void rh_erase_note(uint32_t addr, uint16_t sector_id, int erase_ok, uint64_t seq, uint64_t quanta,
                   uint8_t remap)
{
    rh_erase_event_t ev;
    uint8_t pool;

    if (sector_id >= RH_SECTOR_COUNT)
    {
        return;
    }
    if (erase_ok)
    {
        s_erase_total++;
        s_sector_erase_count[sector_id]++;
    }
    else
    {
        s_erase_fail++;
        s_erase_total++; /* attempt counted */
    }

    pool = (sector_id >= RH_POOL_A_SECTORS) ? 1u : 0u;
    memset(&ev, 0, sizeof(ev));
    ev.id = s_erase_next_id++;
    ev.uptime_ms = (uint32_t)(xTaskGetTickCount() * portTICK_PERIOD_MS);
    ev.addr = addr;
    ev.pool = pool;
    ev.sector = (uint8_t)((pool == 0u) ? sector_id : (sector_id - RH_POOL_A_SECTORS));
    ev.result = erase_ok ? 0u : 1u;
    ev.remap = remap;
    ev.sector_erase_count = s_sector_erase_count[sector_id];
    ev.erase_total = s_erase_total;
    ev.seq = seq;
    ev.quanta = quanta;

    if (s_erase_count_in_ring >= RH_ERASE_RING_CAP)
    {
        /* Drop oldest. Overflow only if that event was never acknowledged by host. */
        uint32_t oldest_idx = (s_erase_head >= RH_ERASE_RING_CAP) ? (s_erase_head - RH_ERASE_RING_CAP) : 0u;
        const rh_erase_event_t *oldest = &s_erase_ring[oldest_idx % RH_ERASE_RING_CAP];
        if (oldest->id > s_erase_host_last_id)
        {
            s_erase_overflow++;
        }
    }
    else
    {
        s_erase_count_in_ring++;
    }
    s_erase_ring[s_erase_head % RH_ERASE_RING_CAP] = ev;
    s_erase_head++;
}

size_t rh_erase_fetch_after(uint32_t last_id, rh_erase_event_t *out, size_t max_out, int *more)
{
    size_t n = 0;
    uint32_t i;
    uint32_t stored = s_erase_count_in_ring;
    uint32_t start;

    /* Host cursor: plan overflow = PC fell behind unread events. */
    if (last_id > s_erase_host_last_id)
    {
        s_erase_host_last_id = last_id;
    }
    if (more)
    {
        *more = 0;
    }
    if (out == NULL || max_out == 0u || stored == 0u)
    {
        return 0;
    }
    start = (s_erase_head >= stored) ? (s_erase_head - stored) : 0u;
    for (i = 0; i < stored; i++)
    {
        const rh_erase_event_t *e = &s_erase_ring[(start + i) % RH_ERASE_RING_CAP];
        if (e->id <= last_id)
        {
            continue;
        }
        if (n >= max_out)
        {
            if (more)
            {
                *more = 1;
            }
            break;
        }
        out[n++] = *e;
        if (e->id > s_erase_host_last_id)
        {
            s_erase_host_last_id = e->id;
        }
    }
    return n;
}

int rh_stress_start(uint64_t absolute_target_quanta)
{
    uint64_t q = 0;
    if (rh_journal_get_quanta(&q) != RH_OK)
    {
        return -1;
    }
    if (absolute_target_quanta == 0ull)
    {
        return -1;
    }
    s_start_boot_q = q;
    s_target = absolute_target_quanta;
    s_complete = 0;
    s_armed = 1;
    s_attempts = 0;
    s_commits_ok = 0;
    s_commit_fail = 0;
    s_deadline_miss = 0;
    if (q >= s_target)
    {
        s_running = 0;
        s_complete = 1;
        PRINTF("rhstress: already at/above target quanta=%lu target=%lu\r\n", (unsigned long)q,
               (unsigned long)s_target);
        return 0;
    }
    s_running = 1;
    PRINTF("rhstress: START quanta=%lu target=%lu\r\n", (unsigned long)q, (unsigned long)s_target);
    return 0;
}

void rh_stress_stop(void)
{
    s_running = 0;
    s_armed = 0;
    PRINTF("rhstress: STOP\r\n");
}

void rh_stress_get_status(rh_stress_status_t *out)
{
    rh_diag_t d;
    if (out == NULL)
    {
        return;
    }
    memset(out, 0, sizeof(*out));
    rh_journal_get_diag(&d);
    out->running = s_running;
    out->complete = s_complete;
    out->armed = s_armed;
    out->start_boot_quanta = s_start_boot_q;
    out->target_quanta = s_target;
    out->quanta = d.quanta;
    out->seq = d.seq;
    out->attempts = s_attempts;
    out->commits_ok = s_commits_ok;
    out->commit_fail = s_commit_fail;
    out->deadline_miss = s_deadline_miss;
    out->erase_total = s_erase_total;
    out->erase_fail = s_erase_fail;
    out->erase_overflow = s_erase_overflow;
    out->auth_fail = d.auth_fail;
    out->torn = d.torn_recoveries;
    out->flash_err = d.flash_errors;
    out->deferred = d.deferred_ota;
    out->key_ver = d.key_version;
    out->key_id = d.key_id;
    out->key_ks = d.key_ks_state;
    out->remap = d.remap_active;
    out->uptime_s = (uint32_t)(xTaskGetTickCount() / configTICK_RATE_HZ);
}

static void stress_task(void *arg)
{
    TickType_t last = xTaskGetTickCount();
    (void)arg;

    for (;;)
    {
        TickType_t wake_deadline = last + pdMS_TO_TICKS(RH_STRESS_PERIOD_MS);
        vTaskDelayUntil(&last, pdMS_TO_TICKS(RH_STRESS_PERIOD_MS));
        if (xTaskGetTickCount() > (wake_deadline + pdMS_TO_TICKS(20u)))
        {
            s_deadline_miss++;
        }

        if (!s_running)
        {
            continue;
        }

        {
            uint64_t q = 0;
            rh_status_t st;
            if (rh_journal_get_quanta(&q) != RH_OK)
            {
                s_commit_fail++;
                continue;
            }
            if (q >= s_target)
            {
                s_running = 0;
                s_complete = 1;
                PRINTF("rhstress: COMPLETE quanta=%lu target=%lu\r\n", (unsigned long)q,
                       (unsigned long)s_target);
                continue;
            }

            s_attempts++;
            st = rh_journal_append_quanta(q + 1ull);
            if (st == RH_OK)
            {
                s_commits_ok++;
                if (rh_journal_get_quanta(&q) == RH_OK && q >= s_target)
                {
                    s_running = 0;
                    s_complete = 1;
                    PRINTF("rhstress: COMPLETE quanta=%lu target=%lu\r\n", (unsigned long)q,
                           (unsigned long)s_target);
                }
            }
            else
            {
                s_commit_fail++;
            }
        }
    }
}

void rh_stress_task_start(void)
{
    rh_stress_boot_banner();
    if (xTaskCreate(stress_task, "rhstress", 1536, NULL, tskIDLE_PRIORITY + 2, NULL) != pdPASS)
    {
        PRINTF("rhstress: task create failed\r\n");
    }
}

#endif /* APP_RH_ENDURANCE_TEST */
