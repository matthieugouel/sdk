package models

// This file is auto-generated.
// Please contact avi-sdk@avinetworks.com for any change requests.

// AlertObjectList alert object list
// swagger:model AlertObjectList
type AlertObjectList struct {

	// Name of the object.
	// Required: true
	Name string `json:"name"`

	//  Enum options - VIRTUALSERVICE, POOL, HEALTHMONITOR, NETWORKPROFILE, APPLICATIONPROFILE, HTTPPOLICYSET, DNSPOLICY, IPADDRGROUP, STRINGGROUP, SSLPROFILE, SSLKEYANDCERTIFICATE, NETWORKSECURITYPOLICY, APPLICATIONPERSISTENCEPROFILE, ANALYTICSPROFILE, VSDATASCRIPTSET, TENANT, PKIPROFILE, AUTHPROFILE, CLOUD, SERVERAUTOSCALEPOLICY, AUTOSCALELAUNCHCONFIG, MICROSERVICEGROUP, IPAMPROFILE, HARDWARESECURITYMODULEGROUP, POOLGROUP, PRIORITYLABELS, POOLGROUPDEPLOYMENTPOLICY, GSLBSERVICE, GSLBSERVICERUNTIME, SCHEDULER, GSLBGEODBPROFILE, GSLBAPPLICATIONPERSISTENCEPROFILE, TRAFFICCLONEPROFILE, VSVIP, WAFPOLICY, WAFPROFILE, ERRORPAGEPROFILE, ERRORPAGEBODY, L4POLICYSET, SERVICEENGINE, DEBUGSERVICEENGINE, DEBUGCONTROLLER, DEBUGVIRTUALSERVICE, SERVICEENGINEGROUP, SEPROPERTIES, NETWORK, CONTROLLERNODE, CONTROLLERPROPERTIES, SYSTEMCONFIGURATION, VRFCONTEXT, USER, ALERTCONFIG, ALERTSYSLOGCONFIG, ALERTEMAILCONFIG, ALERTTYPECONFIG, APPLICATION, ROLE, CLOUDPROPERTIES, SNMPTRAPPROFILE, ACTIONGROUPPROFILE, MICROSERVICE, ALERTPARAMS, ACTIONGROUPCONFIG, CLOUDCONNECTORUSER, GSLB, GSLBDNSUPDATE, GSLBSITEOPS, GLBMGRWARMSTART, IPAMDNSRECORD, GSLBDNSGSSTATUS, GSLBDNSGEOFILEOPS, GSLBDNSGEOUPDATE, GSLBDNSGEOCLUSTEROPS, GSLBDNSCLEANUP, GSLBSITEOPSRESYNC, TCPSTATRUNTIME, UDPSTATRUNTIME, IPSTATRUNTIME, ARPSTATRUNTIME, MBSTATRUNTIME, IPSTKQSTATSRUNTIME, MALLOCSTATRUNTIME, SHMALLOCSTATRUNTIME, CPUUSAGERUNTIME, L7GLOBALSTATSRUNTIME, L7VIRTUALSERVICESTATSRUNTIME, SEAGENTVNICDBRUNTIME, SEAGENTGRAPHDBRUNTIME, SEAGENTSTATERUNTIME, INTERFACERUNTIME, ARPTABLERUNTIME, DISPATCHERSTATRUNTIME, DISPATCHERSTATCLEARRUNTIME, DISPATCHERTABLEDUMPRUNTIME, DISPATCHERREMOTETIMERLISTDUMPRUNTIME, METRICSAGENTMESSAGE, HEALTHMONITORSTATRUNTIME, METRICSENTITYRUNTIME, PERSISTENCEINTERNAL, HTTPPOLICYSETINTERNAL, DNSPOLICYINTERNAL, CONNECTIONDUMPRUNTIME, SHAREDDBSTATS, SHAREDDBSTATSCLEAR, ICMPSTATRUNTIME, ROUTETABLERUNTIME, VIRTUALMACHINE, POOLSERVER, SEVSLIST, MEMINFORUNTIME, RTERINGSTATRUNTIME, ALGOSTATRUNTIME, HEALTHMONITORRUNTIME, CPUSTATRUNTIME, SEVM, HOST, PORTGROUP, CLUSTER, DATACENTER, VCENTER, HTTPPOLICYSETSTATS, DNSPOLICYSTATS, METRICSSESTATS, RATELIMITERSTATRUNTIME, NETWORKSECURITYPOLICYSTATS, TCPCONNRUNTIME, POOLSTATS, CONNPOOLINTERNAL, CONNPOOLSTATS, VSHASHSHOWRUNTIME, SELOGSTATSRUNTIME, NETWORKSECURITYPOLICYDETAIL, LICENSERUNTIME, SERVERRUNTIME, METRICSRUNTIMESUMMARY, METRICSRUNTIMEDETAIL, DISPATCHERSEHMPROBETEMPDISABLERUNTIME, POOLDEBUG, VSLOGMGRMAP, SERUMINSERTIONSTATS, HTTPCACHE, HTTPCACHESTATS, SEDOSSTATRUNTIME, VSDOSSTATRUNTIME, SERVERUPDATEREQ, VSSCALEOUTLIST, SEMEMDISTRUNTIME, TCPCONNRUNTIMEDETAIL, SEUPGRADESTATUS, SEUPGRADEPREVIEW, SEFAULTINJECTEXHAUSTM, SEFAULTINJECTEXHAUSTMCL, SEFAULTINJECTEXHAUSTMCLSMALL, SEFAULTINJECTEXHAUSTCONN, SEHEADLESSONLINEREQ, SEUPGRADE, SEUPGRADESTATUSDETAIL, SERESERVEDVS, SERESERVEDVSCLEAR, VSCANDIDATESEHOSTLIST, SEGROUPUPGRADE, REBALANCE, SEGROUPREBALANCE, SEAUTHSTATSRUNTIME, AUTOSCALESTATE, VIRTUALSERVICEAUTHSTATS, NETWORKSECURITYPOLICYDOS, KEYVALINTERNAL, KEYVALSUMMARYINTERNAL, SERVERSTATEUPDATEINFO, CLTRACKINTERNAL, CLTRACKSUMMARYINTERNAL, MICROSERVICERUNTIME, SEMICROSERVICE, VIRTUALSERVICEANALYSIS, CLIENTINTERNAL, CLIENTSUMMARYINTERNAL, MICROSERVICEGROUPRUNTIME, BGPRUNTIME, REQUESTQUEUERUNTIME, MIGRATEALL, MIGRATEALLSTATUSSUMMARY, MIGRATEALLSTATUSDETAIL, INTERFACESUMMARYRUNTIME, INTERFACELACPRUNTIME, DNSTABLE, GSLBSERVICEDETAIL, GSLBSERVICEINTERNAL, GSLBSERVICEHMONSTAT, SETROLESREQUEST, TRAFFICCLONERUNTIME, GEOLOCATIONINFO, SEVSHBSTATRUNTIME, GEODBINTERNAL, GSLBSITEINTERNAL, WAFSTATS, USERDEFINEDDATASCRIPTCOUNTERS, LLDPRUNTIME, VSESSHARINGPOOL, SEVSSPLACEMENT, L4POLICYSETSTATS, L4POLICYSETINTERNAL, SERESOURCEPROTO, SECONSUMERPROTO, SECREATEPENDINGPROTO, PLACEMENTSTATS, SEVIPPROTO, RMVRFPROTO, VCENTERMAP, VIMGRVCENTERRUNTIME, INTERESTEDVMS, INTERESTEDHOSTS, VCENTERSUPPORTEDCOUNTERS, ENTITYCOUNTERS, TRANSACTIONSTATS, SEVMCREATEPROGRESS, PLACEMENTSTATUS, VISUBFOLDERS, VIDATASTORE, VIHOSTRESOURCES, CLOUDCONNECTOR, VINETWORKSUBNETVMS, VIDATASTORECONTENTS, VIMGRVCENTERCLOUDRUNTIME, VIVCENTERPORTGROUPS, VIVCENTERDATACENTERS, VIMGRHOSTRUNTIME, PLACEMENTGLOBALS, APICCONFIGURATION, CIFTABLE, APICTRANSACTION, VIRTUALSERVICESTATEDBCACHESUMMARY, POOLSTATEDBCACHESUMMARY, SERVERSTATEDBCACHESUMMARY, APICAGENTINTERNAL, APICTRANSACTIONFLAP, APICGRAPHINSTANCES, APICEPGS, APICEPGEPS, APICDEVICEPKGVER, APICTENANTS, APICVMMDOMAINS, NSXCONFIGURATION, NSXSGTABLE, NSXAGENTINTERNAL, NSXSGINFO, NSXSGIPS, NSXAGENTINTERNALCLI, MAXOBJECTS.
	Objects []string `json:"objects,omitempty"`

	//  Enum options - CONN_LOGS, APP_LOGS, EVENT_LOGS, METRICS.
	// Required: true
	Source string `json:"source"`

	//  It is a reference to an object of type Tenant.
	TenantRef string `json:"tenant_ref,omitempty"`

	// url
	// Read Only: true
	URL string `json:"url,omitempty"`

	// Unique object identifier of the object.
	UUID string `json:"uuid,omitempty"`
}
