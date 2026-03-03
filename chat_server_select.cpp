// chat_server_select.cpp
// Select-based (single-threaded, multiplexed) chat server — same protocol as threaded version
#include <iostream>
#include <fstream>
#include <vector>
#include <map>
#include <cstring>
#include <algorithm>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <sys/select.h>
#include "protocol.h"

using namespace std;

// ─── Per-client state (replaces per-thread locals) ──────────────────────────
struct ClientState {
    int    fd            = -1;
    bool   authenticated = false;
    string username;
    string read_buf;          // accumulates bytes until a full message is ready
};

map<int, ClientState>       clients;        // fd -> state
map<string, int>            active_clients; // username -> fd
map<string, Userinfo>       total_clients;  // username -> full info

// ─── Load all users from users.txt ──────────────────────────────────────────
void load_users() {
    ifstream ifs("users.txt");
    if (!ifs.is_open()) {
        cerr << "[ERROR] Cannot open users.txt\n";
        return;
    }
    string u, p, ip;
    int port;
    while (ifs >> u >> p >> ip >> port) {
        if (total_clients.find(u) == total_clients.end()) {
            Userinfo info;
            info.username = u;
            info.password = p;
            info.IP       = ip;
            info.port     = port;
            info.active   = 0;
            total_clients[u] = info;
        } else {
            total_clients[u].password = p;
            total_clients[u].IP       = ip;
            total_clients[u].port     = port;
        }
    }
}

// ─── Verify credentials ────────────────────────────────────────────────────
bool verify_user(const string& username, const string& password) {
    load_users();
    if (total_clients.find(username) != total_clients.end() &&
        total_clients[username].password == password) {
        return true;
    }
    return false;
}

// ─── Send a response on a socket ────────────────────────────────────────────
void send_response(int fd, int32_t type, const char* sender,
                   const char* target, const string& payload) {
    MsgHeader hdr{};
    hdr.type           = type;
    hdr.payload_length = payload.size();
    strncpy(hdr.sender, sender, 31);
    strncpy(hdr.target, target, 31);
    write(fd, &hdr,            sizeof(hdr));
    write(fd, payload.c_str(), payload.size());
}

// ─── Remove a client: close socket, clean maps ─────────────────────────────
void remove_client(int fd) {
    if (clients.count(fd)) {
        string uname = clients[fd].username;
        if (!uname.empty()) {
            active_clients.erase(uname);
            if (total_clients.count(uname))
                total_clients[uname].active = 0;
            cout << "[DISCONNECT] " << uname << " left.\n";
        }
        clients.erase(fd);
    }
    close(fd);
}

// ─── Process one complete message from a client ─────────────────────────────
// Returns false if the client should be dropped.
bool process_message(int fd, const MsgHeader& header, const string& payload) {
    ClientState& cs = clients[fd];

    // ── LOGIN ────────────────────────────────────────────────────────────────
    if (header.type == LOGIN) {
        if (verify_user(header.sender, payload)) {
            cs.username      = header.sender;
            cs.authenticated = true;

            active_clients[cs.username] = fd;
            total_clients[cs.username].active = 1;

            send_response(fd, LOGIN, "server", header.sender, "OK");
            cout << "[LOGIN] " << cs.username << " joined.\n";
        } else {
            send_response(fd, LOGIN, "server", header.sender, "FAIL");
            cout << "[LOGIN] Failed attempt for: " << header.sender << "\n";
            return false; // drop
        }
        return true;
    }

    // ── Reject unauthenticated clients beyond this point ─────────────────────
    if (!cs.authenticated) {
        cout << "[WARN] Unauthenticated packet from socket " << fd << "\n";
        return false;
    }

    // ── BROADCAST ────────────────────────────────────────────────────────────
    if (header.type == BROADCAST) {
        cout << "[BROADCAST] " << header.sender << ": " << payload << "\n";
        for (auto const& [name, sock] : active_clients) {
            if (sock != fd) {
                write(sock, &header,         sizeof(header));
                write(sock, payload.c_str(), header.payload_length);
            }
        }
    }

    // ── PRIVATE MSG ──────────────────────────────────────────────────────────
    else if (header.type == PRIVATE_MSG) {
        if (active_clients.count(header.target)) {
            int target_sock = active_clients[header.target];
            write(target_sock, &header,         sizeof(header));
            write(target_sock, payload.c_str(), header.payload_length);
            cout << "[PM] " << header.sender << " -> " << header.target
                 << ": " << payload << "\n";
        } else {
            send_response(fd, PRIVATE_MSG, "server",
                          header.sender, "User not online.");
        }
    }

    // ── QUERY_USER ───────────────────────────────────────────────────────────
    else if (header.type == QUERY_USER) {
        string user_list;
        for (auto const& [name, info] : total_clients)
            user_list += name + " | active: " + to_string(info.active) + "\n";
        if (user_list.empty()) user_list = "(no users registered)";
        send_response(fd, QUERY_USER, "server", header.sender, user_list);
    }

    return true;
}

