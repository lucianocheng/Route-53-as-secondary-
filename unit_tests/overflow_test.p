#!/usr/bin/env python

import sys
sys.path.append( '..' )
import socket
from handle_notify import HandleNotify

base = "Let's make some random data to see if we can crash our application"
data = ''

while len(data) < 10251: 
	data = data + base
print "**************** Overflow Test - Packet of Size " + str(len(data)) + " ************"
print "Sending Packet..."
print ""
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.sendto(data, ("localhost", 53))
s.close()
print ""
print "... Packet Sent"
