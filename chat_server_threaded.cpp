// chat_server_threaded.cpp
#include <iostream>
#include <fstream>
#include <thread>
#include <vector>
#include <map>
#include <mutex>
#include <cstring>
#include <netinet/in.h>
#include <unistd.h>
#include "protocol.h"

using namespace std;

map<string, int> active_clients; // Username -> Socket
map<string,Userinfo>total_clients;
mutex clients_mtx;

// ─── Load all users from users.txt into total_clients map ────────────────────
void load_users() {
    ifstream ifs("users.txt");
    if (!ifs.is_open()) {
        cerr << "[ERROR] Cannot open users.txt\n";
        return;
    }
    string u, p, ip;
    int port;
    while (ifs >> u >> p >> ip >> port) {
        // Only add new users; preserve active status of existing ones
        if (total_clients.find(u) == total_clients.end()) {
            Userinfo info;
            info.username = u;
            info.password = p;
            info.IP       = ip;
            info.port     = port;
            info.active   = 0;
            total_clients[u] = info;
        } else {
            // Update credentials/ip/port but keep active status
            total_clients[u].password = p;
            total_clients[u].IP       = ip;
            total_clients[u].port     = port;
        }
    }
}

// ─── Verify credentials against the total_clients map ────────────────────────
bool verify_user(const string& username, const string& password) {
    load_users();  // Reload to pick up newly registered users (preserves active status)
    if (total_clients.find(username) != total_clients.end() &&
        total_clients[username].password == password) {
        return true;
    }
    return false;
}

// ─── Send a text response back to a single socket ───────────────────────────
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

// ─── Per-client thread ───────────────────────────────────────────────────────
void handle_client(int client_socket) {
    MsgHeader header{};
    bool authenticated = false;
    string my_username;

    while (read(client_socket, &header, sizeof(header)) > 0) {

        // Read payload
        char* payload = new char[header.payload_length + 1]{};
        if (header.payload_length > 0)
            read(client_socket, payload, header.payload_length);

        // ── LOGIN ────────────────────────────────────────────────────────────
        if (header.type == LOGIN) {
            if (verify_user(header.sender, payload)) {
                my_username = header.sender;
                authenticated = true;

                {
                    lock_guard<mutex> lock(clients_mtx);
                    active_clients[my_username] = client_socket;
                    total_clients[my_username].active = 1;
                }

                send_response(client_socket, LOGIN, "server", header.sender, "OK");
                cout << "[LOGIN] " << my_username << " joined.\n";

            } else {
                send_response(client_socket, LOGIN, "server", header.sender, "FAIL");
                cout << "[LOGIN] Failed attempt for: " << header.sender << "\n";
                delete[] payload;
                close(client_socket);
                return;
            }
        }

        // ── Reject unauthenticated clients beyond this point ─────────────────
        else if (!authenticated) {
            cout << "[WARN] Unauthenticated packet from socket " << client_socket << "\n";
            delete[] payload;
            close(client_socket);
            return;
        }

        // ── BROADCAST ────────────────────────────────────────────────────────
        else if (header.type == BROADCAST) {
            cout << "[BROADCAST] " << header.sender << ": " << payload << "\n";
            lock_guard<mutex> lock(clients_mtx);
            for (auto const& [name, sock] : active_clients) {
                if (sock != client_socket) {
                    write(sock, &header, sizeof(header));
                    write(sock, payload, header.payload_length);
                }
            }
        }

        // ── PRIVATE MSG ──────────────────────────────────────────────────────
        else if (header.type == PRIVATE_MSG) {
            lock_guard<mutex> lock(clients_mtx);
            if (active_clients.count(header.target)) {
                int target_sock = active_clients[header.target];
                write(target_sock, &header,  sizeof(header));
                write(target_sock, payload,  header.payload_length);
                cout << "[PM] " << header.sender << " -> " << header.target << ": " << payload << "\n";
            } else {
                send_response(client_socket, PRIVATE_MSG, "server",
                              header.sender, "User not online.");
            }
        }

        // ── QUERY_USER ───────────────────────────────────────────────────────
        else if (header.type == QUERY_USER) {
            string user_list;
            {
                lock_guard<mutex> lock(clients_mtx);
                for (auto const& [name, info] : total_clients)
                    user_list += name + " | active: " + to_string(info.active) + "\n";
            }
            if (user_list.empty()) user_list = "(no users registered)";
            send_response(client_socket, QUERY_USER, "server", header.sender, user_list);
        }

        delete[] payload;
    }

    // ── Cleanup on disconnect ────────────────────────────────────────────────
    if (!my_username.empty()) {
        lock_guard<mutex> lock(clients_mtx);
        active_clients.erase(my_username);
        total_clients[my_username].active = 0;
        cout << "[DISCONNECT] " << my_username << " left.\n";
    }
    close(client_socket);
}

// ─── Main ────────────────────────────────────────────────────────────────────
int main() {
    int server_fd = socket(AF_INET, SOCK_STREAM, 0);

    // Allow port reuse (avoids "Address already in use" on restart)
    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    sockaddr_in addr{};
    addr.sin_family      = AF_INET;
    addr.sin_port        = htons(6000);
    addr.sin_addr.s_addr = INADDR_ANY;

    bind(server_fd,   (struct sockaddr*)&addr, sizeof(addr));
    listen(server_fd, 10);

    cout << "Threaded Chat Server active on port 6000...\n";
    while (true) {
        int client_fd = accept(server_fd, nullptr, nullptr);
        load_users();
        thread(handle_client, client_fd).detach();
    }
}