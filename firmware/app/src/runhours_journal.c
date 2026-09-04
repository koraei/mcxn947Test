/*
 * Stub / build-gated journal. Full AES-GCM append lands with APP_FLASH_LAYOUT_512K
 * after host fault matrix PASS. Until CMPA remap, live flash uses legacy 1 MiB slots
 * and this module reports NOT_PROVISIONED so product path is unchanged.
 */
#include "runhours_journal.h"
#include "runhours_format.h"
#include <stddef.h>

#if defined(APP_FLASH_LAYOUT_512K)
/* Device implementation follows in M4 once key derivation + flash arbiter land. */
static uint64_t s_quanta;
static int s_ready;

rh_status_t rh_journal_init(void)
{
    /* Recovery scanner not yet wired to on-chip flash — keep boot safe. */
    s_ready = 0;
    s_quanta = 0;
    return RH_ERR_NOT_PROVISIONED;
}

rh_status_t rh_journal_get_quanta(uint64_t *out_quanta)
{
    if (out_quanta == NULL)
    {
        return RH_ERR_IO;
    }
    if (!s_ready)
    {
        return RH_ERR_NOT_PROVISIONED;
    }
    *out_quanta = s_quanta;
    return RH_OK;
}

rh_status_t rh_journal_append_quanta(uint64_t quanta)
{
    (void)quanta;
    return RH_ERR_NOT_PROVISIONED;
}

#else

rh_status_t rh_journal_init(void)
{
    return RH_ERR_NOT_PROVISIONED;
}

rh_status_t rh_journal_get_quanta(uint64_t *out_quanta)
{
    if (out_quanta)
    {
        *out_quanta = 0;
    }
    return RH_ERR_NOT_PROVISIONED;
}

rh_status_t rh_journal_append_quanta(uint64_t quanta)
{
    (void)quanta;
    return RH_ERR_NOT_PROVISIONED;
}

#endif

uint64_t rh_journal_seconds(void)
{
    uint64_t q = 0;
    if (rh_journal_get_quanta(&q) != RH_OK)
    {
        return 0;
    }
    return q * (uint64_t)RH_QUANTUM_SECONDS;
}
