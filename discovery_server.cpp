// discovery_server.cpp (Updated)
#include <iostream>
#include <fstream>
#include <string>
#include <cstring>
#include <arpa/inet.h>
#include <unistd.h>
#include "protocol.h"

using namespace std;

int main() {
    int server_fd = socket(AF_INET, SOCK_STREAM, 0);
    sockaddr_in addr = {AF_INET, htons(5000), {INADDR_ANY}};
    bind(server_fd, (struct sockaddr*)&addr, sizeof(addr));
    listen(server_fd, 5);

    cout << "Discovery Server (DNS) active on port 5000...\n";
    sockaddr_in client_address;
    socklen_t client_len = sizeof(client_address);

    while (true) {
        int client_fd = accept(server_fd, (struct sockaddr*)&client_address, &client_len);

        // Extract client IP and port
        char client_ip[INET_ADDRSTRLEN];
        inet_ntop(AF_INET, &client_address.sin_addr, client_ip, INET_ADDRSTRLEN);
        int client_port = ntohs(client_address.sin_port);

        MsgHeader header;
        read(client_fd, &header, sizeof(header));

        if (header.type == REGISTRATION) {
            char buffer[header.payload_length + 1];
            memset(buffer, 0, header.payload_length + 1);
            read(client_fd, buffer, header.payload_length);

            // Store: username password IP port
            ofstream ofs("users.txt", ios::app);
            ofs << header.sender << " " << buffer << " " << client_ip << " " << client_port << "\n";
            ofs.close();

            cout << "Registered: " << header.sender
                 << " | IP: "      << client_ip
                 << " | Port: "    << client_port << "\n";
        }
        close(client_fd);
    }
}