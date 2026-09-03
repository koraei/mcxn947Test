# Ethernet update protocol (P5)

Transport only. Cryptography remains NXP SB3.1 + `CUST_MK_SK`.

## Ports

| Port | Role |
|------|------|
| TCP 5000 | Hello / STATUS (always) |
| TCP 5555 | SB3 update (new sessions only in first 180 s after boot) |

## Request (client → device)

Fixed header (28 bytes, little-endian integers) then raw SB3:

| Offset | Size | Field |
|--------|------|-------|
| 0 | 4 | Magic `OTAS` (`0x53 0x41 0x54 0x4F`) |
| 4 | 1 | Protocol version `1` |
| 5 | 3 | Reserved `0` |
| 8 | 16 | Target UUID (raw silicon ID bytes, same order as STATUS hex pairs) |
| 24 | 4 | `sb3_len` (uint32 LE), max `UPDATE_SB3_MAX_B` (1 MiB slot + 256 KiB overhead) |
| 28 | `sb3_len` | Raw SB3.1 stream (`sbv3…`) |

No TLS, HTTP, JSON, CBOR, or extra hashes.

## Response (device → client)

ASCII line then close (except success path resets):

| Line | Meaning |
|------|---------|
| `OK` | SB3 accepted, image marked ReadyForTest; device resets shortly |
| `ERR MAGIC` | Bad header magic/version |
| `ERR UUID` | UUID mismatch (early reject) |
| `ERR LEN` | Length zero or above max |
| `ERR TIMEOUT` | Idle / incomplete stream |
| `ERR SB3` | NXP `sb3_api_pump` / finalize path failed |
| `ERR IMAGE` | Candidate not visible / mark-ready failed |
| `ERR BUSY` | Reserved (single-session design) |

## Window / session

- New accepts only while `diagnostics_update_window_remaining_s() > 0`.
- A session accepted before the deadline may finish afterward.
- One active update session; listen backlog 1.
- Finite `SO_RCVTIMEO` on header and stream; incomplete clients are closed without marking an image.
