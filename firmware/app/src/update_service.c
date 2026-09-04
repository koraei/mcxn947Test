/*
 * P5/M3: TCP :5555 → mTLS → OTAS header → raw SB3 → NXP sb3_api.
 * OTAS/SB3 bytes are plaintext after TLS decrypt. Crypto stays in SB3 + CUST_MK_SK.
 */
#include "update_service.h"
#include "app_config.h"
#include "diagnostics.h"
#include "mtls_socket.h"
#include "flash_arbiter.h"

#include "sb3_api.h"
#include "mcuboot_app_support.h"

#include "lwip/sockets.h"
#include "fsl_debug_console.h"
#include "fsl_common.h"

#include "FreeRTOS.h"
#include "task.h"

#include <string.h>

static void close_fd(int *fd)
{
    if (*fd >= 0)
    {
        closesocket(*fd);
        *fd = -1;
    }
}

static void reply_err(mtls_session_t *s, const char *msg)
{
    (void)mtls_write_all(s, msg, strlen(msg), MTLS_IO_TIMEOUT_MS);
    g_update_failure_count++;
}

static int recv_exact(mtls_session_t *s, uint8_t *buf, size_t need, uint32_t timeout_ms)
{
    return mtls_read_exact(s, buf, need, timeout_ms);
}

/* Packed wire header (28 B). */
typedef struct
{
    uint32_t magic;
    uint8_t version;
    uint8_t reserved[3];
    uint8_t uuid[16];
    uint32_t sb3_len;
} update_hdr_t;

static int handle_update_session(int client)
{
    uint8_t hdr_raw[UPDATE_HDR_SIZE_B];
    update_hdr_t hdr;
    uint8_t chunk[UPDATE_CHUNK_B];
    uint32_t remaining;
    uint32_t first_sb3_len = 0;
    int sb3_inited         = 0;
    partition_t prt_ota;
    status_t st;
    mtls_session_t session;

    if (mtls_session_open(&session, client, MTLS_HANDSHAKE_TIMEOUT_MS) != 0)
    {
        g_update_failure_count++;
        g_mtls_session_abort++;
        return -1;
    }

    if (recv_exact(&session, hdr_raw, UPDATE_HDR_SIZE_B, UPDATE_HDR_RECV_TO_MS) != 0)
    {
        reply_err(&session, "ERR TIMEOUT\n");
        mtls_session_close(&session);
        return -1;
    }
    g_update_tls_rx_bytes += UPDATE_HDR_SIZE_B;

    memcpy(&hdr.magic, &hdr_raw[0], 4);
    hdr.version = hdr_raw[4];
    memcpy(hdr.reserved, &hdr_raw[5], 3);
    memcpy(hdr.uuid, &hdr_raw[8], 16);
    memcpy(&hdr.sb3_len, &hdr_raw[24], 4);

    if (hdr.magic != UPDATE_HDR_MAGIC || hdr.version != UPDATE_HDR_VERSION)
    {
        reply_err(&session, "ERR MAGIC\n");
        mtls_session_close(&session);
        return -1;
    }

    if (memcmp(hdr.uuid, diagnostics_uuid_bytes(), 16) != 0)
    {
        reply_err(&session, "ERR UUID\n");
        mtls_session_close(&session);
        return -1;
    }

    if (hdr.sb3_len == 0u || hdr.sb3_len > UPDATE_SB3_MAX_B)
    {
        reply_err(&session, "ERR LEN\n");
        mtls_session_close(&session);
        return -1;
    }

    if (bl_get_update_partition_info(0, &prt_ota) != kStatus_Success)
    {
        reply_err(&session, "ERR IMAGE\n");
        mtls_session_close(&session);
        return -1;
    }

    PRINTF("Update: SB3 len=%lu inactive@0x%08lX\r\n", (unsigned long)hdr.sb3_len,
           (unsigned long)prt_ota.start);

    /* OTA owns flash exclusively until reset (or error release). */
    if (flash_arbiter_acquire(FLASH_OWNER_OTA, 30000) != 0)
    {
        reply_err(&session, "ERR BUSY\n");
        mtls_session_close(&session);
        return -1;
    }

    if (sb3_api_init() != kStatus_Success)
    {
        g_sb3_failure_count++;
        flash_arbiter_release(FLASH_OWNER_OTA);
        reply_err(&session, "ERR SB3\n");
        mtls_session_close(&session);
        return -1;
    }
    sb3_inited = 1;

    remaining = hdr.sb3_len;

    /* First 64 B enough for sb3_parse_header; then stream the rest. */
    {
        uint8_t first[64];
        size_t first_n = remaining < sizeof(first) ? remaining : sizeof(first);

        if (recv_exact(&session, first, first_n, UPDATE_STREAM_TO_MS) != 0)
        {
            g_sb3_failure_count++;
            sb3_api_deinit();
            flash_arbiter_release(FLASH_OWNER_OTA);
            reply_err(&session, "ERR TIMEOUT\n");
            mtls_session_close(&session);
            return -1;
        }
        g_update_tls_rx_bytes += (uint32_t)first_n;

        if (!sb3_parse_header(first, &first_sb3_len) || first_sb3_len != hdr.sb3_len)
        {
            g_sb3_failure_count++;
            sb3_api_deinit();
            flash_arbiter_release(FLASH_OWNER_OTA);
            reply_err(&session, "ERR SB3\n");
            mtls_session_close(&session);
            return -1;
        }

        st = sb3_api_pump(first, first_n);
        if (st != kStatus_Success)
        {
            g_sb3_failure_count++;
            sb3_api_deinit();
            flash_arbiter_release(FLASH_OWNER_OTA);
            reply_err(&session, "ERR SB3\n");
            mtls_session_close(&session);
            return -1;
        }
        remaining -= (uint32_t)first_n;
    }

    while (remaining > 0u)
    {
        size_t want = remaining > UPDATE_CHUNK_B ? UPDATE_CHUNK_B : remaining;
        int n;

        n = mtls_read(&session, chunk, want, UPDATE_STREAM_TO_MS);
        if (n <= 0)
        {
            g_sb3_failure_count++;
            sb3_api_deinit();
            flash_arbiter_release(FLASH_OWNER_OTA);
            reply_err(&session, "ERR TIMEOUT\n");
            mtls_session_close(&session);
            return -1;
        }
        g_update_tls_rx_bytes += (uint32_t)n;

        st = sb3_api_pump(chunk, (size_t)n);
        if (st != kStatus_Success)
        {
            g_sb3_failure_count++;
            sb3_api_deinit();
            flash_arbiter_release(FLASH_OWNER_OTA);
            reply_err(&session, "ERR SB3\n");
            mtls_session_close(&session);
            return -1;
        }

        remaining -= (uint32_t)n;
    }

    sb3_api_finalize();
    sb3_api_deinit();
    sb3_inited = 0;
    (void)sb3_inited;

    if (bl_verify_image(prt_ota.start, prt_ota.size) == 0)
    {
        flash_arbiter_release(FLASH_OWNER_OTA);
        reply_err(&session, "ERR IMAGE\n");
        mtls_session_close(&session);
        return -1;
    }

    if (bl_update_image_state(0, kSwapType_ReadyForTest) != kStatus_Success)
    {
        flash_arbiter_release(FLASH_OWNER_OTA);
        reply_err(&session, "ERR IMAGE\n");
        mtls_session_close(&session);
        return -1;
    }

    (void)mtls_write_all(&session, "OK\n", 3, MTLS_IO_TIMEOUT_MS);
    g_update_tls_tx_bytes += 3;
    g_update_success_count++;
    PRINTF("Update OK - resetting\r\n");
    vTaskDelay(pdMS_TO_TICKS(UPDATE_OK_FLUSH_MS));
    NVIC_SystemReset();
    return 0; /* unreachable */
}

