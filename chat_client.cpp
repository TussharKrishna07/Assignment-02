// chat_client.cpp
#include <iostream>
#include <thread>
#include <string>
#include <arpa/inet.h>
#include <unistd.h>
#include <cstring>
#include "protocol.h"

// Thread function to handle incoming messages from server
void receive_handler(int sock) {
    MsgHeader header;
    while (read(sock, &header, sizeof(header)) > 0) {
        char* payload = new char[header.payload_length + 1]{0};
        read(sock, payload, header.payload_length);
        
        if (header.type == BROADCAST) {
            std::cout << "\n[Broadcast from " << header.sender << "]: " << payload << "\n> " << std::flush;
        } else if (header.type == PRIVATE_MSG) {
            std::cout << "\n[Private from " << header.sender << "]: " << payload << "\n> " << std::flush;
        }
        delete[] payload;
    }
}

int main() {
    int sock = socket(AF_INET, SOCK_STREAM, 0);
    sockaddr_in serv_addr = {AF_INET, htons(6000)};
    inet_pton(AF_INET, "127.0.0.1", &serv_addr.sin_addr);

    if (connect(sock, (struct sockaddr*)&serv_addr, sizeof(serv_addr)) < 0) {
        std::cerr << "Connection to Chat Server failed.\n";
        return -1;
    }

    // 1. Initial Login
    std::string username;
    std::cout << "Enter username: ";
    std::cin >> username;
    
    MsgHeader login_hdr = {LOGIN, 0};
    strncpy(login_hdr.sender, username.c_str(), 31);
    write(sock, &login_hdr, sizeof(login_hdr));

    // 2. Start Receiver Thread
    std::thread(receive_handler, sock).detach();

    // 3. Main CLI Loop
    std::string input;
    std::cin.ignore(); // Clear newline
    while (true) {
        std::cout << "> ";
        std::getline(std::cin, input);
        if (input.empty()) continue;

        MsgHeader msg_hdr;
        strncpy(msg_hdr.sender, username.c_str(), 31);
        std::string message;

        if (input.substr(0, 4) == "@all") {
            msg_hdr.type = BROADCAST;
            message = input.substr(5);
        } else if (input[0] == '@') {
            msg_hdr.type = PRIVATE_MSG;
            size_t space_pos = input.find(' ');
            std::string target = input.substr(1, space_pos - 1);
            strncpy(msg_hdr.target, target.c_str(), 31);
            message = input.substr(space_pos + 1);
        } else {
            std::cout << "Use @all <msg> or @username <msg>\n";
            continue;
        }

        msg_hdr.payload_length = message.length();
        write(sock, &msg_hdr, sizeof(msg_hdr));
        write(sock, message.c_str(), message.length());
    }

    close(sock);
    return 0;
}