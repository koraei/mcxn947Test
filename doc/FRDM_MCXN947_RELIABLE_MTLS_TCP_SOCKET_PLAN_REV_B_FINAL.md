# FRDM-MCXN947 Reliable mTLS TCP Socket Implementation Plan
## Autonomous Cursor-Agent Execution Plan — Rev B FINAL

**Target:** Existing proven FRDM-MCXN947 project on MCUXpresso SDK 26.06 LTS  
**Board:** DEV-UNIT-01 / static IPv4 `192.168.2.90/24`  
**Frozen security baseline:** NXP ROM ECDSA secure boot → IFR MCUboot → FreeRTOS/lwIP application → per-unit SB3.1 OTA  
**Existing application sockets:** normal TCP `:5000`, update TCP `:5555` (new sessions first 180 s only)  
**Primary objective:** use mutual TLS for **all application TCP communication** while preserving ordinary decrypted application data at both endpoints and maximizing long-duration Ethernet reliability with minimal architectural change.  
**Status:** final implementation authority for the mTLS phase.

---

# 0. Final architecture decision

The product remains a **TCP socket application**. Do not introduce HTTP, HTTPS, REST, WebSocket, MQTT, or another application protocol.

mTLS is only a security layer between the existing TCP socket and the existing application protocol.

```text
PC application
    |
    | plaintext application data
    v
PC TLS library
    |
    | encrypted/authenticated TLS records on Ethernet
    v
lwIP TCP/IP / Ethernet
    |
    | encrypted/authenticated TLS records
    v
MCXN947 mbedTLS
    |
    | plaintext application data
    v
FreeRTOS application
```

Therefore both endpoints can see and process the original decrypted message.

For the existing echo/Hello proof:

```text
PC application:
    sends plaintext "Hello MCXN"
        ↓
Python TLS encrypts it
        ↓
Ethernet carries ciphertext
        ↓
MCXN947 mbedTLS decrypts it
        ↓
MCU application receives plaintext "Hello MCXN"

MCU application:
    creates plaintext "Hello PC!"
        ↓
mbedTLS encrypts it
        ↓
Ethernet carries ciphertext
        ↓
Python TLS decrypts it
        ↓
PC application receives plaintext "Hello PC!"
```

**No application-layer encryption/decryption is added.** The application reads/writes plaintext through TLS APIs.

---

# 1. Security responsibilities stay separated

The already proven boot/update architecture is frozen.

| Layer | Responsibility |
|---|---|
| NXP ROM secure boot | authenticates MCUboot |
| MCUboot | authenticates executable application |
| SB3.1 + unique per-unit `CUST_MK_SK` | encrypts/authenticates and unit-binds firmware update packages |
| mTLS | authenticates PC ↔ MCU and encrypts Ethernet communication in transit |
| Existing socket protocols | application framing only |

SB3.1 remains mandatory for firmware updates even after mTLS is enabled.

mTLS must not modify:

- ROM secure boot;
- IFR MCUboot layout;
- CMPA/CFPA;
- `CUST_MK_SK`;
- SB3 format or processing;
- OTAS 28-byte header;
- A/B slot layout or flash remap;
- 180-second update-window policy.

---

# 2. Scope — implement only what is required

Mandatory scope:

1. Reuse NXP MCUXpresso SDK **26.06 LTS** FreeRTOS + lwIP + mbedTLS 3.x integration.
2. Prove NXP's stock FRDM-MCXN947 `lwip_httpssrv_mbedTLS_freertos` example first, but use it **only as an integration reference**.
3. Keep the product's socket API architecture.
4. Add a small common TLS layer around accepted lwIP TCP sockets.
5. Convert normal communication port `5000` to **mTLS-only**.
6. Convert update port `5555` to **mTLS-only** while preserving its 180-second listener.
7. Use one simple private development CA.
8. Give DEV-UNIT-01 one device/server certificate and private key.
9. Give the authorized PC/updater one client certificate and private key.
10. Require mutual certificate authentication.
11. Update the Python host CLI so all communication uses TLS by default.
12. Demonstrate decrypted messages at both application endpoints while proving the Ethernet payload is not plaintext.
13. Perform bounded reliability/resource qualification focused on long-running TCP/mTLS operation.
14. Freeze the result after qualification.

---

# 3. Explicit non-goals

Do not implement these unless a measured failure makes one necessary:

