#ifndef PROTOCOL_H
#define PROTOCOL_H

#include <cstdint>
#include <string>

using namespace std;

// Message Types for our "Grammar"
enum MessageType {
    REGISTRATION = 1,  // Client -> Discovery Server
    LOGIN = 2,         // Client -> Chat Server
    BROADCAST = 3,     // Client -> Chat Server (@all)
    PRIVATE_MSG = 4,   // Client -> Chat Server (@user)
    QUERY_USER = 5,    // Client -> Discovery Server
    STATUS_UPDATE = 6  // Bonus: Change status [cite: 34]
};

// Fixed-size header for every packet
struct MsgHeader {
    int32_t type;             // One of the MessageType enums [cite: 27]
    int32_t payload_length;    // Size of the message body following this header [cite: 29]
    char sender[32];          // Username of the person sending 
    char target[32];          // Username of the recipient (used for private messages)
};

struct Userinfo {
    string username;
    string password;
    string IP;
    int port;
    int active;
};

#endif