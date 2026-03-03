// discovery_server.cpp (Updated)
#include<bits/stdc++.h>
#include <iostream>
#include <fstream>
#include <string>
#include <cstring>
#include <arpa/inet.h>
#include <unistd.h>
#include "protocol.h"

using namespace std;

void listening_to_connections(int fd,int port){
    sockaddr_in addr = {AF_INET, htons(port), {INADDR_ANY}};
    bind(fd, (struct sockaddr*)&addr, sizeof(addr));
    listen(fd, 5);
}


int main() {
    int server_fd = socket(AF_INET, SOCK_STREAM, 0);
    listening_to_connections(server_fd,5000);

    cout << "Discovery Server (DNS) active on port 5000...\n";
    sockaddr_in client_address;
    socklen_t client_len = sizeof(client_address);
    unordered_map<string,Userinfo> total_users;
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
            total_users[header.sender]={header.sender,buffer,client_ip,client_port};
            ofs << header.sender << " " << buffer << " " << client_ip << " " << client_port << "\n";
            ofs.close();

            cout << "Registered: " << header.sender
                 << " | IP: "      << client_ip
                 << " | Port: "    << client_port << "\n";

            // Send confirmation back to client
            MsgHeader resp{};
            resp.type = REGISTRATION;
            string ok_msg = "OK";
            resp.payload_length = ok_msg.size();
            strncpy(resp.sender, "server", 31);
            strncpy(resp.target, header.sender, 31);
            write(client_fd, &resp, sizeof(resp));
            write(client_fd, ok_msg.c_str(), ok_msg.size());
        }
        close(client_fd);
    }
}