- HTTP/HTTPS in the product;
- MQTT/WebSocket/REST;
- TLS as a replacement for SB3;
- TLS session tickets/resumption;
- TLS 0-RTT;
- ALPN or SNI;
- CRL or OCSP;
- online certificate service;
- EdgeLock 2GO;
- NPX/PRINCE;
- TrustZone/TF-M migration;
- lifecycle closing;
- debug locking/authentication;
- new monotonic counters;
- certificate renewal protocol;
- NTP/SNTP solely for TLS;
- custom cryptography;
- custom X.509 parser;
- custom TLS record layer;
- custom memory allocator unless resource tests show a real heap problem;
- ELS opaque TLS-key provisioning during the first implementation;
- multiple simultaneous PC clients;
- dynamic certificate enrollment.

The target system currently has one MCU and one authorized PC peer. Optimize for that architecture.

---

# 4. NXP baseline the agent must reuse

## 4.1 SDK lock

Use the already frozen:

```text
MCUXpresso SDK: 26.06.00 LTS
FreeRTOS:       SDK-provided
lwIP:           SDK-provided
mbedTLS:        SDK-provided 3.x
Board:          frdmmcxn947
```

Do not update middleware independently during this work.

## 4.2 Primary NXP reference

Inspect, build, and run:

```text
examples/lwip_examples/lwip_httpssrv_mbedTLS/freertos
```

with its FRDM-MCXN947 board configuration.

The purpose is to establish the exact NXP-supported combination of:

```text
FRDM-MCXN947
 + FreeRTOS
 + lwIP
 + mbedTLS 3.x
 + Ethernet
```

Reuse from the stock example only what is relevant:

- required SDK/Kconfig components;
- mbedTLS 3.x configuration;
- PSA/RNG/entropy initialization;
- certificate/key parsing patterns;
- Ethernet/lwIP configuration dependencies;
- RAM/stack/linker requirements.

Do **not** copy:

- HTTP server;
- web pages;
- CGI/SSI;
- HTTP parser;
- browser-specific logic.

## 4.3 Product TLS integration method

The product already has reliable lwIP sockets. Preserve them.

Preferred architecture:

```text
lwIP socket accept()
       ↓
mbedTLS SSL context
       ↓
small BIO callbacks around lwIP recv()/send()
       ↓
mbedtls_ssl_read()/mbedtls_ssl_write()
       ↓
existing application parser
```

The application shall never call raw `recv()`/`send()` for a connection that has become TLS-enabled.

Do not migrate the product to lwIP raw callbacks or NXP HTTPS/ALTCP framework solely to obtain TLS.

If the installed SDK exposes a smaller NXP-supported socket-oriented helper that exactly fits this architecture, it may be reused after documenting it. Otherwise use standard mbedTLS SSL APIs with NXP's SDK configuration.

**Never patch SDK lwIP or mbedTLS source files.**

## 4.4 Board Ethernet prerequisite

Keep the already proven board configuration:

```text
JP13 = 2-3
R274 populated
static IPv4 = 192.168.2.90/24
```

Do not reopen PHY/pinmux/reference-clock work unless the proven Ethernet baseline regresses.

---

# 5. Final socket architecture

```text
                               PC
                    authorized client certificate
                               |
         +---------------------+---------------------+
         |                                           |
  mTLS normal socket                             mTLS OTA socket
      TCP :5000                                     TCP :5555
         |                                      first 180 s only
         |                                           |
         v                                           v
+------------------------------------------------------------------+
|                         MCXN947                                  |
|                                                                  |
| FreeRTOS + lwIP + mbedTLS                                        |
|                                                                  |
| normal_comm_task                         update_service_task      |
|       |                                         |                 |
|  mTLS session                              mTLS session           |
|       |                                         |                 |
| plaintext app data                         OTAS header            |
|       |                                         |                 |
| Hello / future DAQ protocol                raw SB3 stream         |
|                                                 |                 |
|                                             NXP sb3_api           |
+------------------------------------------------------------------+
```

### Rules

- `:5000` is always available while Ethernet is healthy.
- `:5555` accepts new TCP/TLS sessions only during the first 180 seconds.
- One active client per service.
- No plaintext fallback.
- Both services use the same device certificate/CA configuration in the initial implementation.
- The same authorized PC client certificate may be used for both services initially.
- TLS failure affects only that connection, never the DAQ/control tasks.

---

