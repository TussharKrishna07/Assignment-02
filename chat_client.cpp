// chat_client.cpp
#include <iostream>
#include <fstream>
#include <string>
#include <cstring>
#include <thread>
#include <atomic>
#include <arpa/inet.h>
#include <unistd.h>
#include "protocol.h"
using namespace std;

#define DISCOVERY_IP   "127.0.0.1"
#define DISCOVERY_PORT 5000
#define CHAT_PORT      6000

atomic<bool> running(true); // shared flag to stop receiver thread on quit

// ─── Helpers ─────────────────────────────────────────────────────────────────

int connect_to(const char* ip, int port) {
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port   = htons(port);
    inet_pton(AF_INET, ip, &addr.sin_addr);
    if (connect(fd, (struct sockaddr*)&addr, sizeof(addr)) < 0) return -1;
    return fd;
}

void send_message(int fd, int32_t type,
                  const char* sender, const char* target,
                  const char* payload) {
    MsgHeader header{};
    header.type           = type;
    header.payload_length = strlen(payload);
    strncpy(header.sender, sender, 31);
    strncpy(header.target, target, 31);
    write(fd, &header,  sizeof(header));
    write(fd, payload,  header.payload_length);
}

string read_response(int fd) {
    MsgHeader header{};
    if (read(fd, &header, sizeof(header)) <= 0) return "";
    if (header.payload_length <= 0) return "";
    char buffer[header.payload_length + 1];
    memset(buffer, 0, header.payload_length + 1);
    read(fd, buffer, header.payload_length);
    return string(buffer);
}

// ─── Background receiver thread ──────────────────────────────────────────────
// Sits in a loop reading from chat_fd and printing anything that arrives
void receive_messages(int chat_fd) {
    while (running) {
        MsgHeader header{};
        int n = read(chat_fd, &header, sizeof(header));
        if (n <= 0) {
            if (running) cout << "\n[SERVER DISCONNECTED]\n";
            running = false;
            break;
        }

        char buffer[header.payload_length + 1];
        memset(buffer, 0, header.payload_length + 1);
        if (header.payload_length > 0)
            read(chat_fd, buffer, header.payload_length);

        // Print differently based on message type
        if (header.type == BROADCAST) {
            cout << "\n[" << header.sender << " -> ALL]: " << buffer << "\n> ";
        } else if (header.type == PRIVATE_MSG) {
            cout << "\n[" << header.sender << " -> YOU]: " << buffer << "\n> ";
        } else {
            // Generic server message (errors, notifications etc.)
            cout << "\n[SERVER]: " << buffer << "\n> ";
        }

        cout.flush(); // make sure it prints immediately
    }
}

// ─── Operations ──────────────────────────────────────────────────────────────

bool register_with_discovery(const string& username, const string& password) {
    int fd = connect_to(DISCOVERY_IP, DISCOVERY_PORT);
    if (fd < 0) { cerr << "[ERROR] Cannot reach discovery server.\n"; return false; }
    send_message(fd, REGISTRATION, username.c_str(), "", password.c_str());
    cout << "[OK] Registered '" << username << "' with discovery server.\n";
    close(fd);
    return true;
}

int login_to_chat(const string& username, const string& password) {
    int fd = connect_to(DISCOVERY_IP, CHAT_PORT);
    if (fd < 0) { cerr << "[ERROR] Cannot reach chat server.\n"; return -1; }
    send_message(fd, LOGIN, username.c_str(), "", password.c_str());
    string response = read_response(fd);
    if (response.find("OK") != string::npos) {
        cout << "[OK] Logged into chat server.\n";
        return fd;
    }
    cerr << "[FAILED] Login rejected: " << response << "\n";
    close(fd);
    return -1;
}

void send_broadcast(int chat_fd, const string& username, const string& message) {
    send_message(chat_fd, BROADCAST, username.c_str(), "all", message.c_str());
}

void send_private(int chat_fd, const string& username,
                  const string& target, const string& message) {
    send_message(chat_fd, PRIVATE_MSG, username.c_str(), target.c_str(), message.c_str());
}

void query_users(const string& username) {
    int fd = connect_to(DISCOVERY_IP, DISCOVERY_PORT);
    if (fd < 0) { cerr << "[ERROR] Cannot reach discovery server.\n"; return; }
    send_message(fd, QUERY_USER, username.c_str(), "", "");
    string response = read_response(fd);
    cout << "\n── Online Users ──\n" << response << "──────────────────\n";
    close(fd);
}

// ─── Main ────────────────────────────────────────────────────────────────────

int main() {
    string username, password;

    cout << "=== Chat Client ===\n";
    cout << "Username: "; cin >> username;
    cout << "Password: "; cin >> password;
    cin.ignore();

    if (!register_with_discovery(username, password)) return 1;

    int chat_fd = login_to_chat(username, password);
    if (chat_fd < 0) return 1;

    // ── Spawn receiver thread — runs in background the entire session ─────────
    thread receiver(receive_messages, chat_fd);
    receiver.detach();

    cout << "\nCommands:\n"
         << "  /all <message>        — broadcast to everyone\n"
         << "  /msg <user> <message> — private message\n"
         << "  /users                — list online users\n"
         << "  /quit                 — exit\n\n";

    string line;
    while (running) {
        cout << "> ";
        getline(cin, line);
        if (line.empty()) continue;

        if (line == "/quit") {
            running = false;
            cout << "Goodbye!\n";
            break;

        } else if (line.substr(0, 4) == "/all") {
            string message = line.length() > 5 ? line.substr(5) : "";
            if (message.empty()) { cout << "Usage: /all <message>\n"; continue; }
            send_broadcast(chat_fd, username, message);

        } else if (line.substr(0, 4) == "/msg") {
            size_t first_space = line.find(' ', 5);
            if (first_space == string::npos) { cout << "Usage: /msg <user> <message>\n"; continue; }
            string target  = line.substr(5, first_space - 5);
            string message = line.substr(first_space + 1);
            if (target.empty() || message.empty()) { cout << "Usage: /msg <user> <message>\n"; continue; }
            send_private(chat_fd, username, target, message);

        } else if (line == "/users") {
            query_users(username);

        } else {
            cout << "Unknown command.\n";
        }
    }

    close(chat_fd);
    return 0;
}