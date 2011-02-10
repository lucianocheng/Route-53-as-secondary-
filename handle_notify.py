#!/usr/bin/env python
import socket
import sys
import ConfigParser
import dns.message
import dns.query
import dns.zone
import sync_route53
from sync_route53 import  *

import settings
from settings import *

class HandleNotify():
	config = ConfigParser.ConfigParser()
	syncer = SyncClass()
	ipList = None
	ipBind = ''
	action_level = ''
	log_file = ''
	log_byte_size = 0
	logger = None
	# logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL
	log_level = logging.INFO
	s = None

	def __init__(self):
		self.readConfig(os.path.join(install_dir, 'handle_notify.cfg'))

                # Now setup the logging

                # Set the logging level
                self.logger = logging.getLogger('notifyLogger')
                self.logger.setLevel(self.log_level)

                if len(self.log_file) > 1:
                        path, name = os.path.split(self.log_file)
                        if os.path.isdir(path) and len(name) > 0:
                                # Add the log message handler to the logger
                                handler = logging.handlers.RotatingFileHandler(self.log_file, maxBytes=log_byte_size, backupCount=5)
                                self.logger.addHandler(handler)
                else:
                        # If no path is specified, log to standard output
                        console = logging.StreamHandler()
                        self.logger.addHandler(console)

                self.logger.info('Started handle_notify logging')

	
	'''
	 main handler loop, runs in the background and replies to notify requests
	'''	
	def run(self):
		self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		self.s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	
		#set a timout of one minute before we re-loop
		self.s.settimeout(60)
	
		if len(self.ipBind) < 1:
			self.logger.info('binding to all local NICs')
			self.s.bind(('', 53))
		else:
			self.logger.info('binding to local ip address ' + ipBind)
			self.s.bind((ipBind, 53))

		self.logger.info('bound to UDP port 53.')
		self.logger.info('entering socket wait loop')
		while True:
			try:
				message, address = self.s.recvfrom(1024)
				self.handleMessage(address, message)
			except socket.timeout:
				pass # we expect the timeout errors, just keep on truckin...
			except Exception as detail:
				self.logger.error('error in handle_notify.py socket loop: ' + str(detail))

	# Parse out the fqdn to update
	def getFQDNFromPacket(self, message):
		try:
			msg = dns.message.from_wire(message)
                	rrSetList =  msg.question
        		for rrSet in rrSetList:
        	        	if rrSet.rdtype == dns.rdatatype.SOA and rrSet.rdclass == dns.rdataclass.IN:
        	                	return rrSet.to_text().split()[0]
		except Exception as detail:
			self.logger.error('Error parsing out FQDN: ' + str(detail))
		self.logger.error('Failed to parse out FQDN from notify message')
		return None

	# Make sure the packet received on port 53 is:
	#	a valid notify packet
	#	from an approved ip address
	#	well formed
	#	contains an SOA record
	# else log the error 
	def verifyDnsNotifyPacket(self, address, message):
		if self.ipList == None:
			self.logger.error('No addresses were allowed in the handle_nofiy.cfg file')
                	return False
	
	        if address in self.ipList:
                	pass
        	else:
                	self.logger.error('!! Received UDP packet from ' + address + '  which was not in the list of approved ip addresses')
                	return False
		try:
        		msg = dns.message.from_wire(message)
			op = msg.opcode()
       			if op != dns.opcode.NOTIFY:
				self.logger.error('!! DNS packet received from ' + address + ' but was not a notify packet, opcode was: ' + str(op))
	                	return False

        		rrSetList =  msg.question
        		for rrSet in rrSetList:
	                	if rrSet.rdtype == dns.rdatatype.SOA and rrSet.rdclass == dns.rdataclass.IN:
        	                	return True
			self.logger.error('!! No SOA  IN record was found in the notify packet from ' + address)
		except Exception as detail:
			self.logger.error('!! Error in verifyDNSNotifyPacket, packet from ' + address + ' was not well formed, Error: ' + str(detail))
		return False

	# Send a reply to the notify message so the sended can acknowledge and stop resending
	def sendReplyToNotify(self, address, message):
		self.logger.info('sending notify response to ' + address[0])
		msg = dns.message.from_wire(message)
	        resp = dns.message.make_response(msg)
	        self.s.sendto(resp.to_wire(), address)

	# Handle the notify message received
	def handleMessage(self, address, message):
		self.logger.info('handleMessage entered')
		self.logger.info('address is ' + address[0])
		
		if self.verifyDnsNotifyPacket(address[0], message):
			self.sendReplyToNotify(address, message)
			fqdn = self.getFQDNFromPacket(message)
			self.syncer.doSync(fqdn)
		else:
			return

	def readConfig(self, configFile):
		self.config.read(configFile)
		ipListString = self.config.get('general', 'notifyip')
		self.ipBind = self.config.get('general', 'bind_ip')
		self.action_level = self.config.get('logging', 'log_level')
		self.log_file = self.config.get('logging', 'log_file')
		self.log_byte_size = self.config.get('logging', 'log_byte_size')
		self.ipList = ipListString.split(',')

if __name__ == '__main__': 
	# main function to kick off the socket loop. Probably want to 
	# run from Daemontools or something similar to keep it alive in the background
	hn = HandleNotify()
	hn.run()