// ─── Try to extract complete messages from a client's read buffer ───────────
// Multiple messages may have arrived in one read(); handle them all.
void drain_buffer(int fd) {
    ClientState& cs = clients[fd];
    const size_t HDR_SZ = sizeof(MsgHeader);

    while (true) {
        // Need at least a full header
        if (cs.read_buf.size() < HDR_SZ)
            break;

        // Peek at header to learn payload length
        MsgHeader header{};
        memcpy(&header, cs.read_buf.data(), HDR_SZ);

        size_t total_needed = HDR_SZ + header.payload_length;
        if (cs.read_buf.size() < total_needed)
            break; // wait for more data

        // Extract payload
        string payload = cs.read_buf.substr(HDR_SZ, header.payload_length);

        // Consume from buffer
        cs.read_buf.erase(0, total_needed);

        // Process — if it returns false, drop this client
        if (!process_message(fd, header, payload)) {
            remove_client(fd);
            return;
        }
    }
}

// ─── Main ────────────────────────────────────────────────────────────────────
int main() {
    int server_fd = socket(AF_INET, SOCK_STREAM, 0);

    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    sockaddr_in addr{};
    addr.sin_family      = AF_INET;
    addr.sin_port        = htons(6000);
    addr.sin_addr.s_addr = INADDR_ANY;

    if (bind(server_fd, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
        perror("bind");
        return 1;
    }
    if (listen(server_fd, 10) < 0) {
        perror("listen");
        return 1;
    }

    cout << "Select Chat Server active on port 6000...\n";

    load_users();

    char recv_buf[4096];

    while (true) {
        // ── Build fd sets ────────────────────────────────────────────────────
        fd_set read_fds;
        FD_ZERO(&read_fds);
        FD_SET(server_fd, &read_fds);
        int max_fd = server_fd;

        for (auto const& [fd, cs] : clients) {
            FD_SET(fd, &read_fds);
            if (fd > max_fd) max_fd = fd;
        }

        // ── select() — blocks until something is ready ───────────────────────
        int activity = select(max_fd + 1, &read_fds, nullptr, nullptr, nullptr);
        if (activity < 0) {
            if (errno == EINTR) continue;   // interrupted by signal, retry
            perror("select");
            break;
        }

        // ── New incoming connection ──────────────────────────────────────────
        if (FD_ISSET(server_fd, &read_fds)) {
            sockaddr_in cli_addr{};
            socklen_t cli_len = sizeof(cli_addr);
            int new_fd = accept(server_fd, (struct sockaddr*)&cli_addr, &cli_len);
            if (new_fd >= 0) {
                load_users();
                clients[new_fd] = ClientState{new_fd, false, "", ""};
                cout << "[NEW] Connection from "
                     << inet_ntoa(cli_addr.sin_addr) << ":"
                     << ntohs(cli_addr.sin_port)
                     << " (fd " << new_fd << ")\n";
            }
        }

        // ── Data from existing clients ───────────────────────────────────────
        // Collect fds first — iteration over `clients` can change during drain
        vector<int> ready_fds;
        for (auto const& [fd, cs] : clients) {
            if (FD_ISSET(fd, &read_fds))
                ready_fds.push_back(fd);
        }

        for (int fd : ready_fds) {
            // Client may have been removed by a previous drain in this loop
            if (!clients.count(fd)) continue;

            ssize_t n = read(fd, recv_buf, sizeof(recv_buf));
            if (n <= 0) {
                // Disconnected or error
                remove_client(fd);
                continue;
            }

            clients[fd].read_buf.append(recv_buf, n);
            drain_buffer(fd);
        }
    }

    close(server_fd);
    return 0;
}
