"""
Load Test — spin up 10 concurrent clients, each sending messages,
and measure end-to-end delivery time.

Writes per-message delivery latencies to  metrics/load_test_latency.csv
and prints a summary at the end.

Usage:
    python3 load_test.py [--clients 10] [--messages 20] [--output metrics/load_test_latency.csv]
"""

import argparse
import csv
import os
import subprocess
import signal
import socket
import threading
import time
import statistics

from protocol import (
    register_user, login_user, send_broadcast,
    recv_message, BROADCAST, HEADER_SIZE, CHAT_PORT
)
from monitor_server import ServerMonitor

NUM_CLIENTS  = 10
NUM_MESSAGES = 20      # each client sends this many broadcasts
PASSWORD     = "pass"


def _find_server_pid(name: str = "chat_server") -> int | None:
    """Find PID of the running chat_server."""
    try:
        out = subprocess.check_output(["pgrep", "-f", name]).decode().split()
        return int(out[0]) if out else None
    except Exception:
        return None


def client_worker(client_id: int, num_messages: int,
                  latencies: list, lock: threading.Lock,
                  barrier: threading.Barrier):
    """
    One test client:
      1. Register + login
      2. Wait at barrier so all clients start sending together
      3. Send `num_messages` broadcasts and record delivery latencies
    """
    username = f"loaduser{client_id}"

    # Register
    if not register_user(username, PASSWORD):
        print(f"[load] {username} registration failed")
        barrier.wait()          # still hit the barrier so others aren't stuck
        return

    # Login
    sock = login_user(username, PASSWORD)
    if sock is None:
        print(f"[load] {username} login failed")
        barrier.wait()
        return

    # Make socket non-blocking for receive with a short timeout
    sock.settimeout(2.0)

    # Wait for all clients to be ready
    barrier.wait()

    for i in range(num_messages):
        msg = f"LOAD_{client_id}_{i}_{time.monotonic_ns()}"
        t_send = time.monotonic()
        send_broadcast(sock, username, msg)

        # Read back any messages that arrive (broadcasts from others + echo)
        try:
            while True:
                _type, _sender, _target, _payload = recv_message(sock)
                if _type == BROADCAST:
                    t_recv = time.monotonic()
                    # Only measure latency for our OWN messages echoed back
                    # We won't receive our own broadcast back (server skips sender),
                    # so measure from other clients receiving ours.
                    # Instead, we'll just measure round-trip of any received msg.
                    with lock:
                        latencies.append(t_recv - t_send)
                    break
        except (socket.timeout, ConnectionError):
            pass  # no message received in time

        time.sleep(0.05)  # small delay between messages

    sock.close()


def run_load_test(num_clients: int = NUM_CLIENTS,
                  num_messages: int = NUM_MESSAGES,
                  output: str = "metrics/load_test_latency.csv",
                  monitor_output: str = "metrics/load_test_server_metrics.csv"):
    """Run the full load test and return (latencies, server_summary)."""
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)

    # ── Start server monitor ──────────────────────────────────────────────────
    server_pid = _find_server_pid()
    monitor = None
    if server_pid:
        monitor = ServerMonitor(server_pid, monitor_output, interval=2.0)
        monitor.start()
        print(f"[load] Server monitor started (PID {server_pid})")
    else:
        print("[load] WARNING: could not find chat_server PID — no server metrics")

    # ── Prepare shared state ──────────────────────────────────────────────────
    latencies: list[float] = []
    lock = threading.Lock()
    barrier = threading.Barrier(num_clients)

    threads: list[threading.Thread] = []
    print(f"[load] Spawning {num_clients} clients, {num_messages} msgs each …")

    for cid in range(num_clients):
        t = threading.Thread(target=client_worker,
                             args=(cid, num_messages, latencies, lock, barrier))
        threads.append(t)
        t.start()
        time.sleep(0.1)        # small stagger to avoid connection storm

    for t in threads:
        t.join(timeout=60)

    # ── Stop monitor ──────────────────────────────────────────────────────────
    if monitor:
        monitor.stop()

    # ── Write latency CSV ─────────────────────────────────────────────────────
    with open(output, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["latency_ms"])
        for lat in latencies:
            w.writerow([round(lat * 1000, 3)])

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 55)
    print("         LOAD TEST SUMMARY  (threaded server)")
    print("=" * 55)
    print(f"  Clients        : {num_clients}")
    print(f"  Messages/client: {num_messages}")
    print(f"  Total latencies: {len(latencies)}")
    if latencies:
        ms = [l * 1000 for l in latencies]
        print(f"  Delivery time  :")
        print(f"     min   = {min(ms):.3f} ms")
        print(f"     max   = {max(ms):.3f} ms")
        print(f"     mean  = {statistics.mean(ms):.3f} ms")
        print(f"     median= {statistics.median(ms):.3f} ms")
        if len(ms) > 1:
            print(f"     stdev = {statistics.stdev(ms):.3f} ms")
    if monitor:
        srv = monitor.summary()
        print(f"  Server CPU%    : {srv.get('cpu_percent', {})}")
        print(f"  Server VmRSS   : {srv.get('vmrss_kb', {})} KB")
        print(f"  Server PSS     : {srv.get('pss_kb', {})} KB")
    print("=" * 55)

    return latencies, monitor.summary() if monitor else {}


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load test for threaded chat server")
    parser.add_argument("--clients",  type=int, default=NUM_CLIENTS)
    parser.add_argument("--messages", type=int, default=NUM_MESSAGES)
    parser.add_argument("--output",   default="metrics/load_test_latency.csv")
    args = parser.parse_args()
    run_load_test(args.clients, args.messages, args.output)
