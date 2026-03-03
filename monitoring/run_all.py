"""
run_all.py — one-click orchestrator that tests BOTH chat servers
(threaded and select) and produces comparison plots.

What it does:
  1. (Optionally) builds the project via make
  2. Starts discovery_server + chat_server (threaded)
  3. Runs Load Test  → metrics/threaded_load_test_*.csv
  4. Runs Stress Test → metrics/threaded_stress_test_*.csv
  5. Restarts with chat_server_select
  6. Runs Load Test  → metrics/select_load_test_*.csv
  7. Runs Stress Test → metrics/select_stress_test_*.csv
  8. Generates comparison plots → metrics/plots/
  9. Prints a combined summary report

Usage:
    cd monitoring/
    python3 run_all.py            # runs everything
    python3 run_all.py --skip-build --skip-stress
    python3 run_all.py --only threaded
    python3 run_all.py --only select
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
CHAT_BINS   = {
    "threaded": os.path.join(PROJECT_DIR, "chat_server"),
    "select":   os.path.join(PROJECT_DIR, "chat_server_select"),
}
USERS_TXT   = os.path.join(PROJECT_DIR, "users.txt")


def build():
    print("\n── Building project ──")
    subprocess.check_call(["make", "-C", PROJECT_DIR, "clean"])
    subprocess.check_call(["make", "-C", PROJECT_DIR, "-j4"])
    print("[OK] Build complete.\n")


def _kill(name: str):
    """Kill all processes matching `name` (best-effort)."""
    try:
        subprocess.call(["pkill", "-x", name],
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


def start_servers(server_label: str):
    """Launch discovery_server + the specified chat server binary."""
    if os.path.exists(USERS_TXT):
        os.remove(USERS_TXT)

    _kill("discovery_server")
    _kill("chat_server")
    _kill("chat_server_select")
    time.sleep(0.5)

    disc = subprocess.Popen([DISC_BIN], cwd=PROJECT_DIR,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _wait_for_process(disc, "discovery_server")

    chat_bin = CHAT_BINS[server_label]
    chat = subprocess.Popen([chat_bin], cwd=PROJECT_DIR,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _wait_for_process(chat, os.path.basename(chat_bin))

    return disc, chat


def stop_servers(disc, chat):
    for p in (chat, disc):
        try:
            p.terminate()
            p.wait(timeout=3)
        except Exception:
            p.kill()
    time.sleep(0.3)


def _run_tests_for_server(server_label: str, server_bin_name: str,
                          skip_load: bool, skip_stress: bool):
    """Run load + stress tests for one server variant."""
    prefix = f"metrics/{server_label}"

    if not skip_load:
        print(f"\n{'=' * 60}")
        print(f"          LOAD TEST  ({server_label} server)")
        print(f"{'=' * 60}")
        disc, chat = start_servers(server_label)
        time.sleep(1)

        from load_test import run_load_test
        run_load_test(
            num_clients=10, num_messages=20,
            output=f"{prefix}_load_test_latency.csv",
            monitor_output=f"{prefix}_load_test_server_metrics.csv",
            server_label=server_label,
            server_bin_name=server_bin_name,
        )

        stop_servers(disc, chat)
        time.sleep(1)

    if not skip_stress:
        print(f"\n{'=' * 60}")
        print(f"         STRESS TEST  ({server_label} server)")
        print(f"{'=' * 60}")
        disc, chat = start_servers(server_label)
        time.sleep(1)

        from stress_test import run_stress_test
        run_stress_test(
            start=2, step=5, max_clients=50, msgs_per_client=10,
            output=f"{prefix}_stress_test_results.csv",
            monitor_output=f"{prefix}_stress_test_server_metrics.csv",
            server_label=server_label,
            server_bin_name=server_bin_name,
        )

        stop_servers(disc, chat)
        time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description="Run all monitoring tests (threaded + select)")
    parser.add_argument("--skip-build",  action="store_true")
    parser.add_argument("--skip-load",   action="store_true")
    parser.add_argument("--skip-stress", action="store_true")
    parser.add_argument("--skip-plots",  action="store_true")
    parser.add_argument("--only", choices=["threaded", "select"], default=None,
                        help="Test only one server variant instead of both")
    args = parser.parse_args()

    # Ensure we run from the monitoring/ directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # ── 1. Build ──────────────────────────────────────────────────────────────
    if not args.skip_build:
        build()

    # ── 2. Determine which servers to test ────────────────────────────────────
    servers_to_test = {
        "threaded": "chat_server",
        "select":   "chat_server_select",
    }
    if args.only:
        servers_to_test = {args.only: servers_to_test[args.only]}

    # ── 3. Run tests for each server ──────────────────────────────────────────
    for label, bin_name in servers_to_test.items():
        _run_tests_for_server(label, bin_name,
                              args.skip_load, args.skip_stress)

    # ── 4. Visualise — comparison plots ───────────────────────────────────────
    if not args.skip_plots:
        print(f"\n{'=' * 60}")
        print("             GENERATING COMPARISON PLOTS")
        print(f"{'=' * 60}")
        from visualize import generate_all_plots
        generate_all_plots("metrics")

    print("\n✓ All done.  Check monitoring/metrics/ for CSVs and metrics/plots/ for graphs.\n")


if __name__ == "__main__":
    main()