# 6. Plaintext boundary — mandatory design rule

The user/application must be able to see the real message at each endpoint.

MCU code conceptually becomes:

```c
/* socket already accepted and mTLS handshake passed */
n = mtls_read(session, rx_buf, sizeof(rx_buf));   /* returns decrypted plaintext */

if (message_is_hello(rx_buf, n))
{
    const char reply[] = "Hello PC!\n";
    mtls_write(session, reply, sizeof(reply) - 1); /* encrypts transparently */
}
```

Host conceptually becomes:

```python
with tls_socket:
    tls_socket.sendall(b"Hello MCXN\n")   # Python SSL encrypts on wire
    reply = tls_socket.recv(64)           # returns decrypted plaintext
    assert reply == b"Hello PC!\n"
```

Application logs may show:

```text
RX plaintext: Hello MCXN
TX plaintext: Hello PC!
```

for development evidence.

Production logging should not automatically dump arbitrary application payloads.

---

# 7. PKI — deliberately simple

## 7.1 Algorithms

Use:

- ECDSA P-256;
- SHA-256;
- X.509 v3;
- TLS >= 1.2;
- prefer ECDHE-ECDSA with AES-GCM when negotiated by the existing NXP configuration.

Do not spend implementation time aggressively pruning cipher suites unless memory or security evidence requires it.

Record the negotiated TLS version and cipher during tests.

## 7.2 Development PKI

Use:

```text
MCXN Development Root CA
        |
        +-- DEV-UNIT-01 server certificate
        |
        +-- DEV-PC-01 client certificate
```

Device certificate:

- unique to DEV-UNIT-01;
- ECDSA P-256;
- serverAuth EKU;
- UUID included in subject or SAN;
- public certificate fingerprint recorded in unit registry.

PC certificate:

- unique to the authorized development PC/operator credential;
- ECDSA P-256;
- clientAuth EKU.

Do not add intermediate CAs.

## 7.3 Peer verification

### MCU verifies PC

Mandatory:

- client certificate must be present;
- chain must validate against the private project CA;
- verification result must otherwise be acceptable.

If the MCU has no trusted wall clock, do not add NTP solely for this phase. Document the exact mbedTLS time behavior. If certificate time flags are the only unavoidable verification flags due to absent trusted time, handle that narrowly and explicitly; do not ignore signature, CA, key-usage, or identity failures.

### PC verifies MCU

Mandatory:

1. validate server certificate chain against project CA;
2. compare exact SHA-256 device-certificate fingerprint with the expected fingerprint in `units/DEV-UNIT-01.json`.

The fingerprint check gives strong device identity even though the lab uses a static IP and avoids unnecessary DNS/SAN infrastructure.

## 7.4 Key storage for this phase

Keep private material outside Git:

```text
C:\mcxn-secrets\mtls\
  ca\
  pcs\DEV-PC-01\
  units\DEV-UNIT-01\
```

The initial MCU device TLS private key may be compiled into the signed application from an ignored generated build object.

This is acceptable for this phase because:

- application authenticity is already protected by ROM + MCUboot;
- the board remains in Develop/debug-open state anyway;
- the objective is reliable mTLS integration.

**Do not add ELS opaque-key provisioning now.**

NXP's PSA/opaque-key capability remains a future hardening option after the socket layer is frozen.

---

# 8. Common TLS module

Create one small reusable product module, for example:

```text
src/security/mtls_socket.c
src/security/mtls_socket.h
```

Responsibilities:

- one-time PSA/mbedTLS initialization;
- parse CA certificate;
- parse own server certificate/private key;
- create immutable/common server TLS configuration;
- initialize/reset a per-connection SSL context;
- perform bounded server handshake;
- read decrypted application bytes;
- write plaintext application bytes;
- perform orderly TLS close when possible;
- force-close on socket/link fault;
- free/reset all per-session resources;
- expose verification/counter diagnostics.

Illustrative interface:

```c
int mtls_global_init(void);

int mtls_session_open(
    mtls_session_t *session,
    int socket_fd,
    uint32_t handshake_timeout_ms);

int mtls_read(
    mtls_session_t *session,
    void *buf,
    size_t max_len,
    uint32_t timeout_ms);

int mtls_read_exact(
    mtls_session_t *session,
    void *buf,
    size_t len,
    uint32_t timeout_ms);

int mtls_write_all(
    mtls_session_t *session,
    const void *buf,
    size_t len,
    uint32_t timeout_ms);

void mtls_session_close(mtls_session_t *session);
```

