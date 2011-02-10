#!/usr/bin/env python

import sys
sys.path.append( '..' )
import socket
import dns.message
import dns.query
import dns.zone

from handle_notify import HandleNotify

counter = 0
loops = 50

good_message_text = """id 62225
opcode NOTIFY
rcode NOERROR
flags AA
;QUESTION
routetester.net. IN SOA
;ANSWER
routetester.net. 0 IN SOA ns1.p08.dynect.net. kgray.dyn.com. 75 3600 600 604800 60
;AUTHORITY
;ADDITIONAL
"""
good_msg = dns.message.from_text(good_message_text)
good_message = good_msg.to_wire()

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
print "************ Starting Stress Test - " + str(loops) + " Packets *************"
print "Socket open (connection on loopback address 127.0.0.1, this must be allowed in the"
print "handle_nofity.cfg for this to show full functionality)."
print ""
print "Begin sending packets..."
while counter < loops:
	s.sendto(good_message, ("localhost", 53))
	counter = counter + 1

s.close()
print ""
print "... stress test complete"

