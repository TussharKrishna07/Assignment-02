#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# test_performance.sh — Automated performance test runner
#
# Runs the load test and stress test, generates visualizations,
# and prints a summary report.
#
# Usage:
#   cd Assignment-02/
#   bash tests/test_performance.sh
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MONITORING_DIR="$PROJECT_DIR/monitoring"

green()  { printf "\033[32m%s\033[0m\n" "$*"; }
red()    { printf "\033[31m%s\033[0m\n" "$*"; }
yellow() { printf "\033[33m%s\033[0m\n" "$*"; }

cleanup() {
    pkill -f "discovery_server" 2>/dev/null || true
    pkill -f "chat_server" 2>/dev/null || true
    sleep 0.5
}

wait_for_port() {
    local port=$1 retries=20
    while ! ss -tln | grep -q ":${port} " && [ $retries -gt 0 ]; do
        sleep 0.2
        retries=$((retries - 1))
    done
}

start_servers() {
    rm -f "$PROJECT_DIR/users.txt"
    cleanup

    "$PROJECT_DIR/discovery_server" &>/dev/null &
    wait_for_port 5000
    green "[OK] Discovery server running"

    "$PROJECT_DIR/chat_server" &>/dev/null &
    wait_for_port 6000
    green "[OK] Chat server running"
    sleep 0.5
}

echo ""
echo "============================================================"
echo "     PERFORMANCE TEST SUITE — Chat System"
echo "============================================================"
echo ""

# ── Build ─────────────────────────────────────────────────────────────────────
yellow "── Building project ──"
make -C "$PROJECT_DIR" -j4 > /dev/null 2>&1
green "[OK] Build complete"

# ── Load Test ─────────────────────────────────────────────────────────────────
echo ""
yellow "── Running Load Test (10 clients × 20 messages) ──"
start_servers

cd "$MONITORING_DIR"
python3 load_test.py --clients 10 --messages 20 \
    --output metrics/load_test_latency.csv
LOAD_EXIT=$?
cd "$PROJECT_DIR"

cleanup
sleep 1

if [ $LOAD_EXIT -eq 0 ] && [ -f "$MONITORING_DIR/metrics/load_test_latency.csv" ]; then
    LOAD_LINES=$(wc -l < "$MONITORING_DIR/metrics/load_test_latency.csv")
    green "[OK] Load test completed — $((LOAD_LINES - 1)) latency samples collected"
else
    red "[FAIL] Load test failed"
fi

# ── Stress Test ───────────────────────────────────────────────────────────────
echo ""
yellow "── Running Stress Test (2→50 clients, step 5) ──"
start_servers

cd "$MONITORING_DIR"
python3 stress_test.py --start 2 --step 5 --max 50 --msgs 10 \
    --output metrics/stress_test_results.csv
STRESS_EXIT=$?
cd "$PROJECT_DIR"

cleanup
sleep 1

if [ $STRESS_EXIT -eq 0 ] && [ -f "$MONITORING_DIR/metrics/stress_test_results.csv" ]; then
    STRESS_LINES=$(wc -l < "$MONITORING_DIR/metrics/stress_test_results.csv")
    green "[OK] Stress test completed — $((STRESS_LINES - 1)) steps recorded"
else
    red "[FAIL] Stress test failed"
fi

# ── Generate Plots ────────────────────────────────────────────────────────────
echo ""
yellow "── Generating Visualization Plots ──"
cd "$MONITORING_DIR"
python3 visualize.py --metrics-dir metrics
cd "$PROJECT_DIR"

PLOT_COUNT=$(ls "$MONITORING_DIR/metrics/plots/"*.png 2>/dev/null | wc -l)
green "[OK] Generated $PLOT_COUNT plots in monitoring/metrics/plots/"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "     PERFORMANCE TEST COMPLETE"
echo "============================================================"
echo ""
echo "Output files:"
echo "  monitoring/metrics/load_test_latency.csv"
echo "  monitoring/metrics/load_test_server_metrics.csv"
echo "  monitoring/metrics/stress_test_results.csv"
echo "  monitoring/metrics/stress_test_server_metrics.csv"
echo "  monitoring/metrics/plots/message_delivery_time.png"
echo "  monitoring/metrics/plots/cpu_vs_clients.png"
echo "  monitoring/metrics/plots/memory_vs_clients.png"
echo ""
echo "For detailed analysis, see: performance_analysis.md"
echo ""
