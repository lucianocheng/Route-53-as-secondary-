#!/usr/bin/python

'''
Very handy script for generating the zone change request xml. Thankl you very much to
Richard Harvey for his provided script in the Amazon Route53 examples section
which this script was originally based on!
'''
import dns.zone, sys, getopt, os, time, datetime
import httplib2
import xml.dom.minidom
import uuid
from hashlib import sha1
from hmac import new as hmac

http = httplib2.Http()

ROUTE53_BASE_URL = 'https://route53.amazonaws.com/'

class Route53Helper():
	dns_types = {'A' : 'true', 'AAAA' : 'true', 'TXT' : 'true', 'CNAME' : 'true', 'MX' : 'true', 'PTR' : 'true', 'SRV' : 'true', 'SPF' : 'true'}
	today = ''
	xml_blob = ''
	_signingKey = ''
	_accessKey = ''
	_datetime = ''
	_auth_header = ''
	_logging = None

	def __init__(self, AWSAccessKeyId, SigningKey):
		self.today = datetime.date.today()
		self.xml_blob = ''
		
		#get the datetime directly from route53 to prevent clock issues
		self._datetime = self.get_date_time()
		
		#now generate the correct autentication from the access keys using HMAC SHA1 
		self._accessKey = AWSAccessKeyId
		self._signingKey = SigningKey
		sig = hmac(self._signingKey, self._datetime, sha1).digest().encode('base64')
		self._auth_header = 'AWS3-HTTPS AWSAccessKeyId=' + AWSAccessKeyId + ',Algorithm=HmacSHA1,Signature=' + sig
	
	def _get_zones_from_xml(self, xmlIn):
		out = xml.dom.minidom.parseString(xmlIn)
		nodes = out.getElementsByTagName("HostedZone")
		rc = {}
		for node in nodes:
			rc[node.getElementsByTagName("Name")[0].childNodes[0].data] = node.getElementsByTagName("Id")[0].childNodes[0].data
		return rc
		
	def get_route53_record_type(self):
		return self.dns_types
	
	def get_hosted_zones(self):
		xmloutput = self._do_rest_call('2010-10-01/hostedzone', 'GET',  '') 
		output = self._get_zones_from_xml(xmloutput)
		return output
	
	def get_hosted_zone_id(self, zone):
		outList = self.get_hosted_zones()
		output = None
		try:
			output = outList[zone]
		except Exception, e:
			output = None
		return output
		
	def get_hosted_zone_rrset(self, zone):
		zone_id = self.get_hosted_zone_id(zone)
		xmloutput = self._do_rest_call('/2010-10-01/' + zone_id + '/rrset', 'GET',  '') 
		return xmloutput
		
	
	def delete_hosted_zone(self, zone):
		# get the zone id
		zoneId = self.get_hosted_zone_id(zone)
		
		if zoneId == None:
			self._log_error('Route53helper.py: delete_hosted_zone: Could not find zone')
			return
			
		# make the rest call to do the actual creation
		xmloutput = self._do_rest_call('/2010-10-01' + zoneId, 'DELETE',  '') 
		
	def add_hosted_zone(self, zone, comment):
		# create the xml for the zone
		self._generate_createhostedzone_header() 
		self._generate_hostedzone(zone, str(uuid.uuid1()), comment) 
		self._generate_createhostedzone_footer()
			
		# make the rest call to do the actual creation
		xmloutput = self._do_rest_call('/2010-10-01/hostedzone', 'POST',  self.xml_blob) 
	
	'''
	update_hosted_zone_rrset - sets up the xml and calls the route53 host update for a given dictionary in the structure:
	
	[fqdn + data : ['fqdn' : fqdn, 'data' : data, 'ttl' : ttl, 'rtype' : rtype, 'action' : action]]
	
	where:
	 fqdn = fully qualified domain name of record to add
	 data = the record data
	 ttl = ttl for record
	 rtype = record type, one of ['A', 'AAAA', 'TXT', 'CNAME', 'MX', 'PTR', 'SRV', 'SPF']
	 action = add a record or delete a record, one of ['add', 'delete']
	 
	ie: [ 'myzone.net1.2.3.4' : ['fqdn' : 'myzone.net', 'data' : '1.2.3.4,,3.4.5.6', 'ttl' : '30', 'rtype' : 'A', 'action' : 'add']]
	
	'''
	def update_hosted_zone_rrset(self, zone, inList):
		self.xml_blob = ''
		
		# get the zone id
		zoneId = self.get_hosted_zone_id(zone)
		
		if zoneId == None:
			self._log_error('Route53helper.py: update_hosted_zone_rrset: Could not find zone')
			return
		
		# create the xml for the zone
		self._generate_changerecordsets_header() 
		for kd, vd in inList.iteritems():
			if vd['action'] == 'delete':
				self._create_change_request_remove(vd['fqdn'], vd['rtype'], vd['ttl'], vd['data'])
		
		for ka, va in inList.iteritems():
			if va['action'] == 'add':
				self._create_change_request_add(va['fqdn'], va['rtype'], va['ttl'], va['data'])
				
		self._generate_changerecordsets_footer()
				
		# make the rest call to do the actual creation
		xmloutput = self._do_rest_call('/2010-10-01' + zoneId + '/rrset', 'POST',  self.xml_blob) 
	
	def get_date_time(self):
		return self._do_rest_call('date', 'GET',  '')
	
	'''
	Change record set xml section
	'''
	def _generate_changerecordsets_header(self):
		self.xml_blob = self.xml_blob + '<?xml version="1.0" encoding="UTF-8"?>'
		self.xml_blob = self.xml_blob + '<ChangeResourceRecordSetsRequest xmlns="https://route53.amazonaws.com/doc/2010-10-01/">'
		self.xml_blob = self.xml_blob + ' <ChangeBatch>'
		self.xml_blob = self.xml_blob + '  <Comment>Updated by Dyn Secondary DNS script at ' + str(self.today) + '</Comment>'
		self.xml_blob = self.xml_blob + '  <Changes>'

	def _generate_changerecordsets_footer(self):
		self.xml_blob = self.xml_blob + '  </Changes>'
		self.xml_blob = self.xml_blob + ' </ChangeBatch>'
		self.xml_blob = self.xml_blob + '</ChangeResourceRecordSetsRequest>'
	
	def _create_change_request_add(self, fqdn, rtype, ttl, rdata):
		self._create_change_request(fqdn, rtype, ttl, rdata, 'CREATE')
		
	def _create_change_request_remove(self, fqdn, rtype, ttl, rdata):
		self._create_change_request(fqdn, rtype, ttl, rdata, 'DELETE')
		
	def _create_change_request_update(self, fqdn, rtype, ttl, old_rdata, new_rdata):
		self._create_change_request(fqdn, rtype, ttl, old_rdata, 'DELETE')
		self._create_change_request(fqdn, rtype, ttl, new_rdata, 'CREATE')
		
	def _create_change_request(self, fqdn, rtype, ttl, rdata, action):
		self.xml_blob = self.xml_blob + '   <Change>'
		self.xml_blob = self.xml_blob + '    <Action>' + action + '</Action>'
		self.xml_blob = self.xml_blob + '     <ResourceRecordSet>'
		self.xml_blob = self.xml_blob + '      <Name>' + fqdn+ '</Name>'
		self.xml_blob = self.xml_blob + '      <Type>' + rtype + '</Type>'
		self.xml_blob = self.xml_blob + '      <TTL>' + str(ttl) + '</TTL>'
		self.xml_blob = self.xml_blob + '      <ResourceRecords>'
		if rdata.find(',,') > -1:
			rdataArray = rdata.split(',,')
			for d in rdataArray:
				self.xml_blob = self.xml_blob + '       <ResourceRecord>'
				if rtype == 'TXT':
					self.xml_blob = self.xml_blob + '        <Value>\"' + d + '\"</Value>'
				else:
                                        self.xml_blob = self.xml_blob + '        <Value>' + d + '</Value>'

					self.xml_blob = self.xml_blob + '       </ResourceRecord>'
		else:
			self.xml_blob = self.xml_blob + '       <ResourceRecord>'
			if rtype == 'TXT':
				self.xml_blob = self.xml_blob + '        <Value>\"' + rdata + '\"</Value>'
			else:
				self.xml_blob = self.xml_blob + '        <Value>' + rdata + '</Value>'

			self.xml_blob = self.xml_blob + '       </ResourceRecord>'

		self.xml_blob = self.xml_blob + '     </ResourceRecords>'
		self.xml_blob = self.xml_blob + '    </ResourceRecordSet>'
		self.xml_blob = self.xml_blob + '   </Change>'
	
	'''
	Create hosted zone xml section
	'''		
	def _generate_createhostedzone_header(self):
		self.xml_blob = self.xml_blob + '<?xml version="1.0" encoding="UTF-8"?>'
		self.xml_blob = self.xml_blob + '<CreateHostedZoneRequest xmlns="https://route53.amazonaws.com/doc/2010-10-01/">'
		
	def _generate_hostedzone(self, name, inId, comment):
		self.xml_blob = self.xml_blob + '<Name>' + name + '.</Name>'
		self.xml_blob = self.xml_blob + '<CallerReference>' + inId + '</CallerReference>'
		self.xml_blob = self.xml_blob + '<HostedZoneConfig>'
		self.xml_blob = self.xml_blob + '<Comment>' +  comment + '</Comment>'
		self.xml_blob = self.xml_blob + '</HostedZoneConfig>'
		
	def _generate_createhostedzone_footer(self):
		self.xml_blob = self.xml_blob + '</CreateHostedZoneRequest>'
		
	"""
	do_rest_call - utility function to take some repition out of the http requests
	
	apiname: the /REST/... function to cal
	verb: either PUT, POST, GET or DELETE
	inputXml: the parameters to pass in as xml or an empty string if no parameters
	
	returns: array built from xml content of return
	"""
	def _do_rest_call(self,  apiname, verb,  inputXml):
		try:
			self._log_debug("Route53:_do_rest_call: Enter")
			response = ""
			content = ""
			http.force_exception_to_status_code = True
			if self._auth_header == "":
				response, content = http.request(ROUTE53_BASE_URL + apiname,  verb , inputXml, headers={'Content-type': 'application/xml'})
				if response['status'] == '200' or response['status'] == '201':
					result = response['date']
			else:
				response, content = http.request(ROUTE53_BASE_URL + apiname, verb, inputXml, headers={'Content-type': 'text/xml','charset' : 'UTF-8', 'Date' : self._datetime, 'X-Amzn-Authorization':  self._auth_header})
				if response['status'] == '200' or response['status'] == '201':
					return content
				else:
					print "Error: " + response
					print content
			self._log_debug("Route53:_do_rest_call: Exit")
			return result
		except:
			self._log_error("Route53:_do_rest_call: Error! - " + self._format_excpt_info())
			return ""

	'''
	Set of functions to handle logging, by passing in the logging object we can let the calling program decide
	if it wants to log, how it wants to log and let it use it's own logging agent
	'''
	
	'''
	use_logger - the main call to determine logging
	
	logger: the logging object, passed in if you want to use it else None
	'''
	def use_logger(self, logger):
		try:
			self._logging = logger
		except:
			pass
		
	def _log_debug(self, msg):
		try:
			if self._logging == None:
				return
			self._logging.debug(msg)
		except:
			pass
		
	def _log_info(self, msg):
		try:
			if self._logging == None:
				return
			self._logging.info(msg)
		except:
			pass
		
	def _log_warning(self, msg):
		try:
			if self._logging == None:
				return
			self._logging.warning(msg)
		except:
			pass
		
	def _log_error(self, msg):
		try:
			if self._logging == None:
				return
			self._logging.error(msg)
		except:
			pass
		
	def _log_critical(self, msg):
		try:
			if self._logging == None:
				return
			self._logging.critical(msg)
		except:
			pass