Exact names may follow the existing codebase.

### Reliability rule

Initialize certificate/key/config objects **once**, not for every packet.

Create/reset session state per TCP connection.

Do not allocate memory proportional to message or SB3 size.

Do not create/delete FreeRTOS tasks per message.

---

# 9. Normal communication service `:5000`

This is the always-on reliability-critical path.

## 9.1 Task model

Keep one long-lived FreeRTOS normal-communication server task.

Conceptually:

```text
LISTEN
  ↓
accept TCP
  ↓
mTLS handshake
  ↓
CONNECTED
  ↓
read decrypted message
  ↓
process
  ↓
write plaintext reply through mTLS
  ↓
continue
  ↓
socket/TLS/link error
  ↓
close/reset session
  ↓
LISTEN
```

Do not reboot the MCU on a normal network/TLS failure.

## 9.2 Hello proof

After conversion:

```text
PC plaintext:  "Hello MCXN\n"
MCU plaintext: "Hello MCXN\n"

MCU plaintext: "Hello PC!\n"
PC plaintext:  "Hello PC!\n"
```

Plain raw TCP to port 5000 must no longer work after final qualification.

## 9.3 Future DAQ use

The same session can later carry the actual DAQ application protocol.

Do not create a second TLS framework for DAQ.

The current Hello service is the proof vehicle for the future normal encrypted socket.

---

# 10. Update service `:5555`

Preserve the proven implementation.

Only insert mTLS:

```text
TCP accept
   ↓
mTLS handshake
   ↓
existing 28-byte OTAS header
   ↓
existing raw SB3 stream
   ↓
NXP sb3_api
```

No OTAS or SB3 changes.

## 10.1 180-second semantics

Definitions:

```text
T0 = application startup
Tclose = T0 + 180 seconds
```

Rules:

1. no new listener accepts after `Tclose`;
2. a raw TCP connection is not yet an authorized update session;
3. TLS handshake has finite timeout;
4. successful mTLS authentication is required before OTAS parsing;
5. OTAS UUID/length validation follows TLS;
6. a valid authenticated update session that started before the deadline may finish after 180 s;
7. idle/malformed TLS clients cannot keep the service open indefinitely;
8. at 180 s close the listening socket;
9. an already authenticated update session may continue;
10. after update service closes, normal mTLS `:5000` remains fully operational.

---

# 11. Timeout and failure policy

No infinite network blocking.

Start with measured, conservative values:

```text
TLS handshake timeout:       5 s
normal socket RX timeout:    application-dependent, finite
normal socket TX timeout:    finite
update socket RX timeout:    finite
update TLS close timeout:    short/bounded
```

Exact values are tuned only after hardware evidence.

On any failure:

```text
certificate failure
TLS protocol failure
peer close
TCP reset
receive timeout
send timeout
cable disconnect
```

the owning connection state machine must:

1. stop using the session;
2. close/free/reset TLS state;
3. close the TCP socket;
4. return to LISTEN/recovery state;
5. leave DAQ/control processing untouched.

No TLS/network fault may modify:

- CMPA;
- CFPA;
- `CUST_MK_SK`;
- MCUboot;
- active image state;
- ReadyForTest state unless SB3 completed successfully.

---

# 12. Resource/reliability rules

Because 24/7 reliability matters more than peak throughput:

- one normal client maximum;
- one update client maximum;
- no unbounded queues;
- fixed application RX/TX buffers;
- bounded TLS records;
- finite timeouts;
- no application heap allocation per message;
- no task creation/deletion per packet;
- acquisition/control tasks must never block on Ethernet;
- TLS session cleanup must be deterministic;
- reconnect is a normal state, not an exception;
- use existing NXP FreeRTOS/lwIP network recovery behavior;
- avoid middleware patches.

Do not introduce `MBEDTLS_MEMORY_BUFFER_ALLOC_C` or a custom TLS heap unless repeated-session tests show real fragmentation/leak behavior with the NXP default allocator.

---

# 13. Instrumentation

Add low-cost counters, compiled into development/qualification builds:

