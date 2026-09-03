/*
 * Product mTLS wrapper around lwIP sockets + NXP mbedTLS 3.x / PSA.
 * Pattern follows middleware/lwip/.../httpsrv_tls.c (BIO send/recv) without HTTPS.
 */
#include "mtls_socket.h"
#include "diagnostics.h"

#include "fsl_debug_console.h"

#include "lwip/sockets.h"

#include "mbedtls/ssl.h"
#include "mbedtls/x509_crt.h"
#include "mbedtls/pk.h"
#include "mbedtls/error.h"
#include "psa/crypto.h"
#include "threading_alt.h"

#include "FreeRTOS.h"
#include "task.h"

#include <string.h>

/* Generated at build time into ignored path; see tools/gen_mtls_creds_c.py */
extern const char mtls_ca_pem[];
extern const unsigned int mtls_ca_pem_len;
extern const char mtls_server_crt_pem[];
extern const unsigned int mtls_server_crt_pem_len;
extern const char mtls_server_key_pem[];
extern const unsigned int mtls_server_key_pem_len;

static mbedtls_x509_crt s_ca;
static mbedtls_x509_crt s_own_crt;
static mbedtls_pk_context s_own_key;
static mbedtls_ssl_config s_conf;
static int s_ready;

static int psa_rng(void *p_rng, unsigned char *output, size_t len)
{
    (void)p_rng;
    return (psa_generate_random(output, len) == PSA_SUCCESS) ? 0 : -1;
}

static int bio_send(void *ctx, const unsigned char *buf, size_t len)
{
    int fd = (int)(intptr_t)ctx;
    int n  = lwip_send(fd, buf, len, 0);
    if (n < 0)
    {
        return MBEDTLS_ERR_SSL_WANT_WRITE;
    }
    return n;
}

static int bio_recv(void *ctx, unsigned char *buf, size_t len)
{
    int fd = (int)(intptr_t)ctx;
    int n  = lwip_recv(fd, buf, len, 0);
    if (n < 0)
    {
        /* lwIP SO_RCVTIMEO → EWOULDBLOCK/EAGAIN mapped as WANT_READ for mbedtls */
        return MBEDTLS_ERR_SSL_WANT_READ;
    }
    if (n == 0)
    {
        return 0;
    }
    return n;
}

static void set_sock_timeout_ms(int fd, uint32_t ms)
{
    struct timeval tv;
    tv.tv_sec  = (long)(ms / 1000u);
    tv.tv_usec = (long)((ms % 1000u) * 1000u);
    (void)lwip_setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    (void)lwip_setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
}

/*
 * No trusted wall clock on device: ignore only time-validity flags.
 * Signature / CA / key-usage / identity failures remain fatal.
 */
static int verify_callback(void *data, mbedtls_x509_crt *crt, int depth, uint32_t *flags)
{
    (void)data;
    (void)crt;
    (void)depth;
    if (flags != NULL)
    {
        *flags &= ~(uint32_t)(MBEDTLS_X509_BADCERT_EXPIRED | MBEDTLS_X509_BADCERT_FUTURE);
    }
    return 0;
}

int mtls_global_init(void)
{
    int ret;

    if (s_ready)
    {
        return 0;
    }

    config_mbedtls_threading_alt();
    if (psa_crypto_init() != PSA_SUCCESS)
    {
        PRINTF("mtls: psa_crypto_init failed\r\n");
        return -1;
    }

    mbedtls_x509_crt_init(&s_ca);
    mbedtls_x509_crt_init(&s_own_crt);
    mbedtls_pk_init(&s_own_key);
    mbedtls_ssl_config_init(&s_conf);

    ret = mbedtls_x509_crt_parse(&s_ca, (const unsigned char *)mtls_ca_pem, mtls_ca_pem_len);
    if (ret != 0)
    {
        PRINTF("mtls: CA parse %d\r\n", ret);
        return -1;
    }

    ret = mbedtls_x509_crt_parse(&s_own_crt, (const unsigned char *)mtls_server_crt_pem, mtls_server_crt_pem_len);
    if (ret != 0)
    {
        PRINTF("mtls: server cert parse %d\r\n", ret);
        return -1;
    }

    ret = mbedtls_pk_parse_key(&s_own_key, (const unsigned char *)mtls_server_key_pem, mtls_server_key_pem_len, NULL, 0,
                               psa_rng, NULL);
    if (ret != 0)
    {
        PRINTF("mtls: server key parse %d\r\n", ret);
        return -1;
    }

    ret = mbedtls_ssl_config_defaults(&s_conf, MBEDTLS_SSL_IS_SERVER, MBEDTLS_SSL_TRANSPORT_STREAM,
                                      MBEDTLS_SSL_PRESET_DEFAULT);
    if (ret != 0)
    {
        PRINTF("mtls: ssl_config_defaults %d\r\n", ret);
        return -1;
    }

    mbedtls_ssl_conf_rng(&s_conf, psa_rng, NULL);
    mbedtls_ssl_conf_authmode(&s_conf, MBEDTLS_SSL_VERIFY_REQUIRED);
    mbedtls_ssl_conf_ca_chain(&s_conf, &s_ca, NULL);
    mbedtls_ssl_conf_verify(&s_conf, verify_callback, NULL);

    ret = mbedtls_ssl_conf_own_cert(&s_conf, &s_own_crt, &s_own_key);
    if (ret != 0)
    {
        PRINTF("mtls: own_cert %d\r\n", ret);
        return -1;
    }

    s_ready = 1;
    PRINTF("mtls: global init OK\r\n");
    return 0;
}

