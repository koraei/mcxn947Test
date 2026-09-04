/*
 * Encrypted running-hours journal API (plan M3/M4).
 * Device flash backend is enabled with APP_FLASH_LAYOUT_512K; host model validates protocol.
 */
#ifndef RUNHOURS_JOURNAL_H_
#define RUNHOURS_JOURNAL_H_

#include <stdint.h>

typedef enum {
    RH_OK = 0,
    RH_ERR_CORRUPT = -1,
    RH_ERR_IO = -2,
    RH_ERR_FULL = -3,
    RH_ERR_BUSY = -4,
    RH_ERR_NOT_PROVISIONED = -5
} rh_status_t;

rh_status_t rh_journal_init(void);
rh_status_t rh_journal_get_quanta(uint64_t *out_quanta);
rh_status_t rh_journal_append_quanta(uint64_t quanta);
uint64_t rh_journal_seconds(void);

#endif /* RUNHOURS_JOURNAL_H_ */
