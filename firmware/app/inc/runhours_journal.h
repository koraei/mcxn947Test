/*
 * Encrypted running-hours journal API (plan M3/M4 / Gate 10).
 */
#ifndef RUNHOURS_JOURNAL_H_
#define RUNHOURS_JOURNAL_H_

#include <stdint.h>
#include "runhours_format.h"

typedef enum {
    RH_OK = 0,
    RH_ERR_CORRUPT = -1,
    RH_ERR_IO = -2,
    RH_ERR_FULL = -3,
    RH_ERR_BUSY = -4,
    RH_ERR_NOT_PROVISIONED = -5
} rh_status_t;

/* Fault-injection stages for HW power-cut / reset campaign (busy-wait until reset). */
typedef enum {
    RH_FAULT_NONE = 0,
    RH_FAULT_BEFORE_RECORD,
    RH_FAULT_DURING_PHRASE0,
    RH_FAULT_DURING_PHRASE1,
    RH_FAULT_DURING_PHRASE2,
    RH_FAULT_BEFORE_COMMIT,
    RH_FAULT_AFTER_COMMIT,
    RH_FAULT_DURING_ERASE,
    RH_FAULT_BEFORE_READY,
    RH_FAULT_AFTER_READY_BEFORE_CKPT,
    RH_FAULT_AFTER_CHECKPOINT
} rh_fault_stage_t;

rh_status_t rh_journal_init(void);
rh_status_t rh_journal_get_quanta(uint64_t *out_quanta);
rh_status_t rh_journal_append_quanta(uint64_t quanta);
uint64_t rh_journal_seconds(void);
void rh_journal_get_diag(rh_diag_t *out);

/* Qualification helpers (Hello commands). */
rh_status_t rh_journal_force_next_quantum(void);
void rh_journal_arm_fault(rh_fault_stage_t stage);
rh_fault_stage_t rh_journal_fault_armed(void);
/* Qual only: erase all journal sectors and re-init virgin INITIAL record. */
rh_status_t rh_journal_wipe_and_init(void);

#endif /* RUNHOURS_JOURNAL_H_ */
