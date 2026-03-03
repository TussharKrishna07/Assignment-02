"""
run_all.py — one-click orchestrator for the threaded chat server tests.

What it does:
  1. (Optionally) builds the project via make
  2. Starts discovery_server and chat_server_threaded
  3. Runs the Load Test   →  metrics/load_test_*.csv
  4. Restarts servers (clean state)
  5. Runs the Stress Test →  metrics/stress_test_*.csv
  6. Generates visualisation plots  →  metrics/plots/
  7. Prints a combined summary report

Usage:
    cd monitoring/
    python3 run_all.py            # runs everything
    python3 run_all.py --skip-build --skip-stress
"""

import argparse
import os
import signal
import subprocess
import time
import sys

# ── paths (relative to the monitoring/ directory) ─────────────────────────────
PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DISC_BIN    = os.path.join(PROJECT_DIR, "discovery_server")
CHAT_BIN    = os.path.join(PROJECT_DIR, "chat_server")
USERS_TXT   = os.path.join(PROJECT_DIR, "users.txt")


def build():
    print("\n── Building project ──")
    subprocess.check_call(["make", "-C", PROJECT_DIR, "clean"])
    subprocess.check_call(["make", "-C", PROJECT_DIR, "-j4"])
    print("[OK] Build complete.\n")


def _kill(name: str):
    """Kill all processes matching `name` (best-effort)."""
    try:
        subprocess.call(["pkill", "-f", name],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    time.sleep(0.3)


def _wait_for_process(proc: subprocess.Popen, label: str, wait: float = 2.0):
    """Wait briefly and verify the process hasn't exited."""
    time.sleep(wait)
    if proc.poll() is not None:
        print(f"[ERROR] {label} exited with code {proc.returncode}")
        sys.exit(1)
    print(f"[OK] {label} is running (PID {proc.pid})")


def start_servers():
    """Launch discovery_server and chat_server, return (disc_proc, chat_proc)."""
    # Clean previous user registrations
    if os.path.exists(USERS_TXT):
        os.remove(USERS_TXT)

    _kill("discovery_server")
    _kill("chat_server")
    time.sleep(0.5)

    disc = subprocess.Popen([DISC_BIN], cwd=PROJECT_DIR,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _wait_for_process(disc, "discovery_server")

    chat = subprocess.Popen([CHAT_BIN], cwd=PROJECT_DIR,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _wait_for_process(chat, "chat_server")

    return disc, chat


def stop_servers(disc, chat):
    for p in (chat, disc):
        try:
            p.terminate()
            p.wait(timeout=3)
        except Exception:
            p.kill()
    time.sleep(0.3)


def main():
    parser = argparse.ArgumentParser(description="Run all monitoring tests")
    parser.add_argument("--skip-build",  action="store_true")
    parser.add_argument("--skip-load",   action="store_true")
    parser.add_argument("--skip-stress", action="store_true")
    parser.add_argument("--skip-plots",  action="store_true")
    args = parser.parse_args()

    # Ensure we run from the monitoring/ directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # ── 1. Build ──────────────────────────────────────────────────────────────
    if not args.skip_build:
        build()

    # ── 2. Load Test ──────────────────────────────────────────────────────────
    if not args.skip_load:
        print("\n" + "=" * 60)
        print("                   LOAD TEST")
        print("=" * 60)
        disc, chat = start_servers()
        time.sleep(1)

        from load_test import run_load_test
        run_load_test(num_clients=10, num_messages=20,
                      output="metrics/load_test_latency.csv",
                      monitor_output="metrics/load_test_server_metrics.csv")

        stop_servers(disc, chat)
        time.sleep(1)

    # ── 3. Stress Test ────────────────────────────────────────────────────────
    if not args.skip_stress:
        print("\n" + "=" * 60)
        print("                  STRESS TEST")
        print("=" * 60)
        disc, chat = start_servers()
        time.sleep(1)

        from stress_test import run_stress_test
        run_stress_test(start=2, step=5, max_clients=50, msgs_per_client=10,
                        output="metrics/stress_test_results.csv",
                        monitor_output="metrics/stress_test_server_metrics.csv")

        stop_servers(disc, chat)
        time.sleep(1)

    # ── 4. Visualise ──────────────────────────────────────────────────────────
    if not args.skip_plots:
        print("\n" + "=" * 60)
        print("                GENERATING PLOTS")
        print("=" * 60)
        from visualize import generate_all_plots
        generate_all_plots("metrics")

    print("\n✓ All done.  Check monitoring/metrics/ for CSVs and plots.\n")


if __name__ == "__main__":
    main()
