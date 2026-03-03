# Multi-User Chat System with Discovery Server

A TCP-based multi-user chat application built in C++ featuring a discovery server for user registration, a multi-threaded chat server for real-time messaging, and an interactive command-line client. Includes a comprehensive Python-based performance monitoring and testing suite.

---

## Table of Contents

1. [System Architecture Overview](#system-architecture-overview)
2. [Protocol Specification](#protocol-specification)
3. [Compilation and Execution Instructions](#compilation-and-execution-instructions)
4. [Testing Guide](#testing-guide)

---

## System Architecture Overview

The system follows a **three-tier client-server architecture** with the following components:

```
┌─────────────┐         ┌────────────────────┐         ┌────────────────────────┐
│  Chat Client │◄───────►│  Discovery Server   │         │  Threaded Chat Server  │
│  (N clients) │  TCP    │  (Port 5000)        │         │  (Port 6000)           │
│              │─ ─ ─ ─ ─│  - User registration│         │  - Authentication      │
│  chat_client │         │  - Credential store  │         │  - Broadcast messaging │
│              │◄───────►│                      │         │  - Private messaging   │
└─────────────┘  TCP    └────────────────────┘         │  - User query          │
       │                                                │  - Thread-per-client   │
       │                                                │                        │
       └───────────────────── TCP ─────────────────────►│                        │
                                                        └────────────────────────┘
```

### Component Details

#### 1. Discovery Server (`discovery_server.cpp` — Port 5000)
- **Role**: Acts as a name/registration service (analogous to DNS).
- Listens on TCP port 5000 for incoming registration requests.
- On receiving a `REGISTRATION` message, stores user credentials (`username`, `password`, `IP`, `port`) to `users.txt`.
- Sends an `OK` confirmation back to the client upon successful registration.
- Runs in a **single-threaded, iterative** loop (one connection at a time).

#### 2. Threaded Chat Server (`chat_server_threaded.cpp` — Port 6000)
- **Role**: Central relay for all chat communication.
- Listens on TCP port 6000 and spawns a **detached thread** for each connecting client (`thread-per-client` model).
- Loads user credentials from `users.txt` (written by the discovery server) to authenticate login requests.
- Supports:
  - **Login** — verifies credentials against the user store.
  - **Broadcast** — relays a message to all connected clients (except the sender).
  - **Private Message** — delivers a message to a specific online user.
  - **User Query** — returns a list of all registered users with their active/inactive status.
- Uses a `std::mutex` to protect the shared `active_clients` map from race conditions across threads.

#### 3. Chat Client (`chat_client.cpp`)
- **Role**: Interactive user-facing terminal application.
- Workflow:
  1. Registers with the discovery server (port 5000).
  2. Logs in to the chat server (port 6000).
  3. Spawns a background **receiver thread** to asynchronously print incoming messages.
  4. Reads user commands from `stdin` in the main thread.
- Supported commands:
  - `/all <message>` — Broadcast to all online users.
  - `/msg <user> <message>` — Send a private message.
  - `/users` — List all registered users and their status.
  - `/quit` — Disconnect and exit.

### Data Flow

```
Registration:   Client ──REGISTRATION──► Discovery Server ──"OK"──► Client
Login:          Client ──LOGIN──────────► Chat Server ──"OK"/"FAIL"─► Client
Broadcast:      Client ──BROADCAST──────► Chat Server ──(relay)─────► All other clients
Private Msg:    Client ──PRIVATE_MSG────► Chat Server ──(forward)───► Target client
User Query:     Client ──QUERY_USER─────► Chat Server ──(user list)─► Client
```

---

## Protocol Specification

All communication uses a **custom binary protocol** over TCP sockets, defined in `protocol.h`.

### Message Types

| Code | Enum Name      | Direction                    | Description                          |
|------|----------------|------------------------------|--------------------------------------|
| 1    | `REGISTRATION` | Client → Discovery Server    | Register a new user account          |
| 2    | `LOGIN`        | Client → Chat Server         | Authenticate with credentials        |
| 3    | `BROADCAST`    | Client → Chat Server → All   | Send message to all online users     |
| 4    | `PRIVATE_MSG`  | Client → Chat Server → User  | Send message to a specific user      |
| 5    | `QUERY_USER`   | Client → Chat Server         | Request list of registered users     |
| 6    | `STATUS_UPDATE`| Client → Chat Server         | Change user status (reserved)        |

### Packet Format

Every packet consists of a **fixed-size header** followed by a **variable-length payload**.

```
┌──────────────────────────────────────────────────────────────────┐
│                        MsgHeader (72 bytes)                      │
├─────────────┬─────────────────┬──────────────┬──────────────────┤
│  type       │  payload_length │    sender    │     target       │
│  (int32_t)  │  (int32_t)      │  (char[32])  │  (char[32])      │
│  4 bytes    │  4 bytes        │  32 bytes    │  32 bytes        │
├─────────────┴─────────────────┴──────────────┴──────────────────┤
│                     Payload (variable length)                    │
│               Length = payload_length bytes                      │
└──────────────────────────────────────────────────────────────────┘
```

### Header Fields

| Field            | Type       | Size     | Description                                      |
|------------------|------------|----------|--------------------------------------------------|
| `type`           | `int32_t`  | 4 bytes  | Message type enum (1–6)                           |
| `payload_length` | `int32_t`  | 4 bytes  | Length of the payload in bytes                    |
| `sender`         | `char[32]` | 32 bytes | Null-padded username of the sender                |
| `target`         | `char[32]` | 32 bytes | Null-padded username of the recipient (if applicable) |

### Payload Content by Message Type

| Message Type     | Payload Content                              |
|------------------|----------------------------------------------|
| `REGISTRATION`   | Password (plaintext string)                  |
| `LOGIN`          | Password (plaintext string)                  |
| `BROADCAST`      | Message text                                 |
| `PRIVATE_MSG`    | Message text                                 |
| `QUERY_USER`     | Empty (request); User list string (response) |
| `STATUS_UPDATE`  | New status string                            |

### User Store (`users.txt`)

The discovery server persists user data as a flat text file with space-separated fields:

```
<username> <password> <IP> <port>
```

Example:
```
alice pass123 127.0.0.1 54321
bob   secret  127.0.0.1 54322
```

---

## Compilation and Execution Instructions

### Prerequisites

- **Compiler**: g++ with C++17 support
- **OS**: Linux (uses POSIX sockets and `/proc` filesystem for monitoring)
- **Python 3.10+** (for test/monitoring suite)
- **Python packages**: `matplotlib`, `numpy` (for visualization only)

### Building

```bash
cd /path/to/Assignment-02

# Build all binaries
make

# This produces:
#   discovery_server
#   chat_server       (compiled from chat_server_threaded.cpp)
#   chat_client
```

To clean build artifacts:
```bash
make clean
```

### Running the System

**Step 1 — Start the Discovery Server:**
```bash
./discovery_server &
# Output: Discovery Server (DNS) active on port 5000...
```

**Step 2 — Start the Chat Server:**
```bash
./chat_server &
# Output: Threaded Chat Server active on port 6000...
```

**Step 3 — Start Chat Clients** (in separate terminals):
```bash
./chat_client
# Prompts for username and password, then opens interactive chat
```

### Client Usage

```
=== Chat Client ===
Username: alice
Password: pass123

Commands:
  /all <message>        — broadcast to everyone
  /msg <user> <message> — private message
  /users                — list online users
  /quit                 — exit

> /all Hello everyone!
> /msg bob Hey Bob, are you there?
> /users
> /quit
```

### Stopping Servers

```bash
pkill -f discovery_server
pkill -f chat_server
```

---

## Testing Guide

### Testing Suite Overview

The `monitoring/` directory contains a full Python-based test and monitoring framework:

| File               | Purpose                                                       |
|--------------------|---------------------------------------------------------------|
| `protocol.py`      | Python implementation of the binary protocol (mirrors `protocol.h`) |
| `monitor_server.py`| Collects CPU%, VmRSS, PSS for the server process at intervals |
| `load_test.py`     | Simulates 10 concurrent clients sending 20 messages each      |
| `stress_test.py`   | Gradually increases clients (2 → 50) to find degradation      |
| `visualize.py`     | Generates plots (latency distribution, CPU & memory vs clients)|
| `run_all.py`       | One-command orchestrator: build → servers → tests → plots     |

### Quick Start — Run All Tests

```bash
cd monitoring/
pip install matplotlib numpy    # install dependencies (one-time)
python3 run_all.py              # builds, starts servers, runs all tests, generates plots
```

### Running Individual Tests

First, start the servers manually from the project root:
```bash
./discovery_server &
./chat_server &
```

Then run specific tests:

```bash
cd monitoring/

# Load Test — 10 clients, 20 messages each
python3 load_test.py --clients 10 --messages 20

# Stress Test — scale from 2 to 50 clients
python3 stress_test.py --start 2 --step 5 --max 50 --msgs 10

# Generate plots from existing CSV data
python3 visualize.py

# Monitor server resources standalone
python3 monitor_server.py --pid $(pgrep -f chat_server | head -1) --interval 2
```

### Test Descriptions

#### Load Test (`load_test.py`)
- Spawns N concurrent clients that register, log in, and send broadcast messages.
- All clients synchronize at a barrier before sending to ensure simultaneous load.
- Measures **per-message delivery latency** (time from send to receiving a broadcast echo).
- Monitors server CPU and memory consumption during the test.
- **Output**: `metrics/load_test_latency.csv`, `metrics/load_test_server_metrics.csv`

#### Stress Test (`stress_test.py`)
- Incrementally increases client count in steps (default: 2, 7, 12, …, 47).
- At each step, every client sends a configurable number of broadcast messages.
- Measures: connection success rate, avg/max/p95 latency, CPU%, memory.
- Automatically stops if **degradation** is detected (>50% failed connections or latency >5s).
- **Output**: `metrics/stress_test_results.csv`, `metrics/stress_test_server_metrics.csv`

#### Visualization (`visualize.py`)
Generates three plots saved to `metrics/plots/`:
1. **`message_delivery_time.png`** — Histogram + boxplot of delivery latencies.
2. **`cpu_vs_clients.png`** — Server CPU usage as concurrent clients increase.
3. **`memory_vs_clients.png`** — Server VmRSS and PSS as clients increase.

### Test Output Structure

```
monitoring/metrics/
├── load_test_latency.csv            # Per-message latency data
├── load_test_server_metrics.csv     # CPU/memory during load test
├── stress_test_results.csv          # Per-step stress test summary
├── stress_test_server_metrics.csv   # CPU/memory during stress test
└── plots/
    ├── message_delivery_time.png    # Latency distribution
    ├── cpu_vs_clients.png           # CPU vs. client count
    └── memory_vs_clients.png        # Memory vs. client count
```

### Manual Functional Testing

You can manually test the system with multiple terminal windows:

```bash
# Terminal 1 — Discovery Server
./discovery_server

# Terminal 2 — Chat Server
./chat_server

# Terminal 3 — Client A
./chat_client
# Enter: alice / pass1

# Terminal 4 — Client B
./chat_client
# Enter: bob / pass2

# In Client A: /all Hello from Alice!
# Client B should receive: [alice -> ALL]: Hello from Alice!

# In Client B: /msg alice Private reply
# Client A should receive: [bob -> YOU]: Private reply

# In either: /users
# Should list both alice and bob as active
```
