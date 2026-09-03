#include "hello_service.h"
#include "app_config.h"
#include "diagnostics.h"
#include "mtls_socket.h"

#include "lwip/sockets.h"
#include "lwip/netdb.h"
#include "fsl_debug_console.h"

#include "FreeRTOS.h"
#include "task.h"

#include <stdio.h>
#include <string.h>

static void close_fd(int *fd)
{
    if (*fd >= 0)
    {
        closesocket(*fd);
        *fd = -1;
    }
}

static void handle_client(int client)
{
    char buf[HELLO_MAX_REQ_B + 1];
    mtls_session_t session;
    int n;

    if (mtls_session_open(&session, client, MTLS_HANDSHAKE_TIMEOUT_MS) != 0)
    {
        g_hello_error_count++;
        g_mtls_session_abort++;
        close_fd(&client);
        return;
    }

    n = mtls_read(&session, buf, HELLO_MAX_REQ_B, HELLO_RECV_TO_MS);
    if (n <= 0)
    {
        g_hello_error_count++;
        mtls_session_close(&session);
        close_fd(&client);
        return;
    }

    g_normal_tls_rx_bytes += (uint32_t)n;
    buf[n] = '\0';
    while (n > 0 && (buf[n - 1] == '\n' || buf[n - 1] == '\r'))
    {
        buf[--n] = '\0';
    }

    PRINTF("RX plaintext: %s\r\n", buf);

    if ((n == 10) && (strncmp(buf, "Hello MCXN", 10) == 0))
    {
        const char *reply = APP_HELLO_REPLY "\n";
        PRINTF("TX plaintext: %s", reply);
        if (mtls_write_all(&session, reply, strlen(reply), MTLS_IO_TIMEOUT_MS) == 0)
        {
            g_normal_tls_tx_bytes += (uint32_t)strlen(reply);
        }
    }
    else if ((n >= 4) && (strncmp(buf, "ECHO", 4) == 0))
    {
        const char *payload = "";
        char reply[HELLO_MAX_REQ_B + 24];
        int len;

        if ((n > 5) && (buf[4] == ' '))
        {
            payload = &buf[5];
        }
        len = snprintf(reply, sizeof(reply), "ECHO %s %s\n", APP_VARIANT, payload);
        if (len > 0)
        {
            if (mtls_write_all(&session, reply, (size_t)len, MTLS_IO_TIMEOUT_MS) == 0)
            {
                g_normal_tls_tx_bytes += (uint32_t)len;
            }
        }
    }
    else if ((n >= 6) && (strncmp(buf, "STATUS", 6) == 0))
    {
        char status[192];
        int len = snprintf(status, sizeof(status),
                           "STATUS version=%s variant=%s uuid=%s uptime_s=%lu update_window_s=%lu\n",
                           APP_VERSION_STRING, APP_VARIANT, diagnostics_uuid_hex(),
                           (unsigned long)diagnostics_uptime_s(),
                           (unsigned long)diagnostics_update_window_remaining_s());
        if (len > 0)
        {
            if (mtls_write_all(&session, status, (size_t)len, MTLS_IO_TIMEOUT_MS) == 0)
            {
                g_normal_tls_tx_bytes += (uint32_t)len;
            }
        }
    }
    else
    {
        g_hello_error_count++;
        (void)mtls_write_all(&session, "ERR\n", 4, MTLS_IO_TIMEOUT_MS);
    }

    mtls_session_close(&session);
    close_fd(&client);
}

static void hello_task(void *arg)
{
    int server = -1;
    struct sockaddr_in addr;

    (void)arg;

    for (;;)
    {
        server = socket(AF_INET, SOCK_STREAM, 0);
        if (server < 0)
        {
            g_hello_error_count++;
            vTaskDelay(pdMS_TO_TICKS(1000));
            continue;
        }

        int yes = 1;
        (void)lwip_setsockopt(server, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));

        memset(&addr, 0, sizeof(addr));
        addr.sin_family      = AF_INET;
        addr.sin_port        = htons(HELLO_TCP_PORT);
        addr.sin_addr.s_addr = htonl(INADDR_ANY);

        if (bind(server, (struct sockaddr *)&addr, sizeof(addr)) < 0)
        {
            g_hello_error_count++;
            close_fd(&server);
            vTaskDelay(pdMS_TO_TICKS(1000));
            continue;
        }

        if (listen(server, 2) < 0)
        {
            g_hello_error_count++;
            close_fd(&server);
            vTaskDelay(pdMS_TO_TICKS(1000));
            continue;
        }

        PRINTF("Hello mTLS listening on port %u\r\n", (unsigned)HELLO_TCP_PORT);

        for (;;)
        {
            struct sockaddr_in caddr;
            socklen_t clen = sizeof(caddr);
            int client     = accept(server, (struct sockaddr *)&caddr, &clen);
            if (client < 0)
            {
                g_hello_error_count++;
                continue;
            }
            g_hello_accept_count++;
            handle_client(client);
        }
    }
}

void hello_service_start(void)
{
    if (xTaskCreate(hello_task, "hello", 4096, NULL, tskIDLE_PRIORITY + 3, NULL) != pdPASS)
    {
        PRINTF("Hello task create failed\r\n");
    }
}
