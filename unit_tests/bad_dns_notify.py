#!/usr/bin/env python

import sys
sys.path.append( '..' )
import dns.message
import dns.query
import dns.zone

from handle_notify import HandleNotify

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

query_msg = dns.message.Message()
query_msg.set_opcode(1)
query_message = query_msg.to_wire()

bad_form_message = 'There is nothing parsable about this using the python dns library'

hn = HandleNotify()
hn.log_level = 2 

# First test good DNS packet and ip address in good list
print '******** Test 1 - Good IP and Good Packet *********'
print hn.verifyDnsNotifyPacket(hn.ipList[0], good_message) 

# Next test good notify packet with ip NOT in good list
print '******** Test 2 - Bad IP and Good Packet *********'
print hn.verifyDnsNotifyPacket('0.0.0.0', good_message) 

# Next test good DNS packet that isn't a NOTIFY packet and ip address in good list
print '******** Test 3 - Good IP and Good Packet but not a NOTIFY Packet *********'
print hn.verifyDnsNotifyPacket(hn.ipList[0], query_message)

# Finally test an invalid DNS packet and ip address in good list
print '******** Test 4 - Good IP and Invalid Packet *********'
print hn.verifyDnsNotifyPacket(hn.ipList[0], bad_form_message)

