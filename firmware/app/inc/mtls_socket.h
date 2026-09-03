#ifndef MTLS_SOCKET_H_
#define MTLS_SOCKET_H_

#include <stddef.h>
#include <stdint.h>

#include "mbedtls/ssl.h"

#ifdef __cplusplus
extern "C" {
#endif

#ifndef MTLS_HANDSHAKE_TIMEOUT_MS
#define MTLS_HANDSHAKE_TIMEOUT_MS 5000u
#endif

#ifndef MTLS_IO_TIMEOUT_MS
#define MTLS_IO_TIMEOUT_MS 5000u
#endif

typedef struct
{
    mbedtls_ssl_context ssl;
    int fd;
    int active;
} mtls_session_t;

int mtls_global_init(void);
int mtls_session_open(mtls_session_t *session, int socket_fd, uint32_t handshake_timeout_ms);
int mtls_read(mtls_session_t *session, void *buf, size_t max_len, uint32_t timeout_ms);
int mtls_read_exact(mtls_session_t *session, void *buf, size_t len, uint32_t timeout_ms);
int mtls_write_all(mtls_session_t *session, const void *buf, size_t len, uint32_t timeout_ms);
void mtls_session_close(mtls_session_t *session);

#ifdef __cplusplus
}
#endif

#endif /* MTLS_SOCKET_H_ */
