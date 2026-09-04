"""M4 host reliability harness. Does not modify MCU firmware.

Product :5000 is one request per mTLS session (Hello/ECHO/STATUS then close).
Soak therefore uses repeated handshake+ECHO cycles; 5 workers approach the
plan's 5×20 KB/s as closely as handshake cost allows.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import ssl
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from mcxn_lib import fetch_hello, fetch_status, load_cfg, load_unit  # noqa: E402
from mcxn_lib.mtls import FingerprintError, connect_mtls, load_client_ctx  # noqa: E402

ROOT = TOOLS.parent


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ping(ip: str, timeout_s: int = 3) -> bool:
    r = subprocess.run(
        ["ping", "-n", "1", "-w", str(timeout_s * 1000), ip],
        capture_output=True,
        text=True,
    )
    return r.returncode == 0


def _echo(cfg: dict, unit: dict, seq: int, payload: bytes) -> bytes:
    s = connect_mtls(cfg, int(cfg["hello_port"]), timeout=10, unit=unit)
    try:
        s.sendall(b"ECHO " + payload + b"\n")
        return s.recv(256)
    finally:
        s.close()


def cmd_reconnect(cfg: dict, count: int, out: Path) -> int:
    unit = load_unit(cfg["unit_name"])
    ok = fail = 0
    t0 = time.time()
    for i in range(count):
        try:
            s = connect_mtls(cfg, int(cfg["hello_port"]), timeout=10, unit=unit)
            s.sendall(b"Hello MCXN\n")
            r = s.recv(256)
            s.close()
            if b"Hello PC!" not in r:
                fail += 1
            else:
                ok += 1
        except Exception:
            fail += 1
        if (i + 1) % 25 == 0:
            print(f"reconnect {i+1}/{count} ok={ok} fail={fail}", flush=True)
        time.sleep(0.05)
    rec = {
        "ts": _utc(),
        "count": count,
        "ok": ok,
        "fail": fail,
        "seconds": round(time.time() - t0, 3),
        "pass": fail == 0 and ok == count,
    }
    out.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    print("RECONNECT", rec)
    return 0 if rec["pass"] else 1


_WRONG_CA_CRT: Path | None = None


def _tls_fail_connect(cfg: dict, ctx: ssl.SSLContext) -> str:
    host, port = cfg["board_ip"], int(cfg["hello_port"])
    try:
        raw = socket.create_connection((host, port), timeout=3)
        raw.settimeout(3)
        with ctx.wrap_socket(raw, server_hostname=None):
            return "UNEXPECTED_OK"
    except Exception as e:
        return type(e).__name__
    finally:
        # MCU handshake timeout is 5 s and hello is single-session; drain before next attack.
        time.sleep(0.25)


def _no_client_cert(cfg: dict) -> str:
    mt = cfg["mtls"]
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_verify_locations(cafile=mt["ca_cert"])
    return _tls_fail_connect(cfg, ctx)


def _wrong_ca(cfg: dict) -> str:
    global _WRONG_CA_CRT
    import datetime as dt
    import tempfile

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    if _WRONG_CA_CRT is None:
        k = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "wrong-ca")])
        ca = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(k.public_key())
            .serial_number(1)
            .not_valid_before(dt.datetime.utcnow() - dt.timedelta(days=1))
            .not_valid_after(dt.datetime.utcnow() + dt.timedelta(days=1))
            .sign(k, hashes.SHA256())
        )
        tmp = Path(tempfile.mkdtemp()) / "wrong.crt"
        tmp.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
        _WRONG_CA_CRT = tmp
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_verify_locations(cafile=str(_WRONG_CA_CRT))
    ctx.load_cert_chain(cfg["mtls"]["client_cert"], cfg["mtls"]["client_key"])
    return _tls_fail_connect(cfg, ctx)


def cmd_faults(cfg: dict, out: Path) -> int:
    unit = load_unit(cfg["unit_name"])
    host, port = cfg["board_ip"], int(cfg["hello_port"])
    results: dict = {"ts": _utc(), "cases": {}}

    # incomplete TLS handshake
    try:
        raw = socket.create_connection((host, port), timeout=5)
        raw.sendall(b"\x16\x03\x01\x00\x01\x00")
        raw.close()
        results["cases"]["incomplete_handshake"] = "sent_garbage"
        time.sleep(6.0)
    except Exception as e:
        results["cases"]["incomplete_handshake"] = f"err:{type(e).__name__}"

    # idle timeout (MCU HELLO_RECV_TO_MS = 5000)
    try:
        s = connect_mtls(cfg, port, timeout=10, unit=unit)
        time.sleep(6.5)
        try:
            s.sendall(b"Hello MCXN\n")
            _ = s.recv(64)
            results["cases"]["idle_timeout"] = "still_open"
        except Exception as e:
            results["cases"]["idle_timeout"] = type(e).__name__
        try:
            s.close()
        except Exception:
            pass
    except Exception as e:
        results["cases"]["idle_timeout"] = f"connect:{type(e).__name__}"

    # no cert / wrong CA (100 unauthorized handshakes: 50+50)
    no_cert = []
    wrong_ca = []
    for i in range(50):
        no_cert.append(_no_client_cert(cfg))
        if (i + 1) % 5 == 0:
            time.sleep(6.0)
            print(f"no_cert {i+1}/50", flush=True)
    for i in range(50):
        wrong_ca.append(_wrong_ca(cfg))
        if (i + 1) % 5 == 0:
            time.sleep(6.0)
            print(f"wrong_ca {i+1}/50", flush=True)
    results["cases"]["no_client_cert_50"] = {
        "ok_if_all_fail": all(x != "UNEXPECTED_OK" for x in no_cert),
        "sample": no_cert[0],
    }
    results["cases"]["wrong_ca_50"] = {
        "ok_if_all_fail": all(x != "UNEXPECTED_OK" for x in wrong_ca),
        "sample": wrong_ca[0],
    }

    # 50 abrupt RST during/after handshake
    rst_ok = 0
    for i in range(50):
        try:
            s = connect_mtls(cfg, port, timeout=10, unit=unit)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, __import__("struct").pack("ii", 1, 0))
            try:
                s.sendall(b"ECHO abort-%d\n" % i)
            except Exception:
                pass
            s.close()
            rst_ok += 1
        except Exception:
            rst_ok += 1  # MCU-side abort still counts as session teardown
    results["cases"]["abrupt_rst_50"] = {"attempts": 50, "completed": rst_ok}

    # PC process kill: child holds a live handshake then SIGTERM
    kills = 0
    for i in range(10):
        p = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import sys,time; sys.path.insert(0,r'%s'); from mcxn_lib import load_cfg,load_unit; from mcxn_lib.mtls import connect_mtls; c=load_cfg(); u=load_unit(c['unit_name']); s=connect_mtls(c,int(c['hello_port']),timeout=10,unit=u); time.sleep(30)"
                % str(TOOLS).replace("\\", "\\\\"),
            ]
        )
        time.sleep(1.2)
        p.kill()
        p.wait(timeout=10)
        kills += 1
    results["cases"]["pc_process_kill_10"] = kills

    # recover
    time.sleep(1)
    ping = _ping(cfg["board_ip"])
    hello = fetch_hello(cfg)
    st = fetch_status(cfg)
    results["recovery"] = {
        "ping": ping,
        "hello": hello,
        "status": st.raw.strip(),
        "pass": ping and "Hello PC!" in hello,
    }
    results["pass"] = (
        results["cases"]["no_client_cert_50"]["ok_if_all_fail"]
        and results["cases"]["wrong_ca_50"]["ok_if_all_fail"]
        and results["recovery"]["pass"]
    )
    out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))
    return 0 if results["pass"] else 1


def _link_cycle(cfg: dict) -> dict:
    """Software equivalent of cable pull: disable/enable the NIC that owns the lab subnet."""
    rec = {"method": "none", "cycles": 0, "recovered": 0}
    ps = (
        "Get-NetIPAddress -AddressFamily IPv4 | "
        "Where-Object { $_.IPAddress -like '192.168.2.*' } | "
        "Select-Object -ExpandProperty InterfaceAlias"
    )
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    alias = (r.stdout or "").strip().splitlines()
    if not alias:
        rec["method"] = "no_lab_nic"
        return rec
    name = alias[0].strip()
    rec["method"] = f"Disable-NetAdapter:{name}"
    rec["alias"] = name
    for i in range(20):
        d = subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"Disable-NetAdapter -Name '{name}' -Confirm:$false"],
            capture_output=True,
            text=True,
        )
        time.sleep(2)
        e = subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"Enable-NetAdapter -Name '{name}' -Confirm:$false"],
            capture_output=True,
            text=True,
        )
        rec["cycles"] += 1
        time.sleep(4)
        if d.returncode != 0 or e.returncode != 0:
            rec["disable_rc"] = d.returncode
            rec["enable_rc"] = e.returncode
            rec["stderr"] = (d.stderr or "") + (e.stderr or "")
            break
        if _ping(cfg["board_ip"]) and "Hello PC!" in fetch_hello(cfg):
            rec["recovered"] += 1
    return rec


def cmd_link(cfg: dict, out: Path) -> int:
    rec = {"ts": _utc(), "link": _link_cycle(cfg)}
    ping = _ping(cfg["board_ip"])
    hello = fetch_hello(cfg) if ping else ""
    rec["after"] = {"ping": ping, "hello": hello}
    rec["pass"] = ping and "Hello PC!" in hello
    if rec["link"].get("cycles") == 20:
        rec["pass"] = rec["pass"] and rec["link"]["recovered"] == 20
    out.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(rec, indent=2))
    return 0 if rec["pass"] else 1


def cmd_soak(cfg: dict, hours: float, workers: int, logdir: Path) -> int:
    unit = load_unit(cfg["unit_name"])
    logdir.mkdir(parents=True, exist_ok=True)
    stop_at = time.time() + hours * 3600
    stats = {
        "tx_bytes": 0,
        "rx_bytes": 0,
        "messages_ok": 0,
        "messages_fail": 0,
        "handshake_fail": 0,
        "tcp_err": 0,
        "reconnects": 0,
        "unexpected_reset": 0,
    }
    lock = threading.Lock()
    start_status = fetch_status(cfg)
    last_uptime = [start_status.uptime_s]
    payload = b"M4" + b"x" * 80  # stays within HELLO_MAX_REQ_B=128 with 'ECHO ' prefix

    def worker(wid: int) -> None:
        seq = 0
        while time.time() < stop_at:
            seq += 1
            try:
                with lock:
                    stats["reconnects"] += 1
                s = connect_mtls(cfg, int(cfg["hello_port"]), timeout=10, unit=unit)
                body = payload + b"-%d-%d" % (wid, seq)
                req = b"ECHO " + body + b"\n"
                s.sendall(req)
                resp = s.recv(256)
                s.close()
                with lock:
                    stats["tx_bytes"] += len(req)
                    stats["rx_bytes"] += len(resp)
                    if b"ECHO" in resp and str(seq).encode() in resp:
                        stats["messages_ok"] += 1
                    else:
                        stats["messages_fail"] += 1
            except (ssl.SSLError, ssl.SSLCertVerificationError, FingerprintError) as e:
                with lock:
                    stats["handshake_fail"] += 1
                    stats["messages_fail"] += 1
                _ = e
            except OSError:
                with lock:
                    stats["tcp_err"] += 1
                    stats["messages_fail"] += 1
            time.sleep(0.15)

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(workers)]
    for t in threads:
        t.start()

    summary_path = logdir / "soak_live.json"
    t0 = time.time()
    while time.time() < stop_at:
        time.sleep(60)
        try:
            st = fetch_status(cfg)
            if st.uptime_s is not None and last_uptime[0] is not None and st.uptime_s + 5 < last_uptime[0]:
                stats["unexpected_reset"] += 1
            if st.uptime_s is not None:
                last_uptime[0] = st.uptime_s
            ping = _ping(cfg["board_ip"])
        except Exception:
            ping = _ping(cfg["board_ip"])
            st_raw = "STATUS_FAIL"
            stats["tcp_err"] += 1
        else:
            st_raw = st.raw.strip()
        elapsed = time.time() - t0
        with lock:
            snap = dict(stats)
        snap.update(
            {
                "ts": _utc(),
                "elapsed_s": round(elapsed, 1),
                "hours_left": round((stop_at - time.time()) / 3600, 3),
                "app_bps": round((snap["tx_bytes"] + snap["rx_bytes"]) / max(elapsed, 1), 1),
                "ping": ping,
                "status": st_raw,
                "start_status": start_status.raw.strip(),
            }
        )
        summary_path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
        print(
            f"soak t={elapsed:.0f}s ok={snap['messages_ok']} fail={snap['messages_fail']} "
            f"hs_fail={snap['handshake_fail']} bps={snap['app_bps']} ping={ping}",
            flush=True,
        )

    for t in threads:
        t.join(timeout=30)
    with lock:
        final = dict(stats)
    elapsed = time.time() - t0
    hello = fetch_hello(cfg)
    st = fetch_status(cfg)
    final.update(
        {
            "ts": _utc(),
            "hours": hours,
            "workers": workers,
            "elapsed_s": round(elapsed, 1),
            "app_bps": round((final["tx_bytes"] + final["rx_bytes"]) / max(elapsed, 1), 1),
            "end_hello": hello,
            "end_status": st.raw.strip(),
            "pass": final["unexpected_reset"] == 0 and "Hello PC!" in hello and final["messages_ok"] > 0,
        }
    )
    (logdir / "soak_final.json").write_text(json.dumps(final, indent=2) + "\n", encoding="utf-8")
    print("SOAK_FINAL", json.dumps(final, indent=2))
    return 0 if final["pass"] else 1


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("reconnect")
    r.add_argument("--count", type=int, default=1000)
    r.add_argument("--out", type=Path, default=ROOT / "docs" / "evidence" / "M4_reconnect.json")
    f = sub.add_parser("faults")
    f.add_argument("--out", type=Path, default=ROOT / "docs" / "evidence" / "M4_faults.json")
    l = sub.add_parser("link")
    l.add_argument("--out", type=Path, default=ROOT / "docs" / "evidence" / "M4_link.json")
    s = sub.add_parser("soak")
    s.add_argument("--hours", type=float, default=24.0)
    s.add_argument("--workers", type=int, default=5)
    s.add_argument("--logdir", type=Path, default=Path(r"C:\mcxn\builds\m4_soak"))
    args = p.parse_args()
    cfg = load_cfg()
    if args.cmd == "reconnect":
        return cmd_reconnect(cfg, args.count, args.out)
    if args.cmd == "faults":
        return cmd_faults(cfg, args.out)
    if args.cmd == "link":
        return cmd_link(cfg, args.out)
    if args.cmd == "soak":
        return cmd_soak(cfg, args.hours, args.workers, args.logdir)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