```text
net_link_down_count
tcp_accept_count
tcp_disconnect_count
tcp_error_count

mtls_handshake_ok
mtls_handshake_fail
mtls_verify_fail
mtls_timeout
mtls_peer_close
mtls_session_abort

normal_tls_rx_bytes
normal_tls_tx_bytes

update_tls_rx_bytes
update_tls_tx_bytes

normal_task_stack_min_free
update_task_stack_min_free
heap_min_free
```

Where available without invasive changes, also record lwIP pbuf/memp high-water or error statistics.

Counters must saturate or use a sufficiently wide type.

Do not continuously log every packet.

---

# 14. PC implementation

Use Python's standard `ssl` library for the host side.

Do not add another TLS library unless the standard library cannot meet a proven requirement.

## 14.1 `mcxn hello`

Existing command becomes mTLS-only:

```text
python tools/mcxn.py hello
```

Internally:

```text
load CA
load DEV-PC-01 client cert/key
connect 192.168.2.90:5000
TLS handshake
verify server chain
verify registered server fingerprint
send plaintext "Hello MCXN\n"
receive decrypted "Hello PC!\n"
report PASS
```

No separate permanent `hello-tls` command.

## 14.2 `mcxn update`

Keep the existing interface:

```text
python tools/mcxn.py update --sb3 <path>
```

Internally:

```text
manifest/unit preflight
  ↓
connect :5555
  ↓
mTLS handshake
  ↓
server CA + fingerprint verification
  ↓
existing OTAS header
  ↓
existing raw SB3
  ↓
existing result/reboot/version verification
```

No plaintext fallback.

## 14.3 Host credentials

Use ignored configuration/environment paths such as:

```text
mtls.ca_cert
mtls.client_cert
mtls.client_key
```

Never place client private credentials in firmware `dist/` automatically.

---

# 15. Execution phases

Execute **M0 → M4** only.

---

## M0 — Baseline freeze and NXP stock TLS proof

### Goal

Prove the NXP-supported TLS stack on this exact board before product integration.

### Tasks

1. Tag/record the current P7-complete product baseline.
2. Record current app flash/RAM map, FreeRTOS heap minimum and relevant task stack high-water values.
3. Inspect the SDK 26.06 FRDM-MCXN947 `lwip_httpssrv_mbedTLS_freertos` example.
4. Record its:
   - Kconfig/config files;
   - mbedTLS components;
   - PSA/RNG initialization;
   - certificate/key loading;
   - lwIP dependencies;
   - memory footprint.
5. Build it unchanged.
6. Flash/run it on the already proven Ethernet hardware.
7. Adapt only static IP to `192.168.2.90` if necessary for lab testing.
8. Complete a PC TLS connection.
9. Record negotiated TLS version/cipher.
10. Restore the frozen product firmware.

### Acceptance

- NXP TLS example works on FRDM-MCXN947;
- TLS >=1.2;
- no MCU security state changes;
- evidence written.

If the NXP example fails, diagnose the NXP baseline before modifying product code.

---

## M1 — Minimal PKI and common TLS wrapper

### Goal

Build the reusable mTLS foundation without changing product protocols.

### Tasks

1. Create one development root CA.
2. Create DEV-UNIT-01 ECDSA-P256 server cert/key.
3. Create DEV-PC-01 ECDSA-P256 client cert/key.
4. Store secrets only under `C:\mcxn-secrets\mtls`.
5. Store only public fingerprints/metadata in unit registry.
6. Add ignored build-time credential generator/injection.
7. Add mbedTLS components/config copied conceptually from M0.
8. Implement common `mtls_socket` module.
9. Add a temporary self-test path if needed to verify server/client handshake before touching existing services.
10. Remove the temporary path after proof.

### Acceptance

- mutual handshake works on board;
- MCU requires client certificate;
- PC validates server CA and fingerprint;
- secrets not tracked;
- no PFR/security writes.

---

## M2 — Convert normal socket `:5000` to mTLS

### Goal

Prove long-lived encrypted/authenticated TCP application communication with visible plaintext at both endpoints.

### Tasks

1. Wrap accepted `:5000` socket in mTLS.
2. Keep existing Hello parser unchanged after the TLS boundary.
3. Convert `mcxn hello` to Python TLS.
4. Remove plaintext normal-service fallback.
5. Add concise session counters.
6. Verify reconnect after client close/reset.
7. Verify server returns to listening after invalid certificate or failed handshake.

### Mandatory tests

