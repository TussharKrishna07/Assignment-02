// chat_server_threaded.cpp
#include <iostream>
#include <fstream>
#include <thread>
#include <vector>
#include <map>
#include <mutex>
#include <netinet/in.h>
#include <unistd.h>
#include "protocol.h"

std::map<std::string, int> active_clients; // Username -> Socket
std::mutex clients_mtx;

bool verify_user(std::string username, std::string password) {
    std::ifstream ifs("users.txt");
    std::string u, p;
    while (ifs >> u >> p) {
        if (u == username && p == password) return true;
    }
    return false;
}

void handle_client(int client_socket) {
    MsgHeader header;
    bool authenticated = false;
    while (read(client_socket, &header, sizeof(header)) > 0) {
        char* payload = new char[header.payload_length + 1]{0};
        read(client_socket, payload, header.payload_length);

        

        std::lock_guard<std::mutex> lock(clients_mtx);
        
        if (header.type == LOGIN) {
            if (verify_user(header.sender, payload)) {
                std::lock_guard<std::mutex> lock(clients_mtx);
                active_clients[header.sender] = client_socket;
                authenticated = true;
                std::cout << header.sender << " authenticated and joined.\n";
            } else {
                // Send an error "packet" back (using a custom type or length 0)
                MsgHeader error_hdr = {LOGIN, 0}; 
                write(client_socket, &error_hdr, sizeof(error_hdr));
                std::cout << "Failed login attempt for: " << header.sender << "\n";
                close(client_socket);
                return;
            }
        }

        else if (header.type == BROADCAST) {
            for (auto const& [name, sock] : active_clients) {
                if (sock != client_socket) {
                    write(sock, &header, sizeof(header));
                    write(sock, payload, header.payload_length);
                }
            }
        }
        else if (header.type == PRIVATE_MSG) {
            if (active_clients.count(header.target)) {
                int target_sock = active_clients[header.target];
                write(target_sock, &header, sizeof(header));
                write(target_sock, payload, header.payload_length);
            }
        }
        delete[] payload;
    }
    // Cleanup on disconnect
    close(client_socket);
}

int main() {
    int server_fd = socket(AF_INET, SOCK_STREAM, 0);
    sockaddr_in addr = {AF_INET, htons(6000), INADDR_ANY};
    bind(server_fd, (struct sockaddr*)&addr, sizeof(addr));
    listen(server_fd, 10);

    std::cout << "Threaded Chat Server active on port 6000...\n";

    while (true) {
        int client_fd = accept(server_fd, nullptr, nullptr);
        std::thread(handle_client, client_fd).detach(); // One thread per client
    }
}