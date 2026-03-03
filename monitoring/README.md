# Monitoring Module

Performance monitoring, load/stress testing, and visualisation for the threaded chat server.

## Files

| File | Purpose |
|---|---|
| `protocol.py` | Python implementation of the binary chat protocol (mirrors `protocol.h`) |
| `monitor_server.py` | Collects CPU%, VmRSS, PSS for the server process at regular intervals |
| `load_test.py` | Simulates 10 concurrent clients sending messages; measures delivery latency |
| `stress_test.py` | Gradually increases clients (2 → 50) until degradation is detected |
| `visualize.py` | Generates comparison plots (latency distribution, CPU & memory vs clients) |
| `run_all.py` | One-command orchestrator: build → start servers → load test → stress test → plots |

## Quick Start

```bash
cd monitoring/
pip install matplotlib numpy       # only dependencies
python3 run_all.py                 # runs everything
```

## Run Individual Tests

```bash
# Start servers manually first (from project root):
#   ./discovery_server &
#   ./chat_server &

cd monitoring/

# Load test only
python3 load_test.py --clients 10 --messages 20

# Stress test only
python3 stress_test.py --start 2 --step 5 --max 50

# Plots only (after CSVs exist)
python3 visualize.py
```

## Output

All metrics go into `monitoring/metrics/`:

- `load_test_latency.csv` — per-message delivery times
- `load_test_server_metrics.csv` — CPU/memory during load test
- `stress_test_results.csv` — per-step summary (clients, latency, CPU, memory)
- `stress_test_server_metrics.csv` — CPU/memory during stress test
- `plots/message_delivery_time.png` — latency distribution histogram + boxplot
- `plots/cpu_vs_clients.png` — CPU% vs concurrent clients
- `plots/memory_vs_clients.png` — VmRSS/PSS vs concurrent clients

## Adding Fork / Select Server Data

The visualisation scripts are pre-wired for comparison. To add another server type:

1. Run the load/stress tests against that server (save CSVs with different names)
2. Uncomment the corresponding entries in `visualize.py` (`server_types` dicts)
3. Re-run `python3 visualize.py`
