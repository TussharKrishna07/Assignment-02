"""
Visualization — generates comparison plots from test metrics CSVs.

Plots produced (saved to  metrics/plots/):
  1. message_delivery_time.png  — latency distribution (histogram + box)
  2. cpu_vs_clients.png         — CPU% as clients increase
  3. memory_vs_clients.png      — VmRSS / PSS as clients increase

Currently only threaded-server data is plotted.  When fork / select
server metrics are available, add their CSV paths and they'll appear
on the same plots for comparison.

Usage:
    python3 visualize.py [--metrics-dir metrics]
"""

import argparse
import os
import csv
import sys

import matplotlib
matplotlib.use("Agg")          # headless — no display needed
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np


PLOTS_DIR = "metrics/plots"


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
    server_types = {
        "Threaded": os.path.join(metrics_dir, "load_test_latency.csv"),
        # Add when available:
        # "Fork":        os.path.join(metrics_dir, "fork_load_test_latency.csv"),
        # "Non-blocking": os.path.join(metrics_dir, "select_load_test_latency.csv"),
    }

    data = {}
    for label, path in server_types.items():
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
        ax.hist(vals, bins=40, alpha=0.6, label=label, edgecolor="black")
    ax.set_xlabel("Delivery Latency (ms)")
    ax.set_ylabel("Count")
    ax.set_title("Message Delivery Time Distribution")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    # Boxplot
    ax = axes[1]
    bp_data = list(data.values())
    bp_labels = list(data.keys())
    bp = ax.boxplot(bp_data, labels=bp_labels, patch_artist=True)
    colors = ["#4C72B0", "#DD8452", "#55A868"]
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
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
    server_types = {
        "Threaded": os.path.join(metrics_dir, "stress_test_results.csv"),
        # "Fork":        ...,
        # "Non-blocking": ...,
    }

    fig, ax = plt.subplots(figsize=(9, 5))
    markers = ["o", "s", "^"]
    colors  = ["#4C72B0", "#DD8452", "#55A868"]

    for idx, (label, path) in enumerate(server_types.items()):
        rows = _load_csv(path)
        clients = [float(r["num_clients"]) for r in rows
                    if r.get("num_clients") and r.get("cpu_percent")
                    and float(r["cpu_percent"]) >= 0]
        cpu     = [float(r["cpu_percent"]) for r in rows
                    if r.get("num_clients") and r.get("cpu_percent")
                    and float(r["cpu_percent"]) >= 0]
        if clients and cpu and len(clients) == len(cpu):
            ax.plot(clients, cpu, marker=markers[idx % 3],
                    color=colors[idx % 3], label=label, linewidth=2)

    if not ax.get_lines():
        print("[viz] No CPU vs clients data — skipping")
        plt.close()
        return

    ax.set_xlabel("Number of Concurrent Clients")
    ax.set_ylabel("Server CPU Usage (%)")
    ax.set_title("CPU Usage vs. Number of Clients")
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
    server_types = {
        "Threaded": os.path.join(metrics_dir, "stress_test_results.csv"),
    }

    fig, ax = plt.subplots(figsize=(9, 5))
    markers = ["o", "s", "^"]
    colors_rss = ["#4C72B0", "#DD8452", "#55A868"]
    colors_pss = ["#7BA3D4", "#EDAB82", "#82C998"]

    for idx, (label, path) in enumerate(server_types.items()):
        rows = _load_csv(path)
        # Filter rows where both clients and memory fields are valid (>= 0)
        valid = [r for r in rows
                 if r.get("num_clients") and r.get("vmrss_kb")
                 and float(r["vmrss_kb"]) >= 0]
        clients = [float(r["num_clients"]) for r in valid]
        rss     = [float(r["vmrss_kb"]) for r in valid]
        pss     = [float(r["pss_kb"]) for r in valid
                   if r.get("pss_kb") and float(r["pss_kb"]) >= 0]

        if clients and rss and len(clients) == len(rss):
            ax.plot(clients, rss, marker=markers[idx % 3],
                    color=colors_rss[idx % 3],
                    label=f"{label} VmRSS", linewidth=2)
        if clients and pss and len(clients) == len(pss):
            ax.plot(clients, pss, marker=markers[idx % 3],
                    color=colors_pss[idx % 3],
                    label=f"{label} PSS", linewidth=2, linestyle="--")

    if not ax.get_lines():
        print("[viz] No memory vs clients data — skipping")
        plt.close()
        return

    ax.set_xlabel("Number of Concurrent Clients")
    ax.set_ylabel("Memory (KB)")
    ax.set_title("Memory Usage vs. Number of Clients")
    ax.legend()
    ax.grid(alpha=0.3)
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))

    plt.tight_layout()
    out = os.path.join(PLOTS_DIR, "memory_vs_clients.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"[viz] Saved {out}")


# ── main ──────────────────────────────────────────────────────────────────────

def generate_all_plots(metrics_dir: str = "metrics"):
    os.makedirs(PLOTS_DIR, exist_ok=True)
    plot_delivery_time(metrics_dir)
    plot_cpu_vs_clients(metrics_dir)
    plot_memory_vs_clients(metrics_dir)
    print(f"\n[viz] All plots saved under  {PLOTS_DIR}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate performance plots")
    parser.add_argument("--metrics-dir", default="metrics")
    args = parser.parse_args()
    generate_all_plots(args.metrics_dir)
