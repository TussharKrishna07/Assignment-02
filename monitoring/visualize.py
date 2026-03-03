"""
Visualization — generates comparison plots for Threaded vs Select chat servers.

Plots produced (saved to  metrics/plots/):
  1. message_delivery_time.png  — latency distribution (histogram + box)
  2. cpu_vs_clients.png         — CPU% as clients increase (stress test)
  3. memory_vs_clients.png      — VmRSS / PSS as clients increase
  4. avg_latency_vs_clients.png — avg delivery latency per step
  5. connection_success.png     — connection success rate per step

Usage:
    python3 visualize.py [--metrics-dir metrics]
"""

import argparse
import os
import csv

import matplotlib
matplotlib.use("Agg")          # headless — no display needed
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np


PLOTS_DIR = "metrics/plots"

# ── Server configurations (label → file-prefix) ──────────────────────────────
SERVERS = {
    "Threaded": "threaded",
    "Select":   "select",
}

COLORS  = {"Threaded": "#4C72B0", "Select": "#DD8452"}
MARKERS = {"Threaded": "o",       "Select": "s"}


# ── helpers ───────────────────────────────────────────────────────────────────

def _load_csv(path: str) -> list[dict]:
    if not os.path.isfile(path):
        print(f"[viz] WARNING: {path} not found — skipping")
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


def _floats(rows: list[dict], key: str) -> list[float]:
    return [float(r[key]) for r in rows if r.get(key) and float(r[key]) >= 0]


# ── Plot 1: message delivery time distribution ───────────────────────────────

