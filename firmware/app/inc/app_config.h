#ifndef APP_CONFIG_H_
#define APP_CONFIG_H_

#ifndef APP_VARIANT
#define APP_VARIANT "V1"
#endif

#ifndef APP_VERSION_STRING
#define APP_VERSION_STRING "1.0.0"
#endif

#ifndef APP_LED_COLOR
#define APP_LED_COLOR GREEN
#endif

#ifndef APP_LED_ON_MS
#define APP_LED_ON_MS 500
#endif

#ifndef APP_LED_OFF_MS
#define APP_LED_OFF_MS 500
#endif

#ifndef APP_HELLO_REPLY
#define APP_HELLO_REPLY "Hello PC!"
#endif

#define HELLO_TCP_PORT   5000
#define UPDATE_TCP_PORT  5555
#define UPDATE_WINDOW_S  180

#define HELLO_MAX_REQ_B  128
#define HELLO_RECV_TO_MS 5000

/* P5 Ethernet SB3 — transport limits (not crypto) */
#define UPDATE_HDR_MAGIC       0x5341544Fu /* 'OTAS' LE */
#define UPDATE_HDR_VERSION     1u
#define UPDATE_HDR_SIZE_B      28u
#define UPDATE_SB3_MAX_B       (0x00100000u + 0x40000u) /* 1 MiB slot + SB3/cmd overhead */
#define UPDATE_CHUNK_B         1024u
#define UPDATE_HDR_RECV_TO_MS  5000
#define UPDATE_STREAM_TO_MS    10000
#define UPDATE_OK_FLUSH_MS     200

#define EXAMPLE_BANNER "MCXN947 Secure OTA prototype"

/* Fleet network policy — override any SDK board network_cfg.h defaults */
#ifndef IP_ADDR
#define IP_ADDR "192.168.2.90"
#endif
#ifndef IP_MASK
#define IP_MASK "255.255.255.0"
#endif
#ifndef GW_ADDR
#define GW_ADDR "192.168.2.24"
#endif

#endif /* APP_CONFIG_H_ */
