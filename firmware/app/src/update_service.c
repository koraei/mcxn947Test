/*
 * P5: TCP :5555 → thin header → raw SB3 stream → NXP sb3_api → ReadyForTest.
 * No TLS/HTTP/JSON/CBOR; crypto stays in SB3 + CUST_MK_SK.
 */
#include "update_service.h"
#include "app_config.h"
#include "diagnostics.h"

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

static void reply_err(int client, const char *msg)
{
    (void)send(client, msg, (int)strlen(msg), 0);
    g_update_failure_count++;
}

static int recv_exact(int fd, uint8_t *buf, size_t need)
{
    size_t got = 0;

    while (got < need)
    {
        int n = recv(fd, (char *)buf + got, (int)(need - got), 0);
        if (n <= 0)
        {
            return -1;
        }
        got += (size_t)n;
    }
    return 0;
}

static void set_recv_timeout_ms(int fd, int ms)
{
    struct timeval tv;
    tv.tv_sec  = ms / 1000;
    tv.tv_usec = (ms % 1000) * 1000;
    (void)lwip_setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
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

    set_recv_timeout_ms(client, UPDATE_HDR_RECV_TO_MS);

    if (recv_exact(client, hdr_raw, UPDATE_HDR_SIZE_B) != 0)
    {
        reply_err(client, "ERR TIMEOUT\n");
        return -1;
    }

    memcpy(&hdr.magic, &hdr_raw[0], 4);
    hdr.version = hdr_raw[4];
    memcpy(hdr.reserved, &hdr_raw[5], 3);
    memcpy(hdr.uuid, &hdr_raw[8], 16);
    memcpy(&hdr.sb3_len, &hdr_raw[24], 4);

    if (hdr.magic != UPDATE_HDR_MAGIC || hdr.version != UPDATE_HDR_VERSION)
    {
        reply_err(client, "ERR MAGIC\n");
        return -1;
    }

    if (memcmp(hdr.uuid, diagnostics_uuid_bytes(), 16) != 0)
    {
        reply_err(client, "ERR UUID\n");
        return -1;
    }

    if (hdr.sb3_len == 0u || hdr.sb3_len > UPDATE_SB3_MAX_B)
    {
        reply_err(client, "ERR LEN\n");
        return -1;
    }

    if (bl_get_update_partition_info(0, &prt_ota) != kStatus_Success)
    {
        reply_err(client, "ERR IMAGE\n");
        return -1;
    }

    PRINTF("Update: SB3 len=%lu inactive@0x%08lX\r\n", (unsigned long)hdr.sb3_len,
           (unsigned long)prt_ota.start);

    if (sb3_api_init() != kStatus_Success)
    {
        g_sb3_failure_count++;
        reply_err(client, "ERR SB3\n");
        return -1;
    }
    sb3_inited = 1;

    set_recv_timeout_ms(client, UPDATE_STREAM_TO_MS);
    remaining = hdr.sb3_len;

    /* First 64 B enough for sb3_parse_header; then stream the rest. */
    {
        uint8_t first[64];
        size_t first_n = remaining < sizeof(first) ? remaining : sizeof(first);

        if (recv_exact(client, first, first_n) != 0)
        {
            g_sb3_failure_count++;
            sb3_api_deinit();
            reply_err(client, "ERR TIMEOUT\n");
            return -1;
        }

        if (!sb3_parse_header(first, &first_sb3_len) || first_sb3_len != hdr.sb3_len)
        {
            g_sb3_failure_count++;
            sb3_api_deinit();
            reply_err(client, "ERR SB3\n");
            return -1;
        }

        st = sb3_api_pump(first, first_n);
        if (st != kStatus_Success)
        {
            g_sb3_failure_count++;
            sb3_api_deinit();
            reply_err(client, "ERR SB3\n");
            return -1;
        }
        remaining -= (uint32_t)first_n;
    }

    while (remaining > 0u)
    {
        size_t want = remaining > UPDATE_CHUNK_B ? UPDATE_CHUNK_B : remaining;
        int n;

        n = recv(client, (char *)chunk, (int)want, 0);
        if (n <= 0)
        {
            g_sb3_failure_count++;
            sb3_api_deinit();
            reply_err(client, "ERR TIMEOUT\n");
            return -1;
        }

        st = sb3_api_pump(chunk, (size_t)n);
        if (st != kStatus_Success)
        {
            g_sb3_failure_count++;
            sb3_api_deinit();
            reply_err(client, "ERR SB3\n");
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
        reply_err(client, "ERR IMAGE\n");
        return -1;
    }

    if (bl_update_image_state(0, kSwapType_ReadyForTest) != kStatus_Success)
    {
        reply_err(client, "ERR IMAGE\n");
        return -1;
    }

    (void)send(client, "OK\n", 3, 0);
    g_update_success_count++;
    PRINTF("Update OK — resetting\r\n");
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

        PRINTF("Update TCP listening on port %u (window remaining %lus)\r\n", (unsigned)UPDATE_TCP_PORT,
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
    if (xTaskCreate(update_task, "update", 3072, NULL, tskIDLE_PRIORITY + 2, NULL) != pdPASS)
    {
        PRINTF("Update task create failed\r\n");
    }
}