static void update_task(void *arg)
{
    (void)arg;

    while (diagnostics_update_window_remaining_s() > 0)
    {
        int server = socket(AF_INET, SOCK_STREAM, 0);
        if (server < 0)
        {
            g_update_failure_count++;
            vTaskDelay(pdMS_TO_TICKS(500));
            continue;
        }

        int yes = 1;
        (void)lwip_setsockopt(server, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));

        struct sockaddr_in addr;
        memset(&addr, 0, sizeof(addr));
        addr.sin_family      = AF_INET;
        addr.sin_port        = htons(UPDATE_TCP_PORT);
        addr.sin_addr.s_addr = htonl(INADDR_ANY);

        if (bind(server, (struct sockaddr *)&addr, sizeof(addr)) < 0)
        {
            g_update_failure_count++;
            close_fd(&server);
            vTaskDelay(pdMS_TO_TICKS(500));
            continue;
        }

        if (listen(server, 1) < 0)
        {
            g_update_failure_count++;
            close_fd(&server);
            vTaskDelay(pdMS_TO_TICKS(500));
            continue;
        }

        PRINTF("Update mTLS listening on port %u (window remaining %lus)\r\n", (unsigned)UPDATE_TCP_PORT,
               (unsigned long)diagnostics_update_window_remaining_s());

        while (diagnostics_update_window_remaining_s() > 0)
        {
            struct timeval tv;
            fd_set rfds;
            int sel;

            tv.tv_sec  = 1;
            tv.tv_usec = 0;
            FD_ZERO(&rfds);
            FD_SET(server, &rfds);
            sel = lwip_select(server + 1, &rfds, NULL, NULL, &tv);
            if (sel <= 0)
            {
                continue;
            }

            int client = accept(server, NULL, NULL);
            if (client < 0)
            {
                g_update_failure_count++;
                continue;
            }

            /* Accepted before deadline — session may finish after window closes. */
            g_update_accept_count++;
            PRINTF("Update session accepted\r\n");
            (void)handle_update_session(client);
            close_fd(&client);
        }

        close_fd(&server);
    }

    PRINTF("Update window closed; update task exiting\r\n");
    vTaskDelete(NULL);
}

void update_service_start(void)
{
    if (xTaskCreate(update_task, "update", 4096, NULL, tskIDLE_PRIORITY + 2, NULL) != pdPASS)
    {
        PRINTF("Update task create failed\r\n");
    }
}
