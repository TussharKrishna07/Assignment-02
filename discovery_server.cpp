// discovery_server.cpp (Updated)
#include <iostream>
#include <fstream>
#include <string>
#include <arpa/inet.h>
#include <unistd.h>
#include "protocol.h"

int main() {
    int server_fd = socket(AF_INET, SOCK_STREAM, 0);
    sockaddr_in addr = {AF_INET, htons(5000), INADDR_ANY};
    bind(server_fd, (struct sockaddr*)&addr, sizeof(addr));
    listen(server_fd, 5);

    std::cout << "Discovery Server (DNS) active on port 5000...\n";

    while (true) {
        int client_fd = accept(server_fd, nullptr, nullptr);
        MsgHeader header;
        read(client_fd, &header, sizeof(header));

        if (header.type == REGISTRATION) {
            char buffer[header.payload_length + 1] = {0};
            read(client_fd, buffer, header.payload_length);
            
            // Append: "username password" to our shared file
            std::ofstream ofs("users.txt", std::ios::app);
            ofs << header.sender << " " << buffer << "\n";
            ofs.close();
            
            std::cout << "Successfully registered: " << header.sender << "\n";
        }
        close(client_fd);
    }
}