def plot_delivery_time(metrics_dir: str):
    """Histogram + boxplot of message delivery latencies for each server type."""
    data: dict[str, list[float]] = {}
    for label, prefix in SERVERS.items():
        path = os.path.join(metrics_dir, f"{prefix}_load_test_latency.csv")
        rows = _load_csv(path)
        vals = _floats(rows, "latency_ms")
        if vals:
            data[label] = vals

    if not data:
        print("[viz] No latency data found — skipping delivery time plot")
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Histogram
    ax = axes[0]
    for label, vals in data.items():
        ax.hist(vals, bins=40, alpha=0.55, label=label,
                edgecolor="black", color=COLORS.get(label))
    ax.set_xlabel("Delivery Latency (ms)")
    ax.set_ylabel("Count")
    ax.set_title("Message Delivery Time Distribution")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    # Boxplot
    ax = axes[1]
    bp_data   = list(data.values())
    bp_labels = list(data.keys())
    bp = ax.boxplot(bp_data, labels=bp_labels, patch_artist=True)
    for patch, label in zip(bp["boxes"], bp_labels):
        patch.set_facecolor(COLORS.get(label, "#999"))
        patch.set_alpha(0.7)
    ax.set_ylabel("Delivery Latency (ms)")
    ax.set_title("Latency Comparison (Box Plot)")
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    out = os.path.join(PLOTS_DIR, "message_delivery_time.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"[viz] Saved {out}")


# ── Plot 2: CPU usage vs number of clients ───────────────────────────────────

def plot_cpu_vs_clients(metrics_dir: str):
    fig, ax = plt.subplots(figsize=(9, 5))

    for label, prefix in SERVERS.items():
        path = os.path.join(metrics_dir, f"{prefix}_stress_test_results.csv")
        rows = _load_csv(path)
        valid = [r for r in rows
                 if r.get("num_clients") and r.get("cpu_percent")
                 and float(r["cpu_percent"]) >= 0]
        clients = [float(r["num_clients"]) for r in valid]
        cpu     = [float(r["cpu_percent"]) for r in valid]
        if clients and cpu:
            ax.plot(clients, cpu, marker=MARKERS[label],
                    color=COLORS[label], label=label, linewidth=2)

    if not ax.get_lines():
        print("[viz] No CPU vs clients data — skipping")
        plt.close()
        return

    ax.set_xlabel("Number of Concurrent Clients")
    ax.set_ylabel("Server CPU Usage (%)")
    ax.set_title("CPU Usage vs. Number of Clients  (Threaded vs Select)")
    ax.legend()
    ax.grid(alpha=0.3)
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))

    plt.tight_layout()
    out = os.path.join(PLOTS_DIR, "cpu_vs_clients.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"[viz] Saved {out}")


# ── Plot 3: Memory usage vs number of clients ────────────────────────────────

def plot_memory_vs_clients(metrics_dir: str):
    fig, ax = plt.subplots(figsize=(9, 5))

    for label, prefix in SERVERS.items():
        path = os.path.join(metrics_dir, f"{prefix}_stress_test_results.csv")
        rows = _load_csv(path)
        valid = [r for r in rows
                 if r.get("num_clients") and r.get("vmrss_kb")
                 and float(r["vmrss_kb"]) >= 0]
        clients = [float(r["num_clients"]) for r in valid]
        rss     = [float(r["vmrss_kb"]) for r in valid]
        pss     = [float(r.get("pss_kb", -1)) for r in valid
                   if float(r.get("pss_kb", -1)) >= 0]

        if clients and rss:
            ax.plot(clients, rss, marker=MARKERS[label],
                    color=COLORS[label],
                    label=f"{label} VmRSS", linewidth=2)
        if clients and pss and len(clients) == len(pss):
            ax.plot(clients, pss, marker=MARKERS[label],
                    color=COLORS[label],
                    label=f"{label} PSS", linewidth=2, linestyle="--",
                    alpha=0.6)

    if not ax.get_lines():
        print("[viz] No memory vs clients data — skipping")
        plt.close()
        return

    ax.set_xlabel("Number of Concurrent Clients")
    ax.set_ylabel("Memory (KB)")
    ax.set_title("Memory Usage vs. Number of Clients  (Threaded vs Select)")
    ax.legend()
    ax.grid(alpha=0.3)
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))

    plt.tight_layout()
    out = os.path.join(PLOTS_DIR, "memory_vs_clients.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"[viz] Saved {out}")


# ── Plot 4: Average latency vs number of clients ─────────────────────────────

def plot_avg_latency_vs_clients(metrics_dir: str):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Left: average latency
    ax = axes[0]
    for label, prefix in SERVERS.items():
        path = os.path.join(metrics_dir, f"{prefix}_stress_test_results.csv")
        rows = _load_csv(path)
        valid = [r for r in rows
                 if r.get("num_clients") and r.get("avg_latency_ms")
                 and float(r["avg_latency_ms"]) >= 0]
        clients = [float(r["num_clients"]) for r in valid]
        avg_lat = [float(r["avg_latency_ms"]) for r in valid]
        if clients and avg_lat:
            ax.plot(clients, avg_lat, marker=MARKERS[label],
                    color=COLORS[label], label=label, linewidth=2)

    ax.set_xlabel("Number of Concurrent Clients")
    ax.set_ylabel("Average Latency (ms)")
    ax.set_title("Avg Delivery Latency vs. Clients")
    ax.legend()
    ax.grid(alpha=0.3)
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))

    # Right: p95 latency
    ax = axes[1]
    for label, prefix in SERVERS.items():
        path = os.path.join(metrics_dir, f"{prefix}_stress_test_results.csv")
        rows = _load_csv(path)
        valid = [r for r in rows
                 if r.get("num_clients") and r.get("p95_latency_ms")
                 and float(r["p95_latency_ms"]) >= 0]
        clients = [float(r["num_clients"]) for r in valid]
        p95     = [float(r["p95_latency_ms"]) for r in valid]
        if clients and p95:
            ax.plot(clients, p95, marker=MARKERS[label],
                    color=COLORS[label], label=label, linewidth=2)

    ax.set_xlabel("Number of Concurrent Clients")
    ax.set_ylabel("P95 Latency (ms)")
    ax.set_title("P95 Delivery Latency vs. Clients")
    ax.legend()
    ax.grid(alpha=0.3)
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))

    if not any(axes[i].get_lines() for i in range(2)):
        print("[viz] No latency-vs-clients data — skipping")
        plt.close()
        return

    plt.tight_layout()
    out = os.path.join(PLOTS_DIR, "avg_latency_vs_clients.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"[viz] Saved {out}")


# ── Plot 5: Connection success rate ──────────────────────────────────────────

def plot_connection_success(metrics_dir: str):
    fig, ax = plt.subplots(figsize=(9, 5))

    for label, prefix in SERVERS.items():
        path = os.path.join(metrics_dir, f"{prefix}_stress_test_results.csv")
        rows = _load_csv(path)
        valid = [r for r in rows
                 if r.get("num_clients") and r.get("connected")]
        clients  = [int(r["num_clients"]) for r in valid]
        success  = [int(r["connected"]) / int(r["num_clients"]) * 100
                    for r in valid]
        if clients and success:
            ax.plot(clients, success, marker=MARKERS[label],
                    color=COLORS[label], label=label, linewidth=2)

    if not ax.get_lines():
        print("[viz] No connection-success data — skipping")
        plt.close()
        return

    ax.set_xlabel("Number of Concurrent Clients")
    ax.set_ylabel("Connection Success Rate (%)")
    ax.set_title("Connection Success vs. Clients  (Threaded vs Select)")
    ax.set_ylim(0, 110)
    ax.legend()
    ax.grid(alpha=0.3)
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))

    plt.tight_layout()
    out = os.path.join(PLOTS_DIR, "connection_success.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"[viz] Saved {out}")


# ── main ──────────────────────────────────────────────────────────────────────

def generate_all_plots(metrics_dir: str = "metrics"):
    os.makedirs(PLOTS_DIR, exist_ok=True)
    plot_delivery_time(metrics_dir)
    plot_cpu_vs_clients(metrics_dir)
    plot_memory_vs_clients(metrics_dir)
    plot_avg_latency_vs_clients(metrics_dir)
    plot_connection_success(metrics_dir)
    print(f"\n[viz] All plots saved under  {PLOTS_DIR}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate performance comparison plots")
    parser.add_argument("--metrics-dir", default="metrics")
    args = parser.parse_args()
    generate_all_plots(args.metrics_dir)