| Test | Expected |
|---|---|
| valid PC certificate | TLS PASS |
| `Hello MCXN` through TLS | MCU sees decrypted plaintext |
| MCU `Hello PC!` through TLS | PC sees decrypted plaintext |
| raw plaintext TCP attempt | rejected |
| no client certificate | handshake rejected |
| wrong-CA client | handshake rejected |
| wrong server fingerprint at PC | PC rejects MCU |
| client abrupt close | server recovers to LISTEN |
| repeated reconnect | no reboot or resource trend |

### On-wire evidence

Capture one Wireshark trace:

- packet capture must not contain literal `Hello MCXN` or `Hello PC!`;
- MCU/PC endpoint logs/tests must show those plaintext strings.

This demonstrates the exact required property: plaintext at endpoints, ciphertext on Ethernet.

---

## M3 — Convert update socket `:5555` to mTLS

### Goal

Protect the existing secure updater without modifying it.

### Tasks

1. Wrap accepted update connection in the same common TLS layer.
2. Require successful mutual TLS before reading the OTAS header.
3. Feed decrypted TLS bytes into the existing OTAS/SB3 stream.
4. Convert `mcxn update` to TLS using the same host credential set.
5. Preserve the 180-second policy exactly.
6. Remove plaintext update fallback.

### Mandatory tests

| Test | Expected |
|---|---|
| valid mTLS + correct unit SB3 | update PASS |
| valid mTLS + wrong-key SB3 | `ERR SB3`, current firmware safe |
| valid mTLS + corrupt/truncated SB3 | safe failure |
| no/wrong client certificate | fails before OTAS |
| raw plaintext OTAS | TLS rejection |
| after 180 s | no update listener |
| connection ~175 s, auth+valid update | may finish after deadline |
| idle TLS handshake | bounded timeout |
| update failure | normal mTLS `:5000` remains healthy |

No changes to CMPA/CFPA/CUST_MK_SK/MCUboot.

---

## M4 — Reliability qualification and freeze

### Goal

Qualify the socket/TLS architecture for continuous industrial use without turning this into a certification program.

### A. Resource baseline

Measure before/after mTLS:

- application flash;
- static RAM;
- FreeRTOS heap minimum;
- TLS/normal/update task stack high-water;
- handshake time;
- reconnect time;
- CPU load if existing instrumentation makes it easy.

### B. Normal-socket reliability tests

Run:

1. **24-hour continuous mTLS socket soak** at the intended application traffic rate.
   - For current requirement, exercise approximately **100 KB/s aggregate** or the closest representative framed traffic.
   - PC verifies sequence numbers/payload content.
   - MCU echoes/acknowledges according to test harness; production protocol need not be changed.
2. **1,000 automated connect → mTLS handshake → message exchange → close/reconnect cycles**.
3. **100 unauthorized certificate handshake attempts**.
4. **50 abrupt PC socket aborts** during active traffic.
5. **20 physical/link-layer disconnect/reconnect cycles** or equivalent controlled NIC/link interruption.
6. Restart the PC test process repeatedly while MCU stays running.
7. Verify the MCU never requires reset to recover networking.

### C. Update-path regression

After normal-socket stress:

1. reboot into update window;
2. perform one correct mTLS + SB3 update;
3. perform one wrong-key/corrupt negative update;
4. verify final normal mTLS communication.

### D. Leak/health criteria

After warm-up and stress:

- no progressive downward trend in minimum-free heap;
- stack margins remain stable;
- no growth in active sockets/pbufs/session objects;
- no orphaned task;
- no watchdog reset;
- no hard fault;
- no network-stack restart unless caused by an intentionally tested link recovery policy;
- DAQ/control task deadlines remain unaffected.

If there is a measurable resource trend, diagnose exact ownership/cleanup first. Do not immediately introduce a custom allocator or new network framework.

### Final freeze

When M4 passes:

- update security/network architecture docs;
- update toolchain lock;
- update reuse-map;
- update operator/technician runbooks;
- store mTLS test evidence;
- tag the qualified baseline;
- stop.

Do not automatically continue into opaque ELS keys, TLS credential rotation, or additional network protocols.

---

# 16. Recommended FreeRTOS priority relationship

Do not make networking able to starve acquisition/control.

Conceptually:

```text
watchdog/safety supervision        high
time-critical DAQ/acquisition      high
DAQ processing                     high/normal
lwIP tcpip thread                  NXP-recommended priority
normal mTLS communication task     normal
update mTLS task                   normal/low (only first 180 s)
logging/diagnostics                low
```

