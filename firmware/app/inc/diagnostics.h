#ifndef DIAGNOSTICS_H_
#define DIAGNOSTICS_H_

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

void diagnostics_init(void);
const char *diagnostics_uuid_hex(void);
const uint8_t *diagnostics_uuid_bytes(void);
uint32_t diagnostics_uptime_s(void);
uint32_t diagnostics_update_window_remaining_s(void);
void diagnostics_mark_app_start(void);

/* Counters for prototype qualification */
extern volatile uint32_t g_hello_accept_count;
extern volatile uint32_t g_hello_error_count;
extern volatile uint32_t g_update_accept_count;
extern volatile uint32_t g_update_success_count;
extern volatile uint32_t g_update_failure_count;
extern volatile uint32_t g_sb3_failure_count;
extern volatile uint32_t g_link_down_count;
extern volatile uint32_t g_mtls_handshake_ok;
extern volatile uint32_t g_mtls_handshake_fail;
extern volatile uint32_t g_mtls_verify_fail;
extern volatile uint32_t g_mtls_timeout;
extern volatile uint32_t g_mtls_peer_close;
extern volatile uint32_t g_mtls_session_abort;
extern volatile uint32_t g_normal_tls_rx_bytes;
extern volatile uint32_t g_normal_tls_tx_bytes;
extern volatile uint32_t g_update_tls_rx_bytes;
extern volatile uint32_t g_update_tls_tx_bytes;

#ifdef __cplusplus
}
#endif

#endif /* DIAGNOSTICS_H_ */
