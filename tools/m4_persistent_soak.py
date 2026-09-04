"""M4 persistent mTLS soak — long-lived session on QA :5001 stream.

Requires firmware built with APP_QA_STREAM=1.
Frame 1024 B: seq(u32 LE) | magic 0x4D345331 | payload[1016].
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from mcxn_lib import fetch_hello, fetch_status, load_cfg, load_unit  # noqa: E402
from mcxn_lib.mtls import connect_mtls  # noqa: E402

FRAME = 1024
HDR = 8
PAYLOAD = FRAME - HDR
MAGIC = 0x4D345331
PORT = 5001


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fill(seq: int) -> bytes:
    body = bytearray(PAYLOAD)
    for i in range(PAYLOAD):
        body[i] = (seq + i) & 0xFF
    return struct.pack("<II", seq & 0xFFFFFFFF, MAGIC) + bytes(body)


def _verify(frame: bytes, expect_seq: int) -> bool:
    if len(frame) != FRAME:
        return False
    seq, magic = struct.unpack_from("<II", frame, 0)
    if seq != (expect_seq & 0xFFFFFFFF) or magic != MAGIC:
        return False
    for i in range(PAYLOAD):
        if frame[HDR + i] != ((expect_seq + i) & 0xFF):
            return False
    return True


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=float, default=24.0)
    p.add_argument("--kbps", type=float, default=100.0, help="Target total app payload KB/s (TX+RX echo)")
    p.add_argument("--logdir", type=Path, default=Path(r"C:\mcxn\builds\m4_persistent_soak"))
    p.add_argument("--port", type=int, default=PORT)
    args = p.parse_args()

    cfg = load_cfg()
    unit = load_unit(cfg["unit_name"])
    args.logdir.mkdir(parents=True, exist_ok=True)

    # Echo: each TX frame produces one RX frame → total app bytes = 2 * TX.
    # Target total kbps ⇒ TX rate = kbps/2.
    tx_bps = (args.kbps * 1000.0) / 2.0
    interval = FRAME / tx_bps if tx_bps > 0 else 0.01

    stats = {
        "tx_bytes": 0,
        "rx_bytes": 0,
        "blocks_tx": 0,
        "blocks_rx": 0,
        "verify_fail": 0,
        "tls_err": 0,
        "disconnects": 0,
        "reconnects": 0,
        "handshake_fail": 0,
        "hello_ok_checks": 0,
        "hello_fail_checks": 0,
    }

    stop_at = time.time() + args.hours * 3600.0
    t0 = time.time()
    seq = 0
    live = args.logdir / "soak_live.json"

    print(
        f"persistent soak hours={args.hours} target_total_kbps={args.kbps} "
        f"tx_interval_s={interval:.4f} port={args.port}",
        flush=True,
    )

    while time.time() < stop_at:
        try:
            stats["reconnects"] += 1
            s = connect_mtls(cfg, args.port, timeout=20, unit=unit)
            s.settimeout(10)
            print(f"session open reconnects={stats['reconnects']}", flush=True)
            next_send = time.time()
            while time.time() < stop_at:
                now = time.time()
                if now < next_send:
                    time.sleep(min(0.002, next_send - now))
                    continue
                next_send = time.time() + interval
                frame = _fill(seq)
                try:
                    s.sendall(frame)
                except OSError as e:
                    stats["tls_err"] += 1
                    stats["disconnects"] += 1
                    print(f"TX disconnect: {e}", flush=True)
                    break
                stats["tx_bytes"] += FRAME
                stats["blocks_tx"] += 1

                try:
                    buf = b""
                    while len(buf) < FRAME:
                        chunk = s.recv(FRAME - len(buf))
                        if not chunk:
                            raise OSError("peer closed")
                        buf += chunk
                except OSError as e:
                    stats["tls_err"] += 1
                    stats["disconnects"] += 1
                    print(f"RX disconnect: {e}", flush=True)
                    break
                stats["rx_bytes"] += FRAME
                stats["blocks_rx"] += 1
                if not _verify(buf, seq):
                    stats["verify_fail"] += 1
                    print(f"VERIFY FAIL seq={seq}", flush=True)
                    break
                seq += 1

                if seq % 500 == 0:
                    elapsed = time.time() - t0
                    total_bps = (stats["tx_bytes"] + stats["rx_bytes"]) / max(elapsed, 1)
                    snap = {
                        **stats,
                        "ts": _utc(),
                        "elapsed_s": round(elapsed, 1),
                        "hours_left": round((stop_at - time.time()) / 3600, 3),
                        "app_bps": round(total_bps, 1),
                        "seq": seq,
                    }
                    live.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
                    print(
                        f"soak t={elapsed:.0f}s seq={seq} ok_tx={stats['blocks_tx']} "
                        f"vfail={stats['verify_fail']} disc={stats['disconnects']} "
                        f"bps={total_bps:.0f}",
                        flush=True,
                    )
                # Periodic :5000 Hello only every ~5 min — may fail while a second
                # mTLS session is open (QA dual-session limit); stream remains primary.
                if seq > 0 and seq % 15000 == 0:
                    try:
                        h = fetch_hello(cfg)
                        if "Hello PC!" in h:
                            stats["hello_ok_checks"] += 1
                        else:
                            stats["hello_fail_checks"] += 1
                        print(f"hello_check: {h!r}", flush=True)
                    except OSError as e:
                        stats["hello_fail_checks"] += 1
                        print(f"hello_check FAIL (concurrent?): {e}", flush=True)
            try:
                s.close()
            except OSError:
                pass
        except Exception as e:
            stats["handshake_fail"] += 1
            stats["disconnects"] += 1
            print(f"handshake/session fail: {type(e).__name__}: {e}", flush=True)
            time.sleep(1.0)

    elapsed = time.time() - t0
    try:
        st = fetch_status(cfg)
        hello = fetch_hello(cfg)
    except OSError as e:
        st = None
        hello = str(e)
    final = {
        **stats,
        "ts": _utc(),
        "hours": args.hours,
        "elapsed_s": round(elapsed, 1),
        "app_bps": round((stats["tx_bytes"] + stats["rx_bytes"]) / max(elapsed, 1), 1),
        "end_hello": hello if isinstance(hello, str) else hello,
        "end_status": st.raw.strip() if st else None,
        "pass": stats["verify_fail"] == 0
        and stats["blocks_tx"] > 0
        and (isinstance(hello, str) and "Hello PC!" in hello),
    }
    (args.logdir / "soak_final.json").write_text(json.dumps(final, indent=2) + "\n", encoding="utf-8")
    print("SOAK_FINAL", json.dumps(final, indent=2), flush=True)
    return 0 if final["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
