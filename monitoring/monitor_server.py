"""
Server metrics collector — polls CPU and memory for the chat_server process
and writes rows to a CSV file at a configurable interval.

Usage (standalone):
    python3 monitor_server.py --pid <PID> [--interval 5] [--output metrics/server_metrics.csv]

Or import and use ServerMonitor in your test scripts.
"""

import argparse
import csv
import os
import time
import threading


def _read_pss(pid: int) -> int:
    """Read Proportional Set Size from /proc/<pid>/smaps_rollup (Linux).
    Returns PSS in KB, or -1 if unavailable."""
    try:
        with open(f"/proc/{pid}/smaps_rollup") as f:
            for line in f:
                if line.startswith("Pss:"):
                    return int(line.split()[1])
    except (FileNotFoundError, PermissionError):
        pass
    return -1


def _read_vmrss(pid: int) -> int:
    """Read VmRSS from /proc/<pid>/status.  Returns KB or -1."""
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except (FileNotFoundError, PermissionError):
        pass
    return -1


def _read_cpu(pid: int) -> tuple[float, float]:
    """Return (process_jiffies, total_jiffies) for delta-based CPU%."""
    try:
        with open(f"/proc/{pid}/stat") as f:
            parts = f.read().split()
            utime = int(parts[13])
            stime = int(parts[14])
            proc_jiffies = utime + stime
        with open("/proc/stat") as f:
            cpu_line = f.readline()  # first line = total
            vals = list(map(int, cpu_line.split()[1:]))
            total_jiffies = sum(vals)
        return proc_jiffies, total_jiffies
    except Exception:
        return 0, 1  # avoid division by zero


class ServerMonitor:
    """Collects CPU% and memory metrics for a given PID at fixed intervals."""

    def __init__(self, pid: int, output_path: str = "metrics/server_metrics.csv",
                 interval: float = 5.0):
        self.pid = pid
        self.output_path = output_path
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.rows: list[dict] = []          # kept in-memory too for reports

    # ── internal ──────────────────────────────────────────────────────────────
    def _sample(self, prev_proc: float, prev_total: float):
        proc_j, total_j = _read_cpu(self.pid)
        d_proc  = proc_j  - prev_proc
        d_total = total_j - prev_total
        cpu_pct = (d_proc / d_total) * 100.0 if d_total else 0.0

        vmrss = _read_vmrss(self.pid)
        pss   = _read_pss(self.pid)
        ts    = time.time()
        row = {
            "timestamp":  round(ts, 3),
            "cpu_percent": round(cpu_pct, 2),
            "vmrss_kb":   vmrss,
            "pss_kb":     pss,
        }
        self.rows.append(row)
        return row, proc_j, total_j

    def _loop(self):
        os.makedirs(os.path.dirname(self.output_path) or ".", exist_ok=True)
        with open(self.output_path, "w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile,
                                    fieldnames=["timestamp", "cpu_percent",
                                                "vmrss_kb", "pss_kb"])
            writer.writeheader()

            prev_proc, prev_total = _read_cpu(self.pid)
            # Take a quick first sample after 1 second so short tests still get data
            time.sleep(min(1.0, self.interval))

            while not self._stop.is_set():
                row, prev_proc, prev_total = self._sample(prev_proc, prev_total)
                writer.writerow(row)
                csvfile.flush()
                print(f"[monitor] CPU={row['cpu_percent']:6.2f}%  "
                      f"VmRSS={row['vmrss_kb']}KB  PSS={row['pss_kb']}KB")
                self._stop.wait(self.interval)

    # ── public API ────────────────────────────────────────────────────────────
    def start(self):
        """Start background collection thread."""
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Signal the collector to stop and wait for it."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval + 2)

    def summary(self) -> dict:
        """Return a dict with min/max/avg of each metric."""
        if not self.rows:
            return {}
        keys = ["cpu_percent", "vmrss_kb", "pss_kb"]
        result = {}
        for k in keys:
            vals = [r[k] for r in self.rows if r[k] >= 0]
            if vals:
                result[k] = {
                    "min": min(vals),
                    "max": max(vals),
                    "avg": round(sum(vals) / len(vals), 2),
                }
        return result


# ── CLI entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monitor chat_server metrics")
    parser.add_argument("--pid", type=int, required=True,
                        help="PID of the chat_server process")
    parser.add_argument("--interval", type=float, default=5.0,
                        help="Sampling interval in seconds (default 5)")
    parser.add_argument("--output", default="metrics/server_metrics.csv",
                        help="Output CSV path")
    args = parser.parse_args()

    mon = ServerMonitor(args.pid, args.output, args.interval)
    print(f"[monitor] Tracking PID {args.pid} every {args.interval}s  →  {args.output}")
    mon.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[monitor] Stopping …")
        mon.stop()
        print("[monitor] Summary:", mon.summary())
