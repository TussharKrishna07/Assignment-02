# Makefile for Chat System

CXX      = g++
CXXFLAGS = -std=c++17 -Wall -pthread

TARGETS  = discovery_server chat_server chat_server_select chat_client

all: $(TARGETS)

discovery_server: discovery_server.cpp protocol.h
	$(CXX) $(CXXFLAGS) -o discovery_server discovery_server.cpp

chat_server: chat_server_threaded.cpp protocol.h
	$(CXX) $(CXXFLAGS) -o chat_server chat_server_threaded.cpp

chat_server_select: chat_server_select.cpp protocol.h
	$(CXX) $(CXXFLAGS) -o chat_server_select chat_server_select.cpp

chat_client: chat_client.cpp protocol.h
	$(CXX) $(CXXFLAGS) -o chat_client chat_client.cpp

clean:
	rm -f $(TARGETS) users.txt

.PHONY: all clean