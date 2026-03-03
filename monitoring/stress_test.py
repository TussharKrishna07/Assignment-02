"""
Stress Test — gradually increase concurrent clients until the server
shows signs of degradation (high latency, failed connections, or errors).

For each "step" we add more clients and measure:
  - connection success rate
  - message delivery latency
  - server CPU / memory

Results are saved to  metrics/stress_test_results.csv
Server metrics are in  metrics/stress_test_server_metrics.csv

Usage:
    python3 stress_test.py [--start 2] [--step 5] [--max 50] [--msgs 10]
"""

import argparse
import csv
import os
import subprocess
import socket
import threading
import time
import statistics

from protocol import (
    register_user, login_user, send_broadcast,
    recv_message, BROADCAST
)
from monitor_server import ServerMonitor

PASSWORD = "pass"


def _find_server_pid(name: str = "chat_server") -> int | None:
    try:
        out = subprocess.check_output(["pgrep", "-f", name]).decode().split()
        return int(out[0]) if out else None
    except Exception:
        return None


def _stress_worker(client_id: int, step: int, num_messages: int,
                   results: list, lock: threading.Lock,
                   barrier: threading.Barrier):
    """Single client for one stress step."""
    username = f"stressuser_s{step}_c{client_id}"
    latencies: list[float] = []
    success = True

    try:
        if not register_user(username, PASSWORD):
            success = False
            barrier.wait()
            with lock:
                results.append({"client": username, "connected": False,
                                "latencies": []})
            return

        sock = login_user(username, PASSWORD)
        if sock is None:
            success = False
            barrier.wait()
            with lock:
                results.append({"client": username, "connected": False,
                                "latencies": []})
            return

        sock.settimeout(3.0)
        barrier.wait()

        for i in range(num_messages):
            msg = f"STRESS_{step}_{client_id}_{i}"
            t0 = time.monotonic()
            send_broadcast(sock, username, msg)
            try:
                _type, _, _, _ = recv_message(sock)
                t1 = time.monotonic()
                if _type == BROADCAST:
                    latencies.append((t1 - t0) * 1000)   # ms
            except (socket.timeout, ConnectionError):
                latencies.append(-1)  # mark failed delivery
            time.sleep(0.05)

        sock.close()
    except Exception as e:
        print(f"[stress] {username} error: {e}")
        success = False

    with lock:
        results.append({
            "client": username,
            "connected": success,
            "latencies": latencies,
        })


def run_stress_test(start: int = 2, step: int = 5, max_clients: int = 50,
                    msgs_per_client: int = 10,
                    output: str = "metrics/stress_test_results.csv",
                    monitor_output: str = "metrics/stress_test_server_metrics.csv"):
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)

    server_pid = _find_server_pid()
    monitor = None
    if server_pid:
        monitor = ServerMonitor(server_pid, monitor_output, interval=2.0)
        monitor.start()
        print(f"[stress] Server monitor started (PID {server_pid})")

    summary_rows: list[dict] = []

    num_clients = start
    while num_clients <= max_clients:
        print(f"\n── Step: {num_clients} clients, {msgs_per_client} msgs each ──")
        results: list[dict] = []
        lock = threading.Lock()
        barrier = threading.Barrier(num_clients, timeout=30)

        threads = []
        for cid in range(num_clients):
            t = threading.Thread(target=_stress_worker,
                                 args=(cid, num_clients, msgs_per_client,
                                       results, lock, barrier))
            threads.append(t)
            t.start()
            time.sleep(0.05)

        for t in threads:
            t.join(timeout=120)

        # Aggregate
        connected = sum(1 for r in results if r["connected"])
        all_lat = [l for r in results for l in r["latencies"] if l >= 0]
        failed   = sum(1 for r in results for l in r["latencies"] if l < 0)

        row = {
            "num_clients":    num_clients,
            "connected":      connected,
            "failed_conns":   num_clients - connected,
            "total_msgs":     len(all_lat) + failed,
            "delivered":      len(all_lat),
            "failed_msgs":    failed,
            "avg_latency_ms": round(statistics.mean(all_lat), 3) if all_lat else -1,
            "max_latency_ms": round(max(all_lat), 3) if all_lat else -1,
            "p95_latency_ms": round(sorted(all_lat)[int(len(all_lat)*0.95)] , 3)
                              if len(all_lat) > 1 else (-1),
        }

        # Grab latest server metrics snapshot
        if monitor and monitor.rows:
            last = monitor.rows[-1]
            row["cpu_percent"] = last["cpu_percent"]
            row["vmrss_kb"]    = last["vmrss_kb"]
            row["pss_kb"]      = last["pss_kb"]
        else:
            row["cpu_percent"] = -1
            row["vmrss_kb"]    = -1
            row["pss_kb"]      = -1

        summary_rows.append(row)

        print(f"   connected={connected}/{num_clients}  "
              f"delivered={row['delivered']}  failed_msgs={failed}  "
              f"avg_lat={row['avg_latency_ms']}ms  max_lat={row['max_latency_ms']}ms  "
              f"CPU={row['cpu_percent']}%  VmRSS={row['vmrss_kb']}KB")

        # Check for degradation
        if connected < num_clients * 0.5 or (all_lat and max(all_lat) > 5000):
            print("[stress] *** Degradation detected — stopping ***")
            break

        num_clients += step

    if monitor:
        monitor.stop()

    # Write summary CSV
    fieldnames = ["num_clients", "connected", "failed_conns", "total_msgs",
                  "delivered", "failed_msgs", "avg_latency_ms", "max_latency_ms",
                  "p95_latency_ms", "cpu_percent", "vmrss_kb", "pss_kb"]
    with open(output, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(summary_rows)

    # Print final summary
    print("\n" + "=" * 60)
    print("         STRESS TEST SUMMARY  (threaded server)")
    print("=" * 60)
    for r in summary_rows:
        print(f"  {r['num_clients']:>3} clients | "
              f"conn={r['connected']:>3} | "
              f"avg_lat={r['avg_latency_ms']:>8} ms | "
              f"CPU={r['cpu_percent']:>6}% | "
              f"RSS={r['vmrss_kb']:>7} KB")
    print("=" * 60)

    return summary_rows


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stress test for threaded chat server")
    parser.add_argument("--start", type=int, default=2,
                        help="Starting number of clients")
    parser.add_argument("--step",  type=int, default=5,
                        help="Add this many clients each step")
    parser.add_argument("--max",   type=int, default=50,
                        help="Maximum number of clients")
    parser.add_argument("--msgs",  type=int, default=10,
                        help="Messages each client sends per step")
    parser.add_argument("--output", default="metrics/stress_test_results.csv")
    args = parser.parse_args()
    run_stress_test(args.start, args.step, args.max, args.msgs, args.output)
