/*
 * QA-only persistent mTLS stream for M4 load soak.
 * Compiled only when APP_QA_STREAM=1. Production builds leave this out of use.
 *
 * TCP :5001 — same mtls_socket + lwIP + mbedTLS path as :5000.
 * Frame (1024 B): seq(u32 LE) | magic 0x4D345331 | payload[1016] patterned (seq+i)&0xFF
 * Server verifies RX, echoes same frame (bidirectional TLS traffic).
 */
#if APP_QA_STREAM

#include "qa_stream.h"
#include "app_config.h"
#include "diagnostics.h"
#include "mtls_socket.h"

#include "lwip/sockets.h"
#include "fsl_debug_console.h"

#include "FreeRTOS.h"
#include "task.h"

#include <malloc.h>
#include <string.h>

#ifndef QA_STREAM_TCP_PORT
#define QA_STREAM_TCP_PORT 5001u
#endif

#define QA_FRAME_B     1024u
#define QA_MAGIC       0x4D345331u /* 'M4S1' */
#define QA_HDR_B       8u
#define QA_PAYLOAD_B   (QA_FRAME_B - QA_HDR_B)
#define QA_IO_TO_MS    5000u
#define QA_STATS_EVERY 200u

static TaskHandle_t s_qa_task;
static volatile uint32_t s_qa_rx_ok;
static volatile uint32_t s_qa_tx_ok;
static volatile uint32_t s_qa_verify_fail;
static volatile uint32_t s_qa_io_err;
static volatile uint32_t s_qa_disconnect;
static volatile uint32_t s_qa_rx_bytes;
static volatile uint32_t s_qa_tx_bytes;
static volatile uint32_t s_qa_min_free_heap = 0xFFFFFFFFu;
static volatile UBaseType_t s_qa_stack_hwm = 0xFFFFFFFFu;

static void close_fd(int *fd)
{
    if (*fd >= 0)
    {
        closesocket(*fd);
        *fd = -1;
    }
}

static int verify_payload(uint32_t seq, const uint8_t *p, size_t n)
{
    for (size_t i = 0; i < n; i++)
    {
        if (p[i] != (uint8_t)((seq + (uint32_t)i) & 0xFFu))
        {
            return -1;
        }
    }
    return 0;
}

static void sample_resources(void)
{
    struct mallinfo mi = mallinfo();
    uint32_t free_b    = (uint32_t)mi.fordblks;
    if (free_b < s_qa_min_free_heap)
    {
        s_qa_min_free_heap = free_b;
    }
#if (INCLUDE_uxTaskGetStackHighWaterMark == 1)
    if (s_qa_task != NULL)
    {
        UBaseType_t hwm = uxTaskGetStackHighWaterMark(s_qa_task);
        if (hwm < s_qa_stack_hwm)
        {
            s_qa_stack_hwm = hwm;
        }
    }
#endif
}

static void print_stats(void)
{
    sample_resources();
    PRINTF(
        "QASTRM rx_ok=%lu tx_ok=%lu vfail=%lu io_err=%lu disc=%lu "
        "rx_b=%lu tx_b=%lu heap_free_min=%lu stack_hwm_words=%lu\r\n",
        (unsigned long)s_qa_rx_ok, (unsigned long)s_qa_tx_ok, (unsigned long)s_qa_verify_fail,
        (unsigned long)s_qa_io_err, (unsigned long)s_qa_disconnect, (unsigned long)s_qa_rx_bytes,
        (unsigned long)s_qa_tx_bytes, (unsigned long)s_qa_min_free_heap,
        (unsigned long)s_qa_stack_hwm);
}

static int read_exact(mtls_session_t *s, uint8_t *buf, size_t need)
{
    return mtls_read_exact(s, buf, need, QA_IO_TO_MS);
}

static void handle_stream(int client)
{
    mtls_session_t session;
    uint8_t frame[QA_FRAME_B];
    uint32_t since_stats = 0;

    if (mtls_session_open(&session, client, MTLS_HANDSHAKE_TIMEOUT_MS) != 0)
    {
        g_mtls_session_abort++;
        s_qa_io_err++;
        close_fd(&client);
        return;
    }

    PRINTF("QASTRM session open\r\n");

    for (;;)
    {
        uint32_t seq;
        uint32_t magic;

        if (read_exact(&session, frame, QA_FRAME_B) != 0)
        {
            s_qa_disconnect++;
            s_qa_io_err++;
            break;
        }
        s_qa_rx_bytes += QA_FRAME_B;
        g_normal_tls_rx_bytes += QA_FRAME_B;

        memcpy(&seq, &frame[0], 4);
        memcpy(&magic, &frame[4], 4);
        if (magic != QA_MAGIC || verify_payload(seq, &frame[QA_HDR_B], QA_PAYLOAD_B) != 0)
        {
            s_qa_verify_fail++;
            break;
        }
        s_qa_rx_ok++;

        /* Echo same frame — exercises TLS write path. */
        if (mtls_write_all(&session, frame, QA_FRAME_B, QA_IO_TO_MS) != 0)
        {
            s_qa_disconnect++;
            s_qa_io_err++;
            break;
        }
        s_qa_tx_bytes += QA_FRAME_B;
        g_normal_tls_tx_bytes += QA_FRAME_B;
        s_qa_tx_ok++;

        since_stats++;
        if (since_stats >= QA_STATS_EVERY)
        {
            since_stats = 0;
            print_stats();
        }
        sample_resources();
    }

    print_stats();
    mtls_session_close(&session);
    close_fd(&client);
    PRINTF("QASTRM session closed (listen continues)\r\n");
}

static void qa_stream_task(void *arg)
{
    (void)arg;
    s_qa_task = xTaskGetCurrentTaskHandle();
    sample_resources();

    for (;;)
    {
        int server = socket(AF_INET, SOCK_STREAM, 0);
        if (server < 0)
        {
            s_qa_io_err++;
            vTaskDelay(pdMS_TO_TICKS(1000));
            continue;
        }

        int yes = 1;
        (void)lwip_setsockopt(server, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));

        struct sockaddr_in addr;
        memset(&addr, 0, sizeof(addr));
        addr.sin_family      = AF_INET;
        addr.sin_port        = htons(QA_STREAM_TCP_PORT);
        addr.sin_addr.s_addr = htonl(INADDR_ANY);

        if (bind(server, (struct sockaddr *)&addr, sizeof(addr)) < 0 || listen(server, 1) < 0)
        {
            s_qa_io_err++;
            close_fd(&server);
            vTaskDelay(pdMS_TO_TICKS(1000));
            continue;
        }

        PRINTF("QASTRM mTLS listening on port %u (APP_QA_STREAM=1)\r\n", (unsigned)QA_STREAM_TCP_PORT);

        for (;;)
        {
            int client = accept(server, NULL, NULL);
            if (client < 0)
            {
                s_qa_io_err++;
                continue;
            }
            handle_stream(client);
        }
    }
}

void qa_stream_service_start(void)
{
    if (xTaskCreate(qa_stream_task, "qastrm", 2560, NULL, tskIDLE_PRIORITY + 3, &s_qa_task) != pdPASS)
    {
        PRINTF("QASTRM task create failed\r\n");
        s_qa_task = NULL;
    }
}

#endif /* APP_QA_STREAM */
