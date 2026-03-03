#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# test_functional.sh — Automated functional tests for the chat system
#
# Tests:
#   1. Server startup (discovery + chat)
#   2. User registration via discovery server
#   3. Login to chat server
#   4. Broadcast messaging between two clients
#   5. Private messaging between two clients
#   6. User query listing
#   7. Concurrent multi-client connections
#   8. Invalid login rejection
#   9. Graceful disconnect handling
#
# Usage:
#   cd Assignment-02/
#   bash tests/test_functional.sh
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0
TOTAL=0

# ── Helpers ───────────────────────────────────────────────────────────────────

green()  { printf "\033[32m%s\033[0m\n" "$*"; }
red()    { printf "\033[31m%s\033[0m\n" "$*"; }
yellow() { printf "\033[33m%s\033[0m\n" "$*"; }

assert_ok() {
    TOTAL=$((TOTAL + 1))
    if [ "$1" -eq 0 ]; then
        green "  [PASS] $2"
        PASS=$((PASS + 1))
    else
        red   "  [FAIL] $2"
        FAIL=$((FAIL + 1))
    fi
}

cleanup() {
    pkill -f "discovery_server" 2>/dev/null || true
    pkill -f "chat_server" 2>/dev/null || true
    rm -f "$PROJECT_DIR/users.txt"
    sleep 0.5
}

wait_for_port() {
    local port=$1 retries=20
    while ! ss -tln | grep -q ":${port} " && [ $retries -gt 0 ]; do
        sleep 0.2
        retries=$((retries - 1))
    done
    ss -tln | grep -q ":${port} "
}

# Python helper: register a user via the protocol
py_register() {
    python3 -c "
import sys; sys.path.insert(0, '$PROJECT_DIR/monitoring')
from protocol import register_user
ok = register_user('$1', '$2')
sys.exit(0 if ok else 1)
"
}

# Python helper: login and optionally send a message, return the response
py_login_and_send() {
    local user=$1 passwd=$2 msg_type=$3 target=$4 message=$5
    python3 -c "
import sys, socket, time
sys.path.insert(0, '$PROJECT_DIR/monitoring')
from protocol import register_user, login_user, send_broadcast, send_private, recv_message, BROADCAST, PRIVATE_MSG, QUERY_USER

# Register first
register_user('$user', '$passwd')
sock = login_user('$user', '$passwd')
if sock is None:
    print('LOGIN_FAILED')
    sys.exit(1)

msg_type = $msg_type
if msg_type == BROADCAST:
    send_broadcast(sock, '$user', '$message')
elif msg_type == PRIVATE_MSG:
    send_private(sock, '$user', '$target', '$message')
elif msg_type == QUERY_USER:
    from protocol import pack_header
    sock.sendall(pack_header(QUERY_USER, b'', '$user', ''))

time.sleep(0.5)
sock.close()
print('OK')
"
}

# Python helper: login and listen for a message
py_listen() {
    local user=$1 passwd=$2 timeout=$3
    python3 -c "
import sys, socket, time
sys.path.insert(0, '$PROJECT_DIR/monitoring')
from protocol import register_user, login_user, recv_message

register_user('$user', '$passwd')
sock = login_user('$user', '$passwd')
if sock is None:
    print('LOGIN_FAILED')
    sys.exit(1)

sock.settimeout($timeout)
try:
    msg_type, sender, target, payload = recv_message(sock)
    print(f'RECEIVED:{sender}:{payload}')
except socket.timeout:
    print('TIMEOUT')
except Exception as e:
    print(f'ERROR:{e}')
finally:
    sock.close()
"
}

# ── Setup ─────────────────────────────────────────────────────────────────────

echo ""
echo "============================================================"
echo "     FUNCTIONAL TEST SUITE — Chat System"
echo "============================================================"
echo ""

cleanup

# Build
echo "── Building project ──"
make -C "$PROJECT_DIR" -j4 > /dev/null 2>&1
assert_ok $? "Project builds successfully"

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 1: Server Startup
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
yellow "── Test 1: Server Startup ──"

"$PROJECT_DIR/discovery_server" &>/dev/null &
DISC_PID=$!
sleep 0.5
wait_for_port 5000
assert_ok $? "Discovery server starts on port 5000"

"$PROJECT_DIR/chat_server" &>/dev/null &
CHAT_PID=$!
sleep 0.5
wait_for_port 6000
assert_ok $? "Chat server starts on port 6000"

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 2: User Registration
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
yellow "── Test 2: User Registration ──"

py_register "testuser1" "pass1"
assert_ok $? "User 'testuser1' registers successfully"

py_register "testuser2" "pass2"
assert_ok $? "User 'testuser2' registers successfully"

grep -q "testuser1" "$PROJECT_DIR/users.txt"
assert_ok $? "User 'testuser1' exists in users.txt"

