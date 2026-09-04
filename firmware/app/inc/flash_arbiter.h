/*
 * Single-writer flash arbiter: OTA exclusive vs journal deferred writes.
 */
#ifndef FLASH_ARBITER_H_
#define FLASH_ARBITER_H_

#include <stdint.h>

typedef enum {
    FLASH_OWNER_NONE = 0,
    FLASH_OWNER_JOURNAL,
    FLASH_OWNER_OTA
} flash_owner_t;

void flash_arbiter_init(void);

/* Blocking take; OTA should use FLASH_OWNER_OTA. */
int flash_arbiter_acquire(flash_owner_t owner, uint32_t timeout_ms);

void flash_arbiter_release(flash_owner_t owner);

flash_owner_t flash_arbiter_owner(void);

uint32_t flash_arbiter_journal_deferred_count(void);
void flash_arbiter_note_journal_deferred(void);

#endif /* FLASH_ARBITER_H_ */