int mtls_session_open(mtls_session_t *session, int socket_fd, uint32_t handshake_timeout_ms)
{
    int ret;
    TickType_t t0;
    TickType_t budget;

    if (!s_ready || session == NULL || socket_fd < 0)
    {
        return -1;
    }

    memset(session, 0, sizeof(*session));
    session->fd = socket_fd;
    session->active = 0;
    mbedtls_ssl_init(&session->ssl);

    ret = mbedtls_ssl_setup(&session->ssl, &s_conf);
    if (ret != 0)
    {
        mbedtls_ssl_free(&session->ssl);
        return -1;
    }

    mbedtls_ssl_set_bio(&session->ssl, (void *)(intptr_t)socket_fd, bio_send, bio_recv, NULL);
    set_sock_timeout_ms(socket_fd, handshake_timeout_ms ? handshake_timeout_ms : MTLS_HANDSHAKE_TIMEOUT_MS);

    budget = pdMS_TO_TICKS(handshake_timeout_ms ? handshake_timeout_ms : MTLS_HANDSHAKE_TIMEOUT_MS);
    t0     = xTaskGetTickCount();

    for (;;)
    {
        ret = mbedtls_ssl_handshake(&session->ssl);
        if (ret == 0)
        {
            break;
        }
        if (ret != MBEDTLS_ERR_SSL_WANT_READ && ret != MBEDTLS_ERR_SSL_WANT_WRITE)
        {
            PRINTF("mtls: handshake fail %d\r\n", ret);
            g_mtls_handshake_fail++;
            mtls_session_close(session);
            return -1;
        }
        if ((xTaskGetTickCount() - t0) > budget)
        {
            PRINTF("mtls: handshake timeout\r\n");
            g_mtls_timeout++;
            g_mtls_handshake_fail++;
            mtls_session_close(session);
            return -1;
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }

    if (mbedtls_ssl_get_verify_result(&session->ssl) != 0)
    {
        PRINTF("mtls: peer verify flags=0x%lx\r\n", (unsigned long)mbedtls_ssl_get_verify_result(&session->ssl));
        g_mtls_verify_fail++;
        g_mtls_handshake_fail++;
        mtls_session_close(session);
        return -1;
    }

    session->active = 1;
    g_mtls_handshake_ok++;
    return 0;
}

int mtls_read(mtls_session_t *session, void *buf, size_t max_len, uint32_t timeout_ms)
{
    int ret;

    if (session == NULL || !session->active || buf == NULL || max_len == 0)
    {
        return -1;
    }

    set_sock_timeout_ms(session->fd, timeout_ms);

    for (;;)
    {
        ret = mbedtls_ssl_read(&session->ssl, (unsigned char *)buf, max_len);
        if (ret == MBEDTLS_ERR_SSL_WANT_READ || ret == MBEDTLS_ERR_SSL_WANT_WRITE)
        {
            return -1; /* timed out or would-block treated as soft fail by caller */
        }
        if (ret == MBEDTLS_ERR_SSL_PEER_CLOSE_NOTIFY)
        {
            g_mtls_peer_close++;
            return 0;
        }
        return ret;
    }
}

int mtls_read_exact(mtls_session_t *session, void *buf, size_t len, uint32_t timeout_ms)
{
    size_t got = 0;
    TickType_t t0;
    TickType_t budget;

    if (session == NULL || !session->active)
    {
        return -1;
    }

    budget = pdMS_TO_TICKS(timeout_ms);
    t0     = xTaskGetTickCount();

    while (got < len)
    {
        int n;
        uint32_t left_ms = timeout_ms;

        if ((xTaskGetTickCount() - t0) > budget)
        {
            return -1;
        }
        left_ms = timeout_ms; /* per-call SO_RCVTIMEO already finite */
        n       = mtls_read(session, (uint8_t *)buf + got, len - got, left_ms);
        if (n <= 0)
        {
            return -1;
        }
        got += (size_t)n;
    }
    return 0;
}

int mtls_write_all(mtls_session_t *session, const void *buf, size_t len, uint32_t timeout_ms)
{
    size_t sent = 0;
    TickType_t t0;
    TickType_t budget;

    if (session == NULL || !session->active || buf == NULL)
    {
        return -1;
    }

    set_sock_timeout_ms(session->fd, timeout_ms);
    budget = pdMS_TO_TICKS(timeout_ms);
    t0     = xTaskGetTickCount();

    while (sent < len)
    {
        int n = mbedtls_ssl_write(&session->ssl, (const unsigned char *)buf + sent, len - sent);
        if (n == MBEDTLS_ERR_SSL_WANT_READ || n == MBEDTLS_ERR_SSL_WANT_WRITE)
        {
            if ((xTaskGetTickCount() - t0) > budget)
            {
                return -1;
            }
            vTaskDelay(pdMS_TO_TICKS(5));
            continue;
        }
        if (n <= 0)
        {
            return -1;
        }
        sent += (size_t)n;
    }
    return 0;
}

void mtls_session_close(mtls_session_t *session)
{
    if (session == NULL)
    {
        return;
    }
    if (session->active)
    {
        (void)mbedtls_ssl_close_notify(&session->ssl);
    }
    mbedtls_ssl_free(&session->ssl);
    session->active = 0;
    session->fd     = -1;
}