grep -q "testuser2" "$PROJECT_DIR/users.txt"
assert_ok $? "User 'testuser2' exists in users.txt"

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 3: Login Authentication
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
yellow "── Test 3: Login Authentication ──"

result=$(python3 -c "
import sys; sys.path.insert(0, '$PROJECT_DIR/monitoring')
from protocol import login_user
sock = login_user('testuser1', 'pass1')
if sock: print('OK'); sock.close()
else: print('FAIL')
")
[ "$result" = "OK" ]
assert_ok $? "Valid login succeeds"

result=$(python3 -c "
import sys; sys.path.insert(0, '$PROJECT_DIR/monitoring')
from protocol import register_user, login_user
register_user('baduser', 'goodpass')
sock = login_user('baduser', 'wrongpass')
if sock: print('OK'); sock.close()
else: print('FAIL')
" 2>/dev/null)
[ "$result" = "FAIL" ]
assert_ok $? "Login with wrong password is rejected"

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 4: Broadcast Messaging
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
yellow "── Test 4: Broadcast Messaging ──"

# Start a listener in background
py_listen "testuser2" "pass2" "5" > /tmp/chat_test_recv.txt 2>/dev/null &
LISTEN_PID=$!
sleep 1

# Send broadcast from testuser1
py_login_and_send "testuser1" "pass1" "3" "all" "Hello broadcast test"
sleep 1

wait $LISTEN_PID 2>/dev/null || true
RECV_RESULT=$(cat /tmp/chat_test_recv.txt)

echo "$RECV_RESULT" | grep -q "RECEIVED:testuser1:Hello broadcast test"
assert_ok $? "Broadcast message delivered to other client"
rm -f /tmp/chat_test_recv.txt

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 5: Private Messaging
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
yellow "── Test 5: Private Messaging ──"

# Re-register users (discovery server appends, chat server reloads)
py_register "pmuser1" "pass1"
py_register "pmuser2" "pass2"
sleep 0.3

# Start listener
py_listen "pmuser2" "pass2" "5" > /tmp/chat_test_pm.txt 2>/dev/null &
LISTEN_PID=$!
sleep 1

# Send private message
py_login_and_send "pmuser1" "pass1" "4" "pmuser2" "Secret message"
sleep 1

wait $LISTEN_PID 2>/dev/null || true
PM_RESULT=$(cat /tmp/chat_test_pm.txt)

echo "$PM_RESULT" | grep -q "RECEIVED:pmuser1:Secret message"
assert_ok $? "Private message delivered to target user"
rm -f /tmp/chat_test_pm.txt

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 6: User Query
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
yellow "── Test 6: User Query ──"

result=$(python3 -c "
import sys, time
sys.path.insert(0, '$PROJECT_DIR/monitoring')
from protocol import register_user, login_user, pack_header, recv_message, QUERY_USER

register_user('queryuser', 'pass')
sock = login_user('queryuser', 'pass')
if not sock:
    print('LOGIN_FAILED')
    sys.exit(1)
sock.settimeout(3)
sock.sendall(pack_header(QUERY_USER, b'', 'queryuser', ''))
_, _, _, payload = recv_message(sock)
sock.close()
print(payload)
" 2>/dev/null)

echo "$result" | grep -q "queryuser"
assert_ok $? "User query returns user list including self"

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 7: Concurrent Connections
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
yellow "── Test 7: Concurrent Connections ──"

CONCURRENT_OK=0
for i in $(seq 1 5); do
    python3 -c "
import sys; sys.path.insert(0, '$PROJECT_DIR/monitoring')
from protocol import register_user, login_user
register_user('concuser$i', 'pass')
sock = login_user('concuser$i', 'pass')
if sock: sock.close(); sys.exit(0)
sys.exit(1)
" 2>/dev/null && CONCURRENT_OK=$((CONCURRENT_OK + 1)) &
done
wait

[ "$CONCURRENT_OK" -ge 4 ]
assert_ok $? "At least 4 out of 5 concurrent clients connect successfully"

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 8: Server Handles Disconnect
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
yellow "── Test 8: Disconnect Handling ──"

python3 -c "
import sys; sys.path.insert(0, '$PROJECT_DIR/monitoring')
from protocol import register_user, login_user
register_user('disconn_user', 'pass')
sock = login_user('disconn_user', 'pass')
if sock: sock.close()
" 2>/dev/null
sleep 0.5

# Verify servers are still running
kill -0 $DISC_PID 2>/dev/null
assert_ok $? "Discovery server survives client disconnect"
kill -0 $CHAT_PID 2>/dev/null
assert_ok $? "Chat server survives client disconnect"

# ═══════════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "============================================================"
echo "     RESULTS: $PASS passed / $FAIL failed / $TOTAL total"
echo "============================================================"
echo ""

cleanup

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
