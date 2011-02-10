#!/usr/bin/env python
import settings
from settings import *

import dynect
from dynect import  *

import route53helper
from route53helper import  *


from sys import exit
import ConfigParser
import re
import asyncore
import logging
import logging.handlers
import socket
import lockfile

config = ConfigParser.RawConfigParser()

'''
SyncClass is where the main parsing of the two DNS sets occurs, it also handles the file lock to prevent multiple
update from occuring simultaneously and calls into the route53 and dynect python wrappers to get back the necissary information
'''
class SyncClass():
	cn = ''
	un = ''
	pwd = ''
	accessid = ''
	secretaccesskey = ''
	action_level = ''
	log_file = ''
	log_byte_size = 0
	logger = None
	lockPath = ''
	# logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL
	log_level = logging.INFO
	preDefinedSections = {'credentials' : 'y', 'logging' : 'y', 'route53' : 'y', 'general' : 'y'}
	def __init__(self):
		config.readfp(open(os.path.join(install_dir, 'dynect.cfg')))
		
		self.cn = config.get('credentials', 'cn')
		self.un = config.get('credentials', 'un')
		self.pwd = config.get('credentials', 'pwd')
	
		self.accessid = config.get('route53', 'access_id')
		self.secretaccesskey = config.get('route53', 'secret_access_key')
	
		self.log_file = config.get('logging', 'log_file')
		string_size = config.get('logging', 'log_byte_size')
		llevel = config.get('logging', 'log_level')
		
		self.lockPath = config.get('general', 'lock_path')
		
		self.log_byte_size = int(string_size)
		
		if llevel == 'DEBUG':
			self.log_level = logging.DEBUG
		elif llevel == 'INFO':
			self.log_level = logging.INFO
		elif llevel == 'WARNING':
			self.log_level = logging.WARNING
		elif llevel == 'ERROR':
			self.log_level = logging.ERROR
		else:
			self.log_level = logging.CRITICAL
		
		#set the logging leve
		self.logger = logging.getLogger('route53Logger')
		self.logger.setLevel(self.log_level)

		if len(self.log_file) > 1:	
			path, name = os.path.split(self.log_file)
			if os.path.isdir(path) and len(name) > 0:
				# Add the log message handler to the logger
				handler = logging.handlers.RotatingFileHandler(self.log_file, maxBytes=self.log_byte_size, backupCount=5)

				self.logger.addHandler(handler)
		else:
			# If the directory doesn't exist use standard output
			console = logging.StreamHandler()
			self.logger.addHandler(console)		

		self.logger.info('Sync Class Created')

	def _rrset_list_from_dynect(self, recordsIn, rtypesSupported, dynClassInstance, zone, fqdn):
		self.logger.info('Entered _rrset_list_from_dynect!')
		rc = {}
		try:
			for record in recordsIn:
				rtype = record.split('/')[2].replace('Record', '')
				if rtype in  rtypesSupported:
					dataName = ''
					dataName1 = ''
					dataName2 = ''
					dataName3 = ''
					vals = 1
					
					# we format the data and the name differently and have different rdata based on the record type so lets handle all of the possibilities supported 
					# by route 53
					if rtype == 'A' or rtype == 'AAAA':
						dataName = 'address'
					elif rtype == 'CNAME':
						dataName = 'cname'
					elif rtype == 'TXT':
						dataName = 'txtdata'
					elif rtype == 'PTR':
						dataName = 'ptrdname'
					elif rtype == 'SRV':
						dataName = 'priority'
						dataName1 = 'weight'
						dataName2 = 'port'
						dataName3 = 'weight'
						vals = 4
					elif rtype == 'MX':
						dataName = 'preference'
						dataName1 = 'exchange'
						vals = 2

					# now lets get the actual data
					fullRecord = dynClassInstance.get_any_record_for_fqdn(zone, fqdn, record)

					mainData = fullRecord['rdata'][dataName]
					
					# here we account for SPF records which are just text records but are handled explicitly in route53
					if rtype == 'TXT':
						if fullRecord['rdata']['txtdata'].startswith('v=spf1 '):
							rtype = 'SPF'
							mainData = fullRecord['rdata']['txtdata'].replace('v=spf1 ', '')
					if vals == 1:
						rc[fqdn + '.-' + str(mainData)] = {'fqdn' : fqdn, 'data' : mainData, 'ttl' : fullRecord['ttl'], 'rtype' : rtype, 'action' : 'add'}
					elif vals == 2:
						rc[fqdn + '.-' +  str(mainData) + ' ' + fullRecord['rdata'][dataName1]] =  {'fqdn' : fqdn, 'data' : str(mainData) + ' ' + fullRecord['rdata'][dataName1], 'ttl' : fullRecord['ttl'], 'rtype' : rtype, 'action' : 'add'}
					elif vals == 4:
						rc[fqdn + '.-' +  mainData + ' ' + fullRecord['rdata'][dataName1] + ' ' + fullRecord['rdata'][dataName2] + ' ' + fullRecord['rdata'][dataName3]] = {'fqdn' : fqdn, 'data' : mainData + ' ' + fullRecord['rdata'][dataName1] + ' ' + fullRecord['rdata'][dataName2] + ' ' + fullRecord['rdata'][dataName3], 'ttl' : fullRecord['ttl'], 'rtype' : rtype, 'action' : 'add'}
					
				elif rtype == 'SOA' or rtype == 'NS':
					self.logger.info('NS or SOA record... ignoring')
				else:
					self.logger.warning('Primary record type ' + record.split('/')[2].replace('Record', '') + ' not available in Route53')
		except Exception, e:
			self.logger.error('Error in _rrset_list_from_dynect! ' + str(e))
			rc = None
		return rc
		
	def _rrset_list_from_xml(self, xmlIn, rtypesDict, fqdn_in):
		self.logger.info('Entered _rrset_list_from_xml!')
		out = xml.dom.minidom.parseString(xmlIn)
		nodes = out.getElementsByTagName('ResourceRecordSets')
		rc = {}
		try:
			for node in nodes:
				innerNodes = node.getElementsByTagName('ResourceRecordSet')
				for innerNode in innerNodes:
					node_type = innerNode.getElementsByTagName('Type')[0].childNodes[0].data
					if (node_type in rtypesDict) == True:
						node_fqdn = innerNode.getElementsByTagName('Name')[0].childNodes[0].data
						node_ttl = innerNode.getElementsByTagName('TTL')[0].childNodes[0].data
						recordNodes = innerNode.getElementsByTagName('ResourceRecord')
						for recordNode in recordNodes:
							if node_fqdn == fqdn_in:
								node_value = recordNode.getElementsByTagName('Value')[0].childNodes[0].data
								rc[node_fqdn + '-' + node_value] = {'fqdn' : node_fqdn, 'data' : node_value, 'ttl' : node_ttl, 'rtype' : node_type, 'action' : 'delete'}
		except Exception, e:
			self.logger.error('Error in _rrset_list_from_xml! ' + e)
			rc = None
		return rc
		
	def _merge_records(self, records, postFix):
		self.logger.info('Entered _merge_records!')
		rc = {}
		try:
			for recordKey in records:
				keyArray = recordKey.split('-')
				if keyArray[0] + postFix + records[recordKey]['rtype'] in rc:
					rc[keyArray[0] + postFix + records[recordKey]['rtype']]['data'] = rc[keyArray[0] + postFix + records[recordKey]['rtype']]['data']  + ',,' + keyArray[1]
				else:
					rc[keyArray[0] + postFix + records[recordKey]['rtype']] = {'fqdn' : records[recordKey]['fqdn'], 'data' : keyArray[1], 'ttl' : records[recordKey]['ttl'], 'rtype' : records[recordKey]['rtype'], 'action' : records[recordKey]['action']}
		except Exception, e:
			self.logger.error('Error in _merge_records!')
			rc = None
			
		return rc

	def _syncFqdn(self, dyn, zone, fqdn):
		#
		# let's start by getting the route 53 zone info 
		#
		
		# First initialize the route53 object with the connection info
		rh = Route53Helper(self.accessid, self.secretaccesskey)
		rh.use_logger(self.logger)
	
		# Now let's get the rrset for the zone and fqdn, if the zone doesn't exist yet, let's create it
		xmlOut = None
		try:
			xmlOut = rh.get_hosted_zone_rrset(fqdn + '.')
			if xmlOut == None:
				rh.add_hosted_zone(fqdn, 'FQDN created by Dynect route53 secondary dns script')
				self.logger.info('Created the fqdn' + fqdn + ' in route 53')
				xmlOut = rh.get_hosted_zone_rrset(fqdn + '.')
		except Exception, e:
			rh.add_hosted_zone(fqdn, 'FQDN created by Dynect route53 secondary dns script')
			self.logger.info('Created the fqdn' + fqdn + ' in route 53')
			xmlOut = rh.get_hosted_zone_rrset(fqdn + '.')
		
		# Check that the zone/fqdn data is there  then parse the route53 zone data to work with them as we are the Dyenct records
		outRoute53Dict = {}
		if xmlOut != None:
			outRoute53Dict = self._rrset_list_from_xml(xmlOut, rh.get_route53_record_type(), fqdn + '.')
			self.logger.info('Parsed the route 53 zone record')
		else:
			self.logger.error('Could not retrieve the rrset for the zone, no action taken')
			return
		
		# Get the zone record data from Dynect
		records = dyn.get_any_records_for_fqdn(zone, fqdn)
		# Put the records into a standardized form so we can work with them in conjuction with route53
		outDynectDict = None
		if records != None:
			self.logger.info('Retreived the dynect records')
			outDynectDict = self._rrset_list_from_dynect(records, rh.get_route53_record_type(), dyn, zone, fqdn)
		else:
			self.logger.error('Could not retrieve the Dynect data for the zone, no action taken')
			return
		print outDynectDict

		# Do a shallow copy of the dictionaries to pass into the merge functions
		outRoute53DictTemp = outRoute53Dict.copy()
		outDynectDictTemp = outDynectDict.copy()
		
		# Now merge multiple records of the same type in the same fqdn into the same data structures (since that is how the xml creation will e3xpect them)
		outRoute53Dict = self._merge_records(outRoute53DictTemp, 'remove')
		outDynectDict = self._merge_records(outDynectDictTemp, 'add')
		self.logger.info('Mutliple records for the same record type and fqdn merged in dictionaries')
		
		# Now let's combine the Add and Remove dictionaries (removing the route 53 then adding the Dynect)
		combinedDict = outRoute53Dict
		combinedDict.update(outDynectDict)
		self.logger.info('Add and Delete dictionaries combined')

		# Finally, call the function in the helper to update the zone based on the passed in dictionary
		rh.update_hosted_zone_rrset(fqdn + '.', combinedDict)
		self.logger.info('Route 53 zone updated')
	

	def doSyncAll(self):
		sections = config.sections()
		for section in sections:
			if section in self.preDefinedSections:
				pass
			else:
				configZoneArray = section.split('.')
                                configZone = configZoneArray[len(configZoneArray) - 2] + '.' + configZoneArray[len(configZoneArray) - 1]
				self._doSync(configZone, section) 
	def doSync(self, zone):
		sections = config.sections()
                for section in sections:
                        if section in self.preDefinedSections:
                                pass
                        else:
				configZoneArray = section.split('.')
                		configZone = configZoneArray[len(configZoneArray) - 2] + '.' + configZoneArray[len(configZoneArray) - 1]

				if zone.strip('.').lower() == configZone.lower():
                                	self._doSync(zone, section)

	def _doSync(self, zone, fqdn):
		# Let's setup the fqdn with and without a dot associated with it
		fqdn = fqdn.strip('.')
 
		try:
			shouldSync = config.get(fqdn, 'sync')
			if shouldSync.lower() != 'yes':
				self.logger.info('"sync" for fqdn ' + fqdn + ' not set to yes')
				return
		except Exception, ex:	
			self.logger.info('Could not find section for fqdn: ' + fqdn + ' - no action has been taken')
			return
			
		# Initialize the Dynect object
		dyn = Dynect(self.cn, self.un, self.pwd)
		dyn.use_logger(self.logger)
		self.logger.info('Successfully connected to Dynect!')
		
		# First thing we need to do is get the soa record for the zone
		soaRecord = dyn.get_soa_record_for_fqdn(zone, zone)
		
		if soaRecord == None:
			self.logger.error('Failed to get SOA Record from Dynect, no action taken')
			return
		else:
			self.logger.info('Successfully got SOA record')
		
		# Now get the serial number from the SOA record
		try:
			currentSerial = int(soaRecord['rdata']['serial'])
		except:
			self.logger.error('Failed to get current serial number from SOA record, no action taken')
			return
		
		# Now that we have the current serial number, let's check the serial number that route53 is currently synced to
		# Start by locking the serial number file so no one else can work with it while we are
		lock = lockfile.FileLock(os.path.join(self.lockPath,  fqdn + '_serial.txt'))
		self.logger.info('Initialize the lock')
		
		lock.acquire(timeout=3) # set a timeout becasue if we don't get it quickly then someone if probably already syncing this guy 
		try:
			continueSyn = False
			if os.path.exists(os.path.join(self.lockPath, fqdn + '_serial.txt')):
				f = open(os.path.join(self.lockPath, fqdn + '_serial.txt'), 'r')
				self.logger.info('Got the lock and opened the file to read the serial number')
				serial = f.readline()
				f.close()
				try:
					# If the current serial is later then the serial we have, well, time to sync!
					continueSync = int(serial) < currentSerial
					self.logger.info('currentSerial is ' + str(currentSerial) + ' and previous serial was ' + serial)
				except:
					# in case there is no serial number, assume the current info is stale and sync
					continueSync = True
			else:
				continueSync = True
			if continueSync:
					self.logger.info('Sync fqdns')
					self._syncFqdn(dyn, zone, fqdn) # call our sync function where we actually, you know, sync it up
			# Now lets write out the current serial number so the next guy through knows whether he needs to sync or not
			f = open(os.path.join(self.lockPath,  fqdn + '_serial.txt'), 'w')
			f.write(str(currentSerial))
			f.close()
		finally:
			# Always release the lock when we are done else there will never be another sync
			lock.release()
			self.logger.info('lock released')
			
syncer = SyncClass()
syncer.doSyncAll()
