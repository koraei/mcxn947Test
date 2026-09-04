/*
 * QA-only run-hours endurance (APP_RH_ENDURANCE_TEST=1).
 * Not compiled into production builds.
 */
#ifndef RUNHOURS_STRESS_H_
#define RUNHOURS_STRESS_H_

#include <stddef.h>
#include <stdint.h>

#if defined(APP_RH_ENDURANCE_TEST) && (APP_RH_ENDURANCE_TEST)

#define RH_STRESS_PERIOD_MS     (250u)
#define RH_STRESS_TARGET_DELTA  (525600ull)
#define RH_ERASE_RING_CAP       (256u)

typedef struct {
    uint32_t id;
    uint32_t uptime_ms;
    uint32_t addr;
    uint8_t  pool; /* 0=A, 1=B */
    uint8_t  sector;
    uint8_t  result; /* 0=OK, 1=FAIL */
    uint8_t  remap;
    uint32_t sector_erase_count;
    uint32_t erase_total;
    uint64_t seq;
    uint64_t quanta;
} rh_erase_event_t;

typedef struct {
    uint8_t  running;
    uint8_t  complete;
    uint8_t  armed;
    uint8_t  key_ver;
    uint8_t  key_ks;
    uint8_t  remap;
    uint16_t key_id;
    uint64_t start_boot_quanta;
    uint64_t target_quanta;
    uint64_t quanta;
    uint64_t seq;
    uint32_t attempts;
    uint32_t commits_ok;
    uint32_t commit_fail;
    uint32_t deadline_miss;
    uint32_t erase_total;
    uint32_t erase_fail;
    uint32_t erase_overflow;
    uint32_t auth_fail;
    uint32_t torn;
    uint32_t flash_err;
    uint32_t deferred;
    uint32_t uptime_s;
} rh_stress_status_t;

void rh_stress_boot_banner(void);
void rh_stress_task_start(void);

/* Host: RHSTRESS START <absolute_target_quanta> */
int rh_stress_start(uint64_t absolute_target_quanta);
void rh_stress_stop(void);
void rh_stress_get_status(rh_stress_status_t *out);

/* Called from journal erase path (QA only). */
void rh_erase_note(uint32_t addr, uint16_t sector_id, int erase_ok, uint64_t seq, uint64_t quanta,
                   uint8_t remap);

/* RHERASE <last_id>: fill out[] with events id > last_id; set *more if truncated. */
size_t rh_erase_fetch_after(uint32_t last_id, rh_erase_event_t *out, size_t max_out, int *more);

#endif /* APP_RH_ENDURANCE_TEST */

#endif /* RUNHOURS_STRESS_H_ */