Do not change NXP lwIP internal priorities casually.

Use bounded queues between DAQ and networking so a slow/broken PC cannot block acquisition.

---

# 17. Error semantics

Normal socket:

```text
TLS/client/network fault
    ↓
close only that session
    ↓
return to LISTEN
    ↓
DAQ continues
```

Update socket:

```text
TLS failure
    ↓
SB3 never starts
    ↓
close session
    ↓
listener remains if within 180 s
```

Authenticated but invalid package:

```text
mTLS PASS
    ↓
OTAS/SB3
    ↓
SB3 FAIL
    ↓
current valid firmware remains bootable
```

These failure classes must remain distinguishable in counters/evidence.

---

# 18. Expected code delta

Keep the product changes small.

Expected approximate delta:

```text
src/security/mtls_socket.c/.h          250–450 lines
normal service adaptation               50–120 lines
update service adaptation               40–100 lines
host Python TLS changes                150–250 lines
PKI/build scripts                       small
tests                                   as needed
```

These are not quotas. If the agent is adding thousands of lines or importing an HTTPS framework, stop and review.

---

# 19. Autonomous-agent safety rules

The mTLS work requires **no irreversible MCU security write**.

Allowed autonomously:

- build/flash signed normal apps through existing proven process;
- create development X.509 credentials;
- modify application and host networking code;
- run TLS/socket/SB3 tests;
- capture network traces;
- update documentation.

Stop for approval before:

- CMPA/CFPA/PFR write;
- CUST_MK_SK reprovision;
- IFR/security-root changes;
- lifecycle changes;
- debug lock/authentication;
- NPX;
- ELS persistent/opaque TLS-key provisioning;
- EdgeLock 2GO.

If basic mTLS appears to require any of these, the agent must stop because the architecture has drifted.

---

# 20. Definition of done

```text
[ ] P7 frozen secure boot/SB3 architecture unchanged
[ ] NXP stock FRDM-MCXN947 FreeRTOS/lwIP/mbedTLS example proven
[ ] simple development CA created
[ ] DEV-UNIT-01 server credential created
[ ] DEV-PC-01 client credential created
[ ] private keys remain outside Git
[ ] common mTLS socket wrapper implemented
[ ] :5000 is mTLS-only
[ ] PC and MCU both see decrypted Hello application messages
[ ] Wireshark does not expose Hello plaintext
[ ] invalid/no client cert rejected
[ ] PC rejects wrong server fingerprint
[ ] :5555 is mTLS-only
[ ] OTAS and SB3 formats unchanged
[ ] correct mTLS + SB3 update passes
[ ] wrong-key/corrupt SB3 still fails safely
[ ] 180-second update-window semantics unchanged
[ ] no plaintext fallback remains
[ ] normal communication recovers from peer/cable faults without MCU reset
[ ] 24-hour representative traffic soak passes
[ ] 1,000 reconnect cycles pass
[ ] heap/stack/socket resources show no progressive degradation
[ ] final mTLS + SB3 regression passes after stress
[ ] documentation/evidence updated
[ ] qualified baseline tagged/frozen
```

---

# 21. Source/reference set the agent must consult

Use the installed SDK 26.06 LTS as primary authority.

Relevant official NXP material includes:

- FRDM-MCXN947 board SDK documentation;
- `lwip_httpssrv_mbedTLS_freertos` example and board overlay;
- MCUXpresso SDK mbedTLS 3.x middleware documentation;
- MCUXpresso SDK lwIP integration;
- NXP PSA Crypto driver/examples;
- `psa_crypto_opaque_key_examples` only as a future-hardening reference;
- existing project's P3–P7 evidence and frozen security documents.

If current installed SDK files contradict this plan, preserve the frozen product architecture, document the exact discrepancy, and choose the smallest NXP-supported correction.

---

# 22. Final implementation principle

The final product networking model shall be:

```text
application plaintext
      ↕
mTLS
      ↕
TCP/IP
      ↕
Ethernet ciphertext
```

not:

```text
application
  + custom encryption
  + TLS
  + HTTP
  + another protocol
```

For this product, **reliability comes from a small number of layers, bounded blocking, deterministic cleanup, reconnect-by-design, and using NXP's supported FreeRTOS/lwIP/mbedTLS stack without unnecessary framework changes.**
