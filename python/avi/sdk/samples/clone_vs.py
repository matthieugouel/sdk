#!/usr/bin/env python

from __future__ import print_function
import sys
import os
import argparse
import getpass
import textwrap
import logging

from avi.sdk.avi_api import ApiSession
from requests.packages import urllib3

logging.basicConfig(level=logging.ERROR)

# Suppress warnings (typically SSL certificate warnings) when calling the API

urllib3.disable_warnings()

DEFAULT_API_VERSION = '16.4.2'

AVICLONE_VERSION = [1, 0, 4]

# Try to obtain the terminal width to allow spprint() to wrap output neatly.
# If unable to determine, assume terminal width is 70 characters

try:
    T_SIZE = os.get_terminal_size()[0]
except:
    T_SIZE = 70

def spprint(s, ind='', **kwargs):
    flush = kwargs.pop('flush', False)
    print('\r\n'.join(textwrap.wrap(s, width=T_SIZE, subsequent_indent=ind,
                                    break_on_hyphens=False)), **kwargs)
    if flush:
        f = kwargs.get('file', sys.stdout)
        f.flush() if f is not None else sys.stdout.flush()

class AviClone:
    VALID_POOL_REF_OBJECTS = {
        'pool-persistency': 'application_persistence_profile_ref',
        'pool-healthmonitor': 'health_monitor_refs',
        'pool-sslprofile': 'ssl_profile_ref',
        'pool-ipaddrgroup': 'ipaddrgroup_ref',
        'pool-pkiprofile': 'pki_profile_ref',
        'pool-sslcert': 'ssl_key_and_certificate_ref'}
    VALID_DATASCRIPT_REF_OBJECTS = {
        'ds-ipgroup': 'ipgroup_refs',
        'ds-stringgroup': 'string_group_refs'}
    VALID_POLICYSET_REF_OBJECTS = {
        'policy-ipgroup': 'group_refs',
        'policy-stringgroup': 'string_group_refs'}
    VALID_VS_REF_OBJECTS = {
        'vs-appprofile': 'application_profile_ref',
        'vs-networkprofile': 'network_profile_ref',
        'vs-analyticsprofile': 'analytics_profile_ref',
        'vs-errorpageprofile': 'error_page_profile_ref',
        'vs-networksecuritypolicy': 'network_security_policy_ref',
        'vs-servernetworkprofile': 'server_network_profile_ref',
        'vs-sslprofile': 'ssl_profile_ref',
        'vs-sslcert': 'ssl_key_and_certificate_refs',
        'vs-wafpolicy': 'waf_policy_ref',
        'vs-rewritablecontent': 'content_rewrite/rewritable_content_ref'}
    VALID_APPLICATIONPROFILE_REF_OBJECTS = {
        'appprofile-cachemimetypesblacklist':
            'http_profile/cache_config/mime_types_black_group_refs',
        'appprofile-cachemimetypes':
            'http_profile/cache_config/mime_types_group_refs',
        'appprofile-compressiblecontent':
            'http_profile/compression_profile/compressible_content_ref',
        'appprofile-compressibleipaddrgroup': 'ip_addrs_ref',
        'appprofile-compressibledevices': 'devices_ref'}

    def __init__(self, source_api, dest_api=None):
        self.api = source_api
        self.dest_api = dest_api or source_api
        self.flush_actions()

    def flush_actions(self):
        self.actions = []
        self.clone_track = {}

    def get_all_objects_by_name(self, path, name, tenant='', tenant_uuid='',
                           timeout=None, params=None, api_version=None,
                           api_to_use=None, **kwargs):
        """
        Helper function which works like the SDK's get_object_by_name but
        returns a list of matches rather than just the first match
        """

        api = api_to_use or self.api

        obj = None
        if not params:
            params = {}
        params['name'] = name
        resp = api.get(path, tenant, tenant_uuid, timeout=timeout,
                        params=params, api_version=api_version, **kwargs)
        if resp.status_code in (401, 419):
            ApiSession.reset_session(self.api)
            resp = api.get_object_by_name(path, name, tenant, tenant_uuid,
                                          timeout=timeout, params=params,
                                          **kwargs)
        if resp.status_code < 300:
            obj = resp.json()['results']

        api._update_session_last_used()

        return obj

    def _delete_created_objs(self, created_objs, otenant_uuid):
        """
        Deletes any created objects when a failure has occurred.
        """

        logger.debug('Deleting created objects...')

        for retry in range(len(created_objs)):
            retry_objs = []
            for obj in created_objs:
                obj_ref = obj['url'].split('/api/')[1]
                logger.debug('Trying to delete %s', obj_ref)
                r = self.dest_api.delete(obj_ref, tenant_uuid=otenant_uuid)
                if r.status_code >= 300:
                    logger.debug('Failed with %s - will retry', r.status_code)
                    retry_objs.append(obj)
            if retry_objs:
                created_objs = retry_objs
            else:
                break

    def delete_objects(self, objs, tenant=None):
        """
        Deletes objects in the given tenant

        :param objects: List of objects to delete
        :param tenant: Tenant containing the objects
        """

        if tenant is None:
            t_obj = None
            tenant_uuid = None
        else:
            t_obj = self.dest_api.get_object_by_name('tenant', tenant)
            if t_obj is None:
                raise Exception('A tenant with name %s could not be found'
                                % tenant)
            tenant_uuid = t_obj['uuid']

        self._delete_created_objs(objs, tenant_uuid)


    def clone_object(self, old_name, new_name, object_type=None, tenant=None,
                     other_tenant=None, other_cloud=None,
                     force_clone=None, force_unique_name=False,
                     t_obj=None, ot_obj=None, oc_obj=None):
        """
        Clones an object other than a virtual service

        Optionally creating the cloned object in a different tenant and/or a
        different cloud.

        Returns a tuple: json representation of the cloned object,
        list of additional objects created if any

        :param old__name: Name of existing virtual service
        :param new__name: New name for cloned virtual service
        :param tenant: Tenant for existing object
        :param other_tenant: Tenant for cloned object
        :param other_cloud: Cloud for cloned object
        :param force_clone: List of referenced object attributes to forcibly
                            clone rather than re-use (for example
                            health_monitor_refs)
        :param force_unique_name: Resolve destination name conflicts by
                                  appending an index number
        :param t_obj: Tenant object. If neither tenant nor t_obj is specified
                      then user's default tenant will be used
        :param ot_obj: Tenant for cloned object. If neither other_tenant nor
                       ot_obj is specified, the object will be cloned to the
                       same tenant as the source
                       other_tenant name)
        :param oc_obj: Cloud for cloned object. If neither other_cloud nor
                       oc_obj is specified, the object will be cloned
                       to the same cloud as the source
        :return: tuple - json representation of the cloned object, list of
                 additional objects created if any
        :rtype: tuple
        """

        force_clone = force_clone or []

        # Retrieve tenant, other_tenant and other_cloud names, uuids and objects
        # which may have been passed as objects or names

        if t_obj:
            tenant = t_obj['name']
            tenant_uuid = t_obj['uuid']
        else:
            if tenant is None:
                t_obj = None
                tenant_uuid = None
            else:
                t_obj = self.api.get_object_by_name('tenant', tenant)
                if t_obj is None:
                    raise Exception('A tenant with name %s could not be found'
                                    % tenant)
                tenant_uuid = t_obj['uuid']

        if ot_obj:
            other_tenant = ot_obj['name']
            otenant_uuid = ot_obj['uuid']
        else:
            if other_tenant is None:
                ot_obj = None
                otenant_uuid = tenant_uuid
            else:
                ot_obj = self.dest_api.get_object_by_name('tenant',
                                                          other_tenant)
                if ot_obj is None:
                    raise Exception('A tenant with name %s could not be found'
                                    % other_tenant)
                otenant_uuid = ot_obj['uuid']

        if oc_obj:
            other_cloud = oc_obj['name']
        else:
            if other_cloud is None:
                oc_obj = None
            else:
                oc_obj = self.dest_api.get_object_by_name('cloud', other_cloud)
                if oc_obj is None:
                    raise Exception('A cloud with name %s could not be found'
                                    % other_cloud)

        if not object_type:
            # If object_type is not specified, assume the old_name is in
            # form object_type/uuid

            object_type = old_name.split('/')[0]

        logger.debug('Cloning %s "%s" to "%s"', object_type,
                                                old_name,
                                                new_name)

        if old_name.startswith(object_type + '/'):
            old_obj = self.api.get(old_name, tenant_uuid=tenant_uuid).json()
            old_name = old_obj['name']
        else:
            old_obj = self.api.get_object_by_name(object_type, old_name,
                                                  tenant_uuid=tenant_uuid)

        if not old_obj:
            raise Exception('Object of type %s named %s could not be found'
                            % (object_type, old_name))

        new_obj_check = self.dest_api.get_object_by_name(
                        object_type, new_name, tenant_uuid=otenant_uuid)

        if new_obj_check is not None:
            if force_unique_name:
                count = 1
                new_name_prefix = new_name
                while new_obj_check is not None:
                    new_name = '-'.join([new_name_prefix, str(count)])
                    count += 1
                    new_obj_check = self.dest_api.get_object_by_name(
                                                   object_type,
                                                   new_name,
                                                   tenant_uuid=otenant_uuid)
                logger.debug('Forced unique name "%s"', new_name)
            else:
                raise Exception('An object of type %s with '
                                'name "%s" already exists'
                                % (object_type, new_name))

        # Remove unique attributes and rename object

        old_obj.pop('uuid', None)
        old_obj_url = old_obj.pop('url', None)
        old_obj['name'] = new_name

        created_objs = []

        try:
            # Do object-type specific processing of child objects etc.

            if object_type == 'pool':
                created_objs = self._process_pool(p_obj=old_obj, t_obj=t_obj,
                                                  ot_obj=ot_obj, oc_obj=oc_obj,
                                                  force_clone=force_clone)
            elif object_type == 'poolgroup':
                created_objs = self._process_poolgroup(pg_obj=old_obj,
                                                       t_obj=t_obj,
                                                       ot_obj=ot_obj,
                                                       oc_obj=oc_obj,
                                                       force_clone=force_clone)
            elif object_type == 'httppolicyset':
                created_objs = self._process_httppolicyset(
                    ps_obj=old_obj, t_obj=t_obj, ot_obj=ot_obj, oc_obj=oc_obj,
                    force_clone=force_clone)
            elif object_type == 'vsdatascriptset':
                created_objs = self._process_vsdatascriptset(
                    ds_obj=old_obj, t_obj=t_obj, ot_obj=ot_obj, oc_obj=oc_obj,
                    force_clone=force_clone)
            elif object_type == 'networksecuritypolicy':
                created_objs = self._process_networksecuritypolicy(
                    ns_obj=old_obj, t_obj=t_obj, ot_obj=ot_obj, oc_obj=oc_obj,
                    force_clone=force_clone)
            elif object_type == 'dnspolicy':
                created_objs = self._process_dnspolicy(
                    dp_obj=old_obj, t_obj=t_obj, ot_obj=ot_obj, oc_obj=oc_obj,
                    force_clone=force_clone)
            elif object_type == 'applicationprofile':
                created_objs = self._process_applicationprofile(
                    ap_obj=old_obj, t_obj=t_obj, ot_obj=ot_obj, oc_obj=oc_obj,
                    force_clone=force_clone)

            # Try to create cloned object (possibly in a different tenant to the
            # source object)

            logger.debug('Creating %s "%s"...', object_type, new_name)

            r = self.dest_api.post(object_type, old_obj,
                                   tenant_uuid=otenant_uuid)
            if r.status_code < 300:
                new_obj = r.json()
                self.actions += ['Cloned %s "%s"%s to "%s"%s'
                                 % (object_type, old_name,
                                    (' in tenant "%s"' % tenant)
                                    if tenant else '', new_name,
                                    (' in tenant "%s"' % other_tenant)
                                    if other_tenant else '')]
                logger.debug('Created %s "%s"', object_type, new_obj['url'])
                if old_obj_url:
                    self.clone_track[old_obj_url] = new_obj['url']
                return new_obj, created_objs
            else:
                exception_string = ('Unable to clone %s "%s" as "%s" (%d:%s)'
                                    % (object_type, old_name,
                                       new_name, r.status_code, r.text))
                logger.debug(exception_string)
                logger.debug(old_obj)
                raise Exception(exception_string)

        except Exception as ex:
            # If an exception occurred, delete any intermediate objects we
            # have created

            self._delete_created_objs(created_objs, otenant_uuid)

            raise Exception('%s\r\n=> Unable to clone %s "%s" as "%s"'
                            % (ex, object_type, old_name, new_name))

    def _process_pool(self, p_obj, t_obj, ot_obj, oc_obj, force_clone):
        """
        Performs pool-specific manipulations on the cloned object
        """

        # Remove read-only attributes

        logger.debug('Running _process_pool')

        p_obj.pop('gslb_sp_enabled', None)

        # If cloning to a different cloud, remove network references

        if oc_obj:
            servers = p_obj.get('servers', [])
            for server in servers:
                server.pop('vm_ref', None)
                server.pop('nw_ref', None)
                server.pop('external_uuid', None)
                server.pop('discovered_networks', None)
            p_obj.pop('networks', None)

        created_objs = []

        try:
            valid_ref_objects = self.VALID_POOL_REF_OBJECTS

            # Clone rather than re-use any references in the force_clone list
            # but re-use previously cloned objects rather than creating
            # multiple identical clones

            refs_to_clone = [ref for key, ref in valid_ref_objects.items()
                                if key in force_clone]

            new_objs = self._clone_refs(parent_obj=p_obj, refs=refs_to_clone,
                                        t_obj=t_obj, ot_obj=ot_obj,
                                        oc_obj=oc_obj, name=p_obj['name'])

            created_objs.extend(list(new_objs))

            # If moving to a different tenant, clone any tenant-specific
            # referenced objects

            if ot_obj or self.api != self.dest_api:
                refs_to_clone = [ref for key, ref in valid_ref_objects.items()
                                    if key not in force_clone]
                new_objs = self._clone_refs_to_tenant(parent_obj=p_obj,
                                                      refs=refs_to_clone,
                                                      t_obj=t_obj,
                                                      ot_obj=ot_obj,
                                                      oc_obj=oc_obj)

                created_objs.extend(list(new_objs))

            if oc_obj:
                p_obj['cloud_ref'] = oc_obj['url']

                # If moving to a different cloud, pool will be moved to the
                # default global VRF in the target cloud

                p_obj.pop('vrf_ref', None)
        except Exception as ex:
            # If an exception occurred, delete any intermediate objects we
            # have created

            self._delete_created_objs(created_objs, ot_obj['uuid'])

            raise

        return created_objs

    def _process_poolgroup(self, pg_obj, t_obj, ot_obj, oc_obj, force_clone):
        """
        Performs poolgroup-specific manipulations on the cloned object, such
        as cloning the poolgroup members
        """

        logger.debug('Running _process_poolgroup')

        new_pool_group_name = pg_obj['name']

        created_objs = []

        try:
            if 'members' in pg_obj:
                count = 1
                for member in pg_obj['members']:
                    if 'pool_ref' in member:
                        p_path = member['pool_ref'].split('/api/')[1]
                        new_pool_name = '-'.join([new_pool_group_name,
                                                  'pool', str(count)])

                        p_obj, p_created_objs = self.clone_object(
                            old_name=p_path, new_name=new_pool_name,
                            t_obj=t_obj, ot_obj=ot_obj, oc_obj=oc_obj,
                            force_clone=force_clone, force_unique_name=True)

                        count += 1

                        created_objs.append(p_obj)
                        created_objs.extend(list(p_created_objs))

                        # Update the pool with the cloned pool

                        member['pool_ref'] = p_obj['url']

            # (Try to!) move the new pool group to a different cloud

            if oc_obj:
                pg_obj['cloud_ref'] = oc_obj['url']
        except Exception as ex:
            # If an exception occurred, delete any intermediate objects we
            # have created

            self._delete_created_objs(created_objs, ot_obj['uuid'])

            raise

        return created_objs

    def _process_httppolicyset(self, ps_obj, t_obj, ot_obj, oc_obj,
                               force_clone):
        """
        Performs httppolicyset-specific manipulations on the cloned object such
        as cloning pools and poolgroups used in the policy rules
        """

        logger.debug('Running _process_httppolicyset')

        new_httppolicyset_name = ps_obj['name']

        created_objs = []

        try:
            for policy_type in ['http_security_policy',
                                'http_request_policy',
                                'http_response_policy']:
                policy_obj = ps_obj.get(policy_type, {})
                if policy_obj:
                    logger.debug('Processing %s', policy_type)
                    new_objs = self._process_policy_rules(
                                     new_httppolicyset_name,
                                     p_obj=policy_obj, t_obj=t_obj,
                                     ot_obj=ot_obj, oc_obj=oc_obj,
                                     force_clone=force_clone)
                    created_objs.extend(new_objs)
        except Exception as ex:
            # If an exception occurred, delete any intermediate objects we
            # have created

            self._delete_created_objs(created_objs, ot_obj['uuid'])

            raise

        return created_objs

    def _process_networksecuritypolicy(self, ns_obj, t_obj, ot_obj, oc_obj,
                               force_clone):
        """
        Performs networksecuritypolicy-specific manipulations on the cloned
        object such as ip groups in the policy rules
        """

        logger.debug('Running _process_networksecuritypolicy')

        new_networksecuritypolicy_name = ns_obj['name']

        created_objs = []

        try:
            new_objs = self._process_policy_rules(
                                new_networksecuritypolicy_name,
                                p_obj=ns_obj, t_obj=t_obj,
                                ot_obj=ot_obj, oc_obj=oc_obj,
                                force_clone=force_clone)
            created_objs.extend(new_objs)
        except Exception as ex:
            # If an exception occurred, delete any intermediate objects we
            # have created

            self._delete_created_objs(created_objs, ot_obj['uuid'])

            raise

        return created_objs

    def _process_dnspolicy(self, dp_obj, t_obj, ot_obj, oc_obj,
                               force_clone):
        """
        Performs dnspolicy-specific manipulations on the cloned
        object such as ip groups in the policy rules
        """

        logger.debug('Running _process_dnspolicy')

        new_dnspolicy_name = dp_obj['name']

        created_objs = []

        try:
            new_objs = self._process_policy_rules(
                                new_dnspolicy_name,
                                p_obj=dp_obj, t_obj=t_obj,
                                ot_obj=ot_obj, oc_obj=oc_obj,
                                force_clone=force_clone)
            created_objs.extend(new_objs)
        except Exception as ex:
            # If an exception occurred, delete any intermediate objects we
            # have created

            self._delete_created_objs(created_objs, ot_obj['uuid'])

            raise

        return created_objs

    def _process_policy_rules(self, new_policy_name, p_obj, t_obj, ot_obj,
                              oc_obj, force_clone):
        """
        Process the network/DNS/HTTP policy rules
        """

        logger.debug('Running _process_policy_rules')

        valid_ref_objects = self.VALID_POLICYSET_REF_OBJECTS

        try:
            created_objs = []

            rules = p_obj.get('rules', [])
            for rule in rules:
                logger.debug('Checking rule "%s"...', rule['name'])

                if 'match' in rule:
                    for m_key, m_obj in rule['match'].items():
                        refs_to_clone = [ref for key, ref in
                                         valid_ref_objects.items()
                                         if key in force_clone]

                        new_objs = self._clone_refs(parent_obj=m_obj,
                                                    refs=refs_to_clone,
                                                    t_obj=t_obj, ot_obj=ot_obj,
                                                    oc_obj=oc_obj,
                                                    name=new_policy_name)

                        created_objs.extend(list(new_objs))

                        # If moving to a different tenant, clone any
                        # tenant-specific referenced objects

                        if ot_obj or self.api != self.dest_api:
                            refs_to_clone = [ref for key, ref in
                                             valid_ref_objects.items()
                                             if key not in force_clone]
                            new_objs = self._clone_refs_to_tenant(
                                   parent_obj=m_obj, refs=refs_to_clone,
                                   t_obj=t_obj, ot_obj=ot_obj, oc_obj=oc_obj)

                            created_objs.extend(list(new_objs))

                if 'switching_action' in rule:
                    switching_action = rule.get('switching_action', {})
                    pool_ref = switching_action.get('pool_ref', None)

                    if pool_ref:
                        # Process a pool referenced in the switching action

                        if pool_ref in self.clone_track:
                            # If this pool has already been cloned during
                            # this session, re-use the cloned object

                            p_obj_url = self.clone_track[pool_ref]
                            logger.debug('Reusing previously cloned object %s',
                                         p_obj_url)
                        else:
                            # Otherwise, clone the pool

                            p_path = pool_ref.split('/api/')[1]
                            p_name = '-'.join([new_policy_name, 'pool'])
                            p_obj, p_created_objs = self.clone_object(
                                old_name=p_path, new_name=p_name,
                                t_obj=t_obj, ot_obj=ot_obj, oc_obj=oc_obj,
                                force_clone=force_clone,
                                force_unique_name=True)
                            created_objs.append(p_obj)
                            created_objs.extend(p_created_objs)
                            p_obj_url = p_obj['url']

                        switching_action['pool_ref'] = p_obj_url

                    pool_group_ref = switching_action.get('pool_group_ref',
                                                          None)

                    if pool_group_ref:
                        # Process a pool group referenced in the switching
                        # action

                        if pool_group_ref in self.clone_track:
                            # If this pool group has already been cloned during
                            # this session, re-use the cloned object

                            pg_obj_url = self.clone_track[pool_group_ref]
                            logger.debug('Reusing previously cloned object %s',
                                         pg_obj_url)
                        else:
                            pg_path = pool_group_ref.split('/api/')[1]
                            pg_name = '-'.join([new_policy_name,
                                                'poolgroup'])
                            pg_obj, pg_created_objs = self.clone_object(
                                old_name=pg_path, new_name=pg_name,
                                t_obj=t_obj, ot_obj=ot_obj, oc_obj=oc_obj,
                                force_clone=force_clone,
                                force_unique_name=True)
                            created_objs.append(pg_obj)
                            created_objs.extend(pg_created_objs)
                            pg_obj_url = pg_obj['url']

                        switching_action['pool_group_ref'] = pg_obj_url
        except Exception as ex:
            # If an exception occurred, delete any intermediate objects we
            # have created

            self._delete_created_objs(created_objs, ot_obj['uuid'])

            raise

        return created_objs

    def _process_vsdatascriptset(self, ds_obj, t_obj, ot_obj, oc_obj,
                               force_clone):
        """
        Performs datascript-specific manipulations on the cloned object such
        as cloning pools, pool groups, string groups, ip groups referenced
        by the DataScript
        """

        logger.debug('Running _process_vsdatascriptset')

        new_vsdatascriptset_name = ds_obj['name']

        created_objs = []

        try:
            if 'pool_refs' in ds_obj:
                for index, pool_ref in enumerate(ds_obj['pool_refs']):
                    if pool_ref in self.clone_track:
                        # If this pool has already been cloned during
                        # this session, re-use the cloned object

                        p_obj_url = self.clone_track[pool_ref]
                        logger.debug('Reusing previously cloned object %s',
                                     p_obj_url)
                    else:
                        # Otherwise, clone the pool

                        p_path = pool_ref.split('/api/')[1]
                        p_name = '-'.join([ds_obj['name'], 'pool'])
                        p_obj, p_created_objs = self.clone_object(
                            old_name=p_path, new_name=p_name,
                            t_obj=t_obj, ot_obj=ot_obj, oc_obj=oc_obj,
                            force_clone=force_clone,
                            force_unique_name=True)

                        created_objs.append(p_obj)
                        created_objs.extend(p_created_objs)
                        p_obj_url = p_obj['url']

                    ds_obj['pool_refs'][index] = p_obj_url

            if 'pool_group_refs' in ds_obj:
                for index, pool_group_ref in enumerate(
                                               ds_obj['pool_group_refs']):
                    if pool_group_ref in self.clone_track:
                        # If this pool group has already been cloned during
                        # this session, re-use the cloned object

                        pg_obj_url = self.clone_track[pool_group_ref]
                        logger.debug('Reusing previously cloned object %s',
                                     pg_obj_url)
                    else:
                        pg_path = pool_group_ref.split('/api/')[1]
                        pg_name = '-'.join([ds_obj['name'], 'poolgroup'])
                        pg_obj, pg_created_objs = self.clone_object(
                            old_name=pg_path, new_name=pg_name,
                            t_obj=t_obj, ot_obj=ot_obj, oc_obj=oc_obj,
                            force_clone=force_clone,
                            force_unique_name=True)

                        created_objs.append(pg_obj)
                        created_objs.extend(pg_created_objs)
                        pg_obj_url = pg_obj['url']

                    ds_obj['pool_group_refs'][index] = pg_obj_url

            valid_ref_objects = self.VALID_DATASCRIPT_REF_OBJECTS

            # Clone rather than re-use any references in the force_clone list
            # but re-use previously cloned objects rather than creating
            # multiple identical clones

            refs_to_clone = [ref for key, ref in valid_ref_objects.items()
                             if key in force_clone]

            new_objs = self._clone_refs(parent_obj=ds_obj, refs=refs_to_clone,
                                        t_obj=t_obj, ot_obj=ot_obj,
                                        oc_obj=oc_obj)

            created_objs.extend(list(new_objs))

            # If moving to a different tenant, clone any tenant-specific
            # referenced objects

            if ot_obj or self.api != self.dest_api:
                refs_to_clone = [ref for key, ref in valid_ref_objects.items()
                                 if key not in force_clone]
                new_objs = self._clone_refs_to_tenant(parent_obj=ds_obj,
                                                      refs=refs_to_clone,
                                                      t_obj=t_obj,
                                                      ot_obj=ot_obj,
                                                      oc_obj=oc_obj)

                created_objs.extend(list(new_objs))

        except Exception as ex:
            # If an exception occurred, delete any intermediate objects we
            # have created

            self._delete_created_objs(created_objs, ot_obj['uuid'])

            raise

        return created_objs

    def _process_applicationprofile(self, ap_obj, t_obj, ot_obj, oc_obj,
                               force_clone):
        """
        Performs applicationprofile-specific manipulations on the cloned
        object such as cloning string groups used for caching/compression
        MIME types
        """

        logger.debug('Running _process_applicationprofile')

        created_objs = []

        valid_ref_objects = self.VALID_APPLICATIONPROFILE_REF_OBJECTS

        try:
            http_profile = ap_obj.get('http_profile', {})
            comp_profile = http_profile.get('compression_profile', None)

            if comp_profile:
                filters = comp_profile.get('filter', [])
                for filter in filters:
                    logger.debug('Checking filter "%s"...', filter['name'])

                    refs_to_clone = [ref for key, ref in
                                     valid_ref_objects.items()
                                     if key in force_clone]

                    new_objs = self._clone_refs(parent_obj=filter,
                                                refs=refs_to_clone,
                                                t_obj=t_obj, ot_obj=ot_obj,
                                                oc_obj=oc_obj,
                                                name=ap_obj['name'])

                    created_objs.extend(list(new_objs))

                    # If moving to a different tenant, clone any
                    # tenant-specific referenced objects

                    if ot_obj or self.api != self.dest_api:
                        refs_to_clone = [ref for key, ref in
                                         valid_ref_objects.items()
                                         if key not in force_clone]
                        new_objs = self._clone_refs_to_tenant(
                                parent_obj=filter, refs=refs_to_clone,
                                t_obj=t_obj, ot_obj=ot_obj, oc_obj=oc_obj)

                        created_objs.extend(list(new_objs))

            # Clone rather than re-use any references in the force_clone list
            # but re-use previously cloned objects rather than creating
            # multiple identical clones

            refs_to_clone = [ref for key, ref in valid_ref_objects.items()
                             if key in force_clone]

            new_objs = self._clone_refs(parent_obj=ap_obj, refs=refs_to_clone,
                                        t_obj=t_obj, ot_obj=ot_obj,
                                        oc_obj=oc_obj)

            created_objs.extend(list(new_objs))

            # If moving to a different tenant, clone any tenant-specific
            # referenced objects

            if ot_obj or self.api != self.dest_api:
                refs_to_clone = [ref for key, ref in valid_ref_objects.items()
                                 if key not in force_clone]
                new_objs = self._clone_refs_to_tenant(parent_obj=ap_obj,
                                                      refs=refs_to_clone,
                                                      t_obj=t_obj,
                                                      ot_obj=ot_obj,
                                                      oc_obj=oc_obj)

                created_objs.extend(list(new_objs))

        except Exception as ex:
            # If an exception occurred, delete any intermediate objects we
            # have created

            self._delete_created_objs(created_objs, ot_obj['uuid'])

            raise

        return created_objs

    def _clone_refs(self, parent_obj, refs, t_obj, ot_obj, oc_obj, name=None):

        # Process the list of child objects, refs, of the parent_obj.
        # If the child object has been cloned before, refer to the
        # previously-cloned object otherwise clone the object.

        parent_obj_name = (name or (parent_obj['name']
                                    if 'name' in parent_obj else ''))

        logger.debug('Cloning forced refs%s',
                     (' for %s' % parent_obj_name if parent_obj_name else ''))

        created_objs = []

        try:
            for ref_str in refs:
                ref_split = ref_str.split('/')
                pobj_attr = parent_obj
                for ref_attr in ref_split[:-1]:
                    pobj_attr = pobj_attr.get(ref_attr, {})
                referenced = ref_split[-1]

                if referenced in pobj_attr:
                    logger.debug('Processing %s', ref_str)
                    child_objs = pobj_attr[referenced]

                    is_list = isinstance(child_objs, list)
                    if not is_list:
                        child_objs = [child_objs]

                    for i in range(len(child_objs)):
                        child_obj = child_objs[i]
                        if child_obj in self.clone_track:
                            new_r_obj_url = self.clone_track[child_obj]
                            logger.debug('Reusing previously cloned object %s',
                                         new_r_obj_url)
                        else:
                            r_obj_path = child_obj.split('/api/')[1]
                            r_obj_type = r_obj_path.split('/')[0]
                            r_obj_name = '-'.join([parent_obj_name,
                                                   r_obj_type])
                            new_r_obj, r_created_objs = self.clone_object(
                                old_name=r_obj_path, new_name=r_obj_name,
                                t_obj=t_obj, ot_obj=ot_obj, oc_obj=oc_obj,
                                force_clone=force_clone, force_unique_name=True)

                            created_objs.append(new_r_obj)
                            created_objs.extend(r_created_objs)
                            new_r_obj_url = new_r_obj['url']

                        if is_list:
                            pobj_attr[referenced][i] = new_r_obj_url
                        else:
                            pobj_attr[referenced] = new_r_obj_url

        except Exception as ex:
            # If an exception occurred, delete any intermediate objects we
            # have created

            self._delete_created_objs(created_objs, (ot_obj['uuid']
                                                     if ot_obj else None))

            raise

        return created_objs

    def _clone_refs_to_tenant(self, parent_obj, refs, t_obj, ot_obj, oc_obj,
                              name=None):

        # Process the list of child objects, refs, of the parent_obj.
        # If the child object is not a global object, then either update the
        # reference to point to an object of the same name in the target tenant
        # or clone the object to the target tenant.

        parent_obj_name = (name or (parent_obj['name']
                                    if 'name' in parent_obj else ''))

        logger.debug('Cloning refs%s',
                     (' for %s' % parent_obj_name if parent_obj_name else ''))

        tenant_uuid = t_obj['uuid'] if t_obj else None
        otenant_uuid = ot_obj['uuid'] if ot_obj else None

        created_objs = []

        try:
            for ref_str in refs:
                ref_split = ref_str.split('/')
                pobj_attr = parent_obj
                for ref_attr in ref_split[:-1]:
                    pobj_attr = pobj_attr.get(ref_attr, {})
                referenced = ref_split[-1]

                if referenced in pobj_attr:
                    child_objs = pobj_attr[referenced]

                    is_list = isinstance(child_objs, list)
                    if not is_list:
                        child_objs = [child_objs]

                    for i in range(len(child_objs)):

                        child_obj = child_objs[i]

                        r_obj_path = child_obj.split('/api/')[1]
                        r_obj_type = r_obj_path.split('/')[0]

                        # Check if the referenced object exists in the target
                        # tenant context (i.e. is global)

                        r_obj = self.dest_api.get(r_obj_path,
                                                  tenant_uuid=otenant_uuid)

                        if r_obj.status_code == 404:
                            logger.debug('Referenced object not available in '
                                         'target (%s)', r_obj_path)
                            # If not global, check for an object of the same
                            # name in the target tenant context

                            if r_obj_path in self.clone_track:
                                # Re-use previously cloned object if
                                # available

                                new_r_obj_url = self.clone_track[child_obj]
                                logger.debug('Reusing previously cloned '
                                                'object %s', new_r_obj_url)
                            else:
                                old_r_obj = self.api.get(r_obj_path,
                                               tenant_uuid=tenant_uuid).json()
                                new_r_obj = self.dest_api.get_object_by_name(
                                               r_obj_type, old_r_obj['name'],
                                               tenant_uuid=otenant_uuid)
                                if new_r_obj:
                                    # If object of same name exists in the
                                    # target tenant context, use this object

                                    logger.debug('Using identically-named '
                                                 ' object "%s"',
                                                 new_r_obj['name'])
                                    new_r_obj_url = new_r_obj['url']
                                else:
                                    # Otherwise clone the object to the target
                                    # tenant context

                                    (new_r_obj,
                                     r_created_objs) = self.clone_object(
                                                     old_name=r_obj_path,
                                                     new_name=old_r_obj['name'],
                                                     t_obj=t_obj, ot_obj=ot_obj,
                                                     oc_obj=oc_obj,
                                                     force_unique_name=True)
                                    created_objs.append(new_r_obj)
                                    created_objs.extend(r_created_objs)
                                    new_r_obj_url = new_r_obj['url']

                            if is_list:
                                pobj_attr[referenced][i] = new_r_obj_url
                            else:
                                pobj_attr[referenced] = new_r_obj_url
        except Exception as ex:
            # If an exception occurred, delete any intermediate objects we
            # have created

            self._delete_created_objs(created_objs, otenant_uuid)

            raise

        return created_objs

    def clone_vs(self, old_vs_name, new_vs_name, enable_vs=False,
                 new_vs_vips=None, new_vs_fips=None, new_fqdns=None,
                 new_segroup=None, tenant=None, other_tenant=None,
                 other_cloud=None, force_clone=None,
                 force_unique_name=False):

        """
        Clones a virtual service object

        Optionally creating the cloned VS in a different tenant and/or a
        different cloud.

        Returns a tuple: json representation of the cloned virtual service,
        list of additional objects created if any

        :param old_vs_name: Name of existing virtual service
        :param new_vs_name: New name for cloned virtual service
        :param enable_vs: Whether the cloned VS should be enabled
        :param new_vs_vips: List of VIPs for cloned VS or ['*'] to use
                            auto-allocation for VIPs and FIPs (source VS must
                            also use auto-allocation)
        :param new_vs_fips: List of FIPs for cloned VS or [None] if FIPs are
                            not used (must have same number of elements as
                            new_vs_vips if specified)
        :param new_fqdns: List of FQDNs for cloned VS or ['*'] to derive FQDN
                            from new_vs_name and domain name in original VS
        :param new_segroup: SE Group to be used by cloned VS or None to use SE
                            group with same name as used by source VS
        :param tenant: Tenant for existing VS (if not specfied, use user's
                        default tenant)
        :param other_tenant: Tenant for cloned VS (if not specified, clone to
                                same tenant as source)
        :param other_cloud: Cloud for cloned VS (if not specified, clone to
                            same cloud as source)
        :param force_clone: List of referenced object attributes to forcibly
                            clone rather than re-use (for example
                            health_monitor_refs)
        :param force_unique_name: Resolve destination name conflicts by
                                    appending an index number
        :return: tuple - json representation of the cloned VS object, list of
                    additional objects created if any
        :rtype: tuple
        """

        # Lookup source and destination tenant and destination cloud if
        # specified

        logger.debug('Cloning virtual service "%s" to "%s"',
                     old_vs_name, new_vs_name)

        force_clone = force_clone or []
        new_vs_vips = new_vs_vips or ['*']
        new_vs_fips = new_vs_fips or [None]
        new_fqdns = new_fqdns or ['*']

        if tenant is None:
            t_obj = None
            tenant_uuid = None
        else:
            t_obj = self.api.get_object_by_name('tenant', tenant)
            if t_obj is None:
                raise Exception('A tenant with name %s could not be found'
                                % tenant)
            tenant_uuid = t_obj['uuid']

        if other_tenant is None:
            ot_obj = None
            otenant_uuid = tenant_uuid
        else:
            ot_obj = self.dest_api.get_object_by_name('tenant', other_tenant)
            if ot_obj is None:
                raise Exception('A tenant with name %s could not be found'
                                % other_tenant)
            otenant_uuid = ot_obj['uuid']

        if other_cloud is None:
            oc_obj = None
        else:
            oc_obj = self.dest_api.get_object_by_name('cloud', other_cloud)
            if oc_obj is None:
                raise Exception('A cloud with name %s could not be found'
                                % other_cloud)

        if new_vs_fips != [None] and len(new_vs_vips) != len(new_vs_fips):
            raise Exception('Cannot clone virtual service if number of VIPs '
                            'and number of FIPs is not equal')

        if old_vs_name.startswith('virtualservice/'):
            v_obj = self.api.get(old_vs_name, tenant_uuid=tenant_uuid).json()
            old_vs_name = v_obj['name']
        else:
            v_obj = self.api.get_object_by_name('virtualservice', old_vs_name,
                                tenant_uuid=tenant_uuid)
        if not v_obj:
            raise Exception('Virtual Service %s could not be found' %
                            old_vs_name)

        c_obj = self.api.get(v_obj['cloud_ref'].split('/api/')[1]).json()

        created_objs = []
        warnings = []

        try:
            # Allocate new VIPs. If auto-allocating then remove existing IP
            # addresses and allow auto_allocate_ip to do the work. Otherwise
            # build a new array of VIPs.

            # For versions prior to 17.1, only a single VIP is supported, and
            # this case (detected by the absence of the 'vips' attribute),
            # only populate the first VIP.

            if new_vs_vips == ['*']:
                v_obj.pop('vsvip_ref', None)
                for vip in v_obj['vip'] if 'vip' in v_obj else [v_obj]:
                    vip.pop('port_uuid', None)
                    if vip['auto_allocate_ip'] is True:
                        vip.pop('ip_address', None)
                    else:
                        raise Exception('Existing VS does not have '
                                        'auto-allocate enabled')
                    if vip['auto_allocate_floating_ip'] is True:
                        vip.pop('floating_ip', None)
            else:
                if 'vip' in v_obj:
                    v_obj.pop('vip', None)
                    v_obj.pop('vsvip_ref', None)
                    if new_vs_fips == [None]:
                        v_obj['vip'] = [{'auto_allocate_ip': False,
                                'enabled': True, 'vip_id': str(c+1),
                                'ip_address': {'type': 'V4', 'addr':
                                new_vs_vip}} for c, new_vs_vip in
                                         enumerate(new_vs_vips)]
                    else:
                        v_obj['vip'] = [{'auto_allocate_ip': False,
                                'auto_allocate_fip': False, 'enabled': True,
                                'vip_id': str(c+1), 'ip_address': {'type': 'V4',
                                'addr': new_vs_vip}, 'floating_ip': {
                                'type': 'V4', 'addr': new_vs_fip}} for c,
                                (new_vs_vip, new_vs_fip) in enumerate(zip(
                                                    new_vs_vips, new_vs_fips))]
                else:
                    v_obj['auto_allocate_ip'] = False
                    v_obj['auto_allocate_fip'] = False
                    v_obj.pop('discovered_networks', None)
                    v_obj['ip_address'] = {'type': 'V4', 'addr': new_vs_vips[0]}
                    if new_vs_fips is None:
                        v_obj.pop('floating_ip', None)
                    else:
                        v_obj['floating_ip'] = {'type': 'V4',
                                                'addr': new_vs_fips[0]}

            # Allocate new FQDNs or create a single FQDN derived from the first
            # FQDN, replacing the hostname part with the new VS name

            if new_fqdns == ['*']:
                if 'dns_info' in v_obj:
                    new_fqdn = new_vs_name + '.' + v_obj['dns_info'][0][
                                'fqdn'].split('.', 1)[1]
                    v_obj['dns_info'] = [{'type': 'DNS_RECORD_A',
                                           'fqdn': new_fqdn}]
            else:
                if new_fqdns != [None]:
                    v_obj['dns_info'] = [{'type': 'DNS_RECORD_A',
                                    'fqdn': new_fqdn} for new_fqdn in new_fqdns]
                else:
                    v_obj.pop('dns_info', None)

            # Clone the pool/pool group used by the VS

            if 'pool_ref' in v_obj:
                p_path = v_obj['pool_ref'].split('/api/')[1]
                p_name = '-'.join([new_vs_name, 'pool'])

                p_obj, p_created_objs = self.clone_object(
                    old_name=p_path, new_name=p_name, t_obj=t_obj,
                    ot_obj=ot_obj, oc_obj=oc_obj, force_clone=force_clone,
                    force_unique_name=True)

                created_objs.append(p_obj)
                created_objs.extend(list(p_created_objs))

                # Update the pool with the cloned pool

                v_obj['pool_ref'] = p_obj['url']

            if 'pool_group_ref' in v_obj:
                pg_path = v_obj['pool_group_ref'].split('/api/')[1]
                pg_name = '-'.join([new_vs_name, 'poolgroup'])

                pg_obj, pg_created_objs = self.clone_object(
                    old_name=pg_path, new_name=pg_name, t_obj=t_obj,
                    ot_obj=ot_obj, oc_obj=oc_obj, force_clone=force_clone,
                    force_unique_name=True)

                created_objs.append(pg_obj)
                created_objs.extend(list(pg_created_objs))

                # Update the pool group with the cloned pool group

                v_obj['pool_group_ref'] = pg_obj['url']

            # Remove unique atributes and rename

            v_obj.pop('uuid', None)
            v_obj_old_url = v_obj.pop('url', None)
            v_obj.pop('vip_runtime', None)
            v_obj['name'] = new_vs_name

            # Remove site persistency references

            if v_obj.pop('sp_pool_refs', None):
                warnings.append('VS was linked to a GSLB service with site '
                                'persistency. Linkage removed in cloned VS.')

            # (Try to!) move the new virtual service to a different cloud

            if oc_obj:
                v_obj['cloud_ref'] = oc_obj['url']
                v_obj.pop('cloud_type')

                # If moving to a different cloud and a new SE group is not
                # specified, try to find an SE group
                # with the same name as the source virtual service's SE group

                if new_segroup is None:
                    seg_obj = self.api.get(
                                v_obj['se_group_ref'].split('/api/')[1],
                                tenant_uuid=tenant_uuid).json()
                    new_segroup = seg_obj['name']

                # If moving to a different cloud, virtual service will be moved
                # to the default global VRF in the target cloud

                v_obj.pop('vrf_context_ref', None)

            if new_segroup is not None:
                # Locate SE group by name in the appropriate cloud

                cloud_url = c_obj['url'] if oc_obj is None else oc_obj['url']

                new_seg_objs = self.get_all_objects_by_name(
                                'serviceenginegroup', new_segroup,
                                tenant_uuid=otenant_uuid,
                                api_to_use=self.dest_api)

                new_seg_obj = [new_seg_obj for new_seg_obj in new_seg_objs if
                               new_seg_obj['cloud_ref'] == cloud_url]

                # If can't find an SE group with matching name, raise an error

                try:
                    v_obj['se_group_ref'] = new_seg_obj[0]['url']
                except IndexError:
                    raise Exception('A service engine group with name %s could'
                                    ' not be found' % new_segroup)

            v_obj['enabled'] = enable_vs

            # Clone any HTTP policy sets referenced in the VS

            if 'http_policies' in v_obj:
                for polset in v_obj['http_policies']:
                    ps_path = polset['http_policy_set_ref'].split('/api/')[1]
                    ps_name = '-'.join([new_vs_name,
                                        (c_obj['name']
                                         if oc_obj is None
                                         else oc_obj['name']),
                                        'HTTP-Policy-Set'])
                    ps_obj, ps_created_objs = self.clone_object(
                        old_name=ps_path, new_name=ps_name, t_obj=t_obj,
                        ot_obj=ot_obj, oc_obj=oc_obj, force_clone=force_clone,
                        force_unique_name=True)

                    polset['http_policy_set_ref'] = ps_obj['url']
                    created_objs.append(ps_obj)
                    created_objs.extend(list(ps_created_objs))

            # Clone any DNS policy sets referenced in the VS

            if 'dns_policies' in v_obj:
                for polset in v_obj['dns_policies']:
                    ps_path = polset['dns_policy_ref'].split('/api/')[1]
                    ps_name = '-'.join([new_vs_name,
                                        (c_obj['name']
                                         if oc_obj is None
                                         else oc_obj['name']),
                                        'DNS-Policy'])
                    ps_obj, ps_created_objs = self.clone_object(
                        old_name=ps_path, new_name=ps_name, t_obj=t_obj,
                        ot_obj=ot_obj, oc_obj=oc_obj, force_clone=force_clone,
                        force_unique_name=True)

                    polset['dns_policy_ref'] = ps_obj['url']
                    created_objs.append(ps_obj)
                    created_objs.extend(list(ps_created_objs))

            # Clone network security policy referenced in the VS

            if 'network_security_policy_ref' in v_obj:
                ns_path = v_obj['network_security_policy_ref'].split('/api/')[1]
                ns_name = '-'.join(['vs', new_vs_name,
                                    (c_obj['name']
                                         if oc_obj is None
                                         else oc_obj['name']),
                                        'ns'])
                ns_obj, ns_created_objs = self.clone_object(
                        old_name=ns_path, new_name=ns_name, t_obj=t_obj,
                        ot_obj=ot_obj, oc_obj=oc_obj, force_clone=force_clone,
                        force_unique_name=True)

                v_obj['network_security_policy_ref'] = ns_obj['url']
                created_objs.append(ns_obj)
                created_objs.extend(list(ns_created_objs))

            # Clone any datascripts referenced in the VS

            if 'vs_datascripts' in v_obj:
                for dsset in v_obj['vs_datascripts']:
                    ds_path = dsset['vs_datascript_set_ref'].split('/api/')[1]
                    ds_name = '-'.join([new_vs_name, (c_obj['name']
                                                      if oc_obj is None
                                                      else oc_obj['name']),
                                        'DataScript-Set'])
                    ds_obj, ds_created_objs = self.clone_object(
                        old_name=ds_path, new_name=ds_name, t_obj=t_obj,
                        ot_obj=ot_obj, oc_obj=oc_obj, force_clone=force_clone,
                        force_unique_name=True)

                    dsset['vs_datascript_set_ref'] = ds_obj['url']

                    created_objs.append(ds_obj)
                    created_objs.extend(list(ds_created_objs))

                    if ds_created_objs:
                        warnings.append('VS contains DataScripts with '
                                        'references to objects that were '
                                        'cloned. It will be necessary to '
                                        'update the script with the cloned '
                                        'object names.')

            valid_ref_objects = self.VALID_VS_REF_OBJECTS

            # Clone rather than re-use any references in the force_clone list
            # but re-use previously cloned objects rather than creating
            # multiple identical clones

            refs_to_clone = [ref for key, ref in valid_ref_objects.items()
                             if key in force_clone]

            new_objs = self._clone_refs(parent_obj=v_obj, refs=refs_to_clone,
                                        t_obj=t_obj, ot_obj=ot_obj,
                                        oc_obj=oc_obj)

            created_objs.extend(list(new_objs))

            # If moving to a different tenant, clone any tenant-specific
            # referenced objects

            if ot_obj or self.api != self.dest_api:
                refs_to_clone = [ref for key, ref in valid_ref_objects.items()
                                 if key not in force_clone]
                new_objs = self._clone_refs_to_tenant(parent_obj=v_obj,
                                                      refs=refs_to_clone,
                                                      t_obj=t_obj,
                                                      ot_obj=ot_obj,
                                                      oc_obj=oc_obj)

                created_objs.extend(list(new_objs))

            # Try to create the new VS (possibly in a different tenant to the
            # source)

            r = self.dest_api.post('virtualservice', v_obj,
                                    tenant_uuid=otenant_uuid)

            if r.status_code < 300:
                new_vs = r.json()
                self.actions += ['Cloned virtual service "%s"%s to "%s"%s%s' %
                                 (old_vs_name,
                                 (' in tenant "%s"' % t_obj['name'])
                                  if t_obj else '', new_vs_name,
                                 (' in tenant "%s"' % ot_obj['name'])
                                  if ot_obj else '',
                                 (' in cloud "%s"' % oc_obj['name'])
                                  if oc_obj else '')]
                logger.debug('Created virtual service "%s"', new_vs['url'])
                if v_obj_old_url:
                    self.clone_track[v_obj_old_url] = new_vs['url']
                return new_vs, created_objs, warnings
            else:
                exception_string = ('Unable to clone virtual service "%s" '
                                    'as "%s" (%d:%s)' % (old_vs_name,
                                                         new_vs_name,
                                                         r.status_code,
                                                         r.text))
                logger.debug(exception_string)
                logger.debug(v_obj)
                raise Exception(exception_string)

        except Exception as ex:
            # If an exception occurred, delete any intermediate objects we have
            # created

            self._delete_created_objs(created_objs, otenant_uuid)

            raise Exception('%s\r\n=> Unable to clone virtual service "%s" '
                            'as "%s"' % (ex, old_vs_name, new_vs_name))

# MAIN PROGRAM

if __name__ == '__main__':
    print('%s version %s' % (sys.argv[0], '.'.join(str(v) for v in
                                                   AVICLONE_VERSION)))
    print()

    # Build the command-line parameter parser

    pool_valid_refs = sorted(
           set(AviClone.VALID_POOL_REF_OBJECTS.keys()) |
           set(AviClone.VALID_POLICYSET_REF_OBJECTS.keys()) |
           set(AviClone.VALID_DATASCRIPT_REF_OBJECTS.keys()) |
           set(AviClone.VALID_APPLICATIONPROFILE_REF_OBJECTS.keys()))
    vs_valid_refs = sorted(set(pool_valid_refs) |
                         set(AviClone.VALID_VS_REF_OBJECTS.keys()))

    parser = argparse.ArgumentParser(description='')
    parser.add_argument('-c', '--controller',
                        help='FQDN or IP address of Avi Vantage controller')
    parser.add_argument('-u', '--user', help='Avi Vantage username',
                        default='admin')
    parser.add_argument('-p', '--password', help='Avi Vantage password')
    parser.add_argument('-x', '--api_version',
                        help='Avi Vantage API version (default=%s)'
                        % DEFAULT_API_VERSION,
                        default=DEFAULT_API_VERSION)
    parser.add_argument('-dc', '--destcontroller',
                        help='FQDN or IP address of target Avi controller')
    parser.add_argument('-du', '--destuser', help='Avi Vantage username',
                        default='admin')
    parser.add_argument('-dp', '--destpassword', help='Avi Vantage password')
    parser.add_argument('-debug', help='Enable debug logging',
                        action='store_true')
    parser.add_argument('-dryrun', help='Allows a dry-run to be performed. '
                                        'Performs the clone, then waits '
                                        'for user input and then deletes '
                                        'the created objects.',
                        action='store_true')
    type_parser = parser.add_subparsers(help='Type of object to clone',
                                metavar='object_type', dest='obj_type')
    vs_parser = type_parser.add_parser('vs', help='Clone a Virtual Service')
    vs_parser.add_argument('vs_name',
                           help='Name of an existing Virtual Service')
    vs_parser.add_argument('new_vs_names',
               help='Name(s) to be assigned to the cloned Virtual Service(s)')
    vs_parser.add_argument('-v', '--vips',
          help='The new VIP or list of VIPs (optionally specify list of FIPs '
          'after ;) or * for auto-allocation', metavar='VIPs', default='*')
    vs_parser.add_argument('-d', '--fqdns',
        help='The new FQDN or list of FQDNs or * to derive from the VS name',
                           metavar='FQDNs', default='')
    vs_parser.add_argument('-e', '--enable',
        help='Enable the cloned Virtual Service', action='store_true')
    vs_parser.add_argument('-t', '--tenant',
                    help='Scope to a particular tenant', metavar='tenant')
    vs_parser.add_argument('-2t', '--totenant',
                           help='Clone the service to a different tenant',
                           metavar='other_tenant')
    vs_parser.add_argument('-2c', '--tocloud',
                           help='Clone the service to a different cloud',
                           metavar='other_cloud')
    vs_parser.add_argument('-g', '--segroup',
             help='The optional new SE group for the cloned Virtual Service',
                           metavar='se_group')
    vs_parser.add_argument('-fc', '--forceclone',
                           help='List of references to forcibly clone '
                           'rather than re-use. Valid values are: %s'
                           % ', '.join(vs_valid_refs),
                           metavar='ref_list',
                           default=[])
    pool_parser = type_parser.add_parser('pool', help='Clone a Pool')
    pool_parser.add_argument('pool_name', help='Name of an existing Pool')
    pool_parser.add_argument('new_pool_names',
                        help='Name(s) to be assigned to the cloned Pool(s)')
    pool_parser.add_argument('-t', '--tenant',
                             help='Scope to a particular tenant',
                             metavar='tenant')
    pool_parser.add_argument('-2t', '--totenant',
                             help='Clone the pool to a different tenant',
                             metavar='other_tenant')
    pool_parser.add_argument('-2c', '--tocloud',
                             help='Clone the pool to a different cloud',
                             metavar='other_cloud')
    pool_parser.add_argument('-fc', '--forceclone',
                             help='List of references to forcibly clone '
                             'rather than re-use. Valid values are: %s'
                             % ', '.join(pool_valid_refs),
                             metavar='ref_list',
                             default=[])
    pool_group_parser = type_parser.add_parser('poolgroup',
                                               help='Clone a Pool Group')
    pool_group_parser.add_argument('pool_group_name',
                                   help='Name of an existing Pool Group')
    pool_group_parser.add_argument('new_pool_group_names',
                    help='Name(s) to be assigned to the cloned Pool Group(s)')
    pool_group_parser.add_argument('-t', '--tenant',
                      help='Scope to a particular tenant', metavar='tenant')
    pool_group_parser.add_argument('-2t', '--totenant',
                            help='Clone the pool group to a different tenant',
                                   metavar='other_tenant')
    pool_group_parser.add_argument('-2c', '--tocloud',
                            help='Clone the pool group to a different cloud',
                                   metavar='other_cloud')
    pool_group_parser.add_argument('-fc', '--forceclone',
                                   help='List of references to forcibly clone '
                                   'rather than re-use. Valid values are: %s'
                                   % ', '.join(pool_valid_refs),
                                   metavar='ref_list',
                                   default=[])
    generic_parser = type_parser.add_parser('generic',
                      help='Clone a generic object')
    generic_parser.add_argument('object_type',
                      help='Type of object to clone (e.g. applicationprofile)')
    generic_parser.add_argument('generic_name',
                      help='Name of an existing object')
    generic_parser.add_argument('new_generic_names',
                      help='Name(s) to be assigned to the cloned object(s)')
    generic_parser.add_argument('-t', '--tenant',
                      help='Scope to a particular tenant',
                             metavar='tenant')
    generic_parser.add_argument('-2t', '--totenant',
                      help='Clone the object to a different tenant',
                      metavar='other_tenant')
    generic_parser.add_argument('-fc', '--forceclone',
                                 help='List of references to forcibly clone '
                                 'rather than re-use',
                                 metavar='ref_list',
                                 default=[])

    args = parser.parse_args()

    if args and args.obj_type:

        # If not specified on the command-line, prompt the user for the
        # controller IP address and/or password

        logger = logging.getLogger('clonevs')

        if args.debug:
            logger.setLevel(logging.DEBUG)
            logger.debug('Debugging enabled')

        controller = args.controller
        user = args.user
        password = args.password

        controller2 = args.destcontroller
        user2 = args.destuser
        password2 = args.destpassword

        try:
            while not controller:
                controller = input('Controller:')

            while not password:
                password = getpass.getpass('Password for %s@%s:' %
                                           (user, controller))

            if controller2:
                if not args.tocloud and args.obj_type in ['vs', 'pool',
                                                          'poolgroup']:
                    raise Exception('Destination cloud should be specified '
                                    'when cloning %s to a different '
                                    'controller' % args.obj_type)

                while not password2:
                    password = getpass.getpass('Password for %s@%s:' %
                                               (user2, controller2))

            # Create the API session

            print('Creating API session...', end='')
            api = ApiSession.get_session(controller, user, password,
                                         api_version=args.api_version)
            print('OK!')
            print()

            # Create destination API session to a second controller

            if controller2:
                print('Creating destination API session...', end='')
                api2 = ApiSession.get_session(controller2, user2, password2,
                                              api_version=args.api_version)
                print('OK!')
                print()
            else:
                api2 = None

            # Create an instance of our cloning class

            cl = AviClone(api, api2)

            force_clone = (args.forceclone.split(',')
                           if args.forceclone else None)

            all_created_objs = []

            if args.obj_type == 'vs':
                # Loop through the clone names and clone the source VS for
                # each destination

                new_vs_names = args.new_vs_names.split(',')
                num_new_vs = len(new_vs_names)

                vipsfips = args.vips.split(';')
                vips = (['*'] * num_new_vs
                        if args.vips == '*' else vipsfips[0].split(','))
                fips = ([None] * num_new_vs
                        if (args.vips == '*' or len(vipsfips) == 1)
                        else vipsfips[1].split(','))
                fqdns = (['*'] * num_new_vs
                         if args.fqdns == '*' else args.fqdns.split(',')
                         if args.fqdns else [None] * num_new_vs)

                if num_new_vs == 1:
                    # If we only have a single destination VS name, assume the
                    # provided VIPs/FIPs/FQDNs are multi-values for a single
                    # VS rather than values per new VS

                    vips = [vips]
                    fips = [fips]
                    fqdns = [fqdns]
                else:
                    # Otherwise, make sure we have the same number of VIPs,
                    # FIPs, FQDNs as the number of provided VS names

                    if len(vips) == len(fips) == len(fqdns) == num_new_vs:
                        vips = [[vip] for vip in vips]
                        fips = [[fip] for fip in fips]
                        fqdns = [[fqdn] for fqdn in fqdns]
                    else:
                        raise Exception('Number of VIPs, FIPs and FQDNs '
                                        'specified should match the number of '
                                        'new virtual services')

                for new_vs_name, new_vips, new_fips, new_fqdns in \
                        zip(new_vs_names, vips, fips, fqdns):
                    spprint('Trying to clone VS %s%s to %s%s%s...'
                            % (args.vs_name, ' ['+args.tenant+']'
                               if args.tenant else '',
                               new_vs_name,
                               ' ['+args.totenant+']'
                               if args.totenant else '',
                               ' in cloud '+args.tocloud
                               if args.tocloud else ''),
                            flush=True)
                    new_vs, cloned_objs, warnings = cl.clone_vs(args.vs_name,
                                            new_vs_name, args.enable, new_vips,
                                            new_fips, new_fqdns, args.segroup,
                                            args.tenant, args.totenant,
                                            args.tocloud, force_clone,
                                            False)
                    all_created_objs.append(new_vs)
                    all_created_objs.extend(cloned_objs)
                    if warnings:
                        print('OK with warnings:')
                        print()
                        for w in warnings:
                            spprint(w, end='', flush=True)
                        print()
                    else:
                        print('OK!')
                    print()

                    print('New Virtual Service created as follows:')
                    print('%10s: %s' % ('Name', new_vs['name']))
                    print('%10s: %s' % ('VIP(s)', ','.join([ipa['ip_address'][
                                        'addr'] for ipa in new_vs['vip']]) if
                            'vip' in new_vs else new_vs['ip_address']['addr']))
                    print('%10s: %s' % ('FIP(s)', ','.join([(ipa['floating_ip'][
                                        'addr'] if 'floating_ip' in ipa else
                                        'N/A') for ipa in new_vs['vip']]) if
                                        'vip' in new_vs else (new_vs[
                                        'floating_ip']['addr'] if
                                        'floating_ip' in new_vs else 'N/A')))
                    if 'dns_info' in new_vs:
                        print('%10s: %s' % ('FQDN(s)',
                         ','.join([dns['fqdn'] for dns in new_vs['dns_info']])))
                    print('%10s: %s' % ('State', 'Enabled' if new_vs['enabled']
                                                               else 'Disabled'))
                    if args.totenant:
                        print('%10s: %s' % ('Tenant', args.totenant))
                    if args.tocloud:
                        print('%10s: %s' % ('Cloud', args.tocloud))
                    print()
            elif args.obj_type == 'pool':
                # Loop through the clone names and clone the source pool for
                # each destination

                for new_pool_name in args.new_pool_names.split(','):
                    spprint('Trying to clone pool %s%s to %s%s%s...'
                            % (args.pool_name, ' ['+args.tenant+']'
                               if args.tenant else '',
                               new_pool_name,
                               ' ['+args.totenant+']'
                               if args.totenant else '',
                               ' in cloud '+args.tocloud
                               if args.tocloud else ''),
                            flush=True)

                    new_pool, cloned_objs = cl.clone_object(
                        object_type='pool',
                        old_name=args.pool_name, new_name=new_pool_name,
                        tenant=args.tenant, other_tenant=args.totenant,
                        other_cloud=args.tocloud, force_clone=force_clone,
                        force_unique_name=False)
                    all_created_objs.append(new_pool)
                    all_created_objs.extend(cloned_objs)
                    print('OK!')
                    print()

                    print('New Pool created as follows:')
                    print('%10s: %s' % ('Name', new_pool['name']))
                    if args.totenant:
                        print('%10s: %s' % ('Tenant', args.totenant))
                    if args.tocloud:
                        print('%10s: %s' % ('Cloud', args.tocloud))
                    print()

            elif args.obj_type == 'poolgroup':
                # Loop through the clone names and clone the source pool group
                # for each destination

                for new_pool_group_name in args.new_pool_group_names.split(','):
                    spprint('Trying to clone pool group %s%s to %s%s%s...'
                            % (args.pool_group_name,
                               ' ['+args.tenant+']'
                               if args.tenant else '',
                               new_pool_group_name,
                               ' ['+args.totenant+']'
                               if args.totenant else '',
                               ' in cloud '+args.tocloud
                               if args.tocloud else ''),
                            flush=True)
                    new_poolgroup, cloned_objs = cl.clone_object(
                        object_type='poolgroup',
                        old_name=args.pool_group_name,
                        new_name=new_pool_group_name,
                        tenant=args.tenant, other_tenant=args.totenant,
                        other_cloud=args.tocloud, force_clone=force_clone,
                        force_unique_name=False)
                    all_created_objs.append(new_poolgroup)
                    all_created_objs.extend(cloned_objs)
                    print('OK!')
                    print()

                    print('New Pool Group created as follows:')
                    print('%10s: %s' % ('Name', new_poolgroup['name']))
                    if args.totenant:
                        print('%10s: %s' % ('Tenant', args.totenant))
                    if args.tocloud:
                        print('%10s: %s' % ('Cloud', args.tocloud))
                    print()

            elif args.obj_type == 'generic':
                # Loop through the clone names and clone the source object for
                # each destination

                for new_gen_name in args.new_generic_names.split(','):
                    spprint('Trying to clone object of type %s with '
                            'name %s%s to %s%s...'
                            % (args.object_type, args.generic_name,
                              ' ['+args.tenant+']'
                              if args.tenant else '',
                              new_gen_name,
                              ' ['+args.totenant+']'
                              if args.totenant else ''),
                            flush=True)
                    new_gen, cloned_objs = cl.clone_object(
                                                  object_type=args.object_type,
                                                  old_name=args.generic_name,
                                                  new_name=new_gen_name,
                                                  tenant=args.tenant,
                                                  other_tenant=args.totenant,
                                                  force_unique_name=False)
                    all_created_objs.append(new_gen)
                    all_created_objs.extend(cloned_objs)
                    print('OK!')
                    print()

                    print('New object of type %s created as follows:'
                          % (args.object_type))
                    print('%10s: %s' % ('Name', new_gen['name']))
                    if args.totenant:
                        print('%10s: %s' % ('Tenant', args.totenant))
                    print()

            # Display the actions taken by the cloning class

            print('-' * 32)
            print('Actions taken were:')
            for index, action in enumerate(cl.actions):
                spprint('%2d. %s' % (index + 1, action), '    ')

            if args.dryrun:
                input('Dry-run: Hit ENTER to delete all cloned objects')
                cl.delete_objects(objs=all_created_objs,
                                  tenant=args.totenant or args.tenant)

        except Exception as ex:
            print()
            print(ex)
    else:
        parser.print_help()

'''
Notes:

For help, use:

clone_vs.py -h

For detailed help on cloning a specific object, use for example:

clone_vs.py vs -h

The script allows the cloning of virtual services, pools, pool groups and
generic objects (that have no child references).

The script clones any additional objects that are required, so for example
when cloning a virtual service, the pools and/or pool groups used by that
VS, including any specified in context-switching rules, will also be cloned.

The script also allows the cloning of objects into a different tenant and/or 
cloud than the source - the destination may also be on a different Avi Vantage
controller.

These advanced cloning options may not always be successful because the source 
and destination tenant/cloud/controllers may have different properties. If the
clone attempt fails, the script will automatically delete any objects that it
created along the way.

By default, re-usable objects/profiles such as application profiles, health
monitors, persistency profiles etc. are not cloned so that the cloned object
simply refers to the same simply refers to the same objects as the original.
However, when cloning to a different tenant, the behaviour is slightly
different:

If a re-usable object was defined in the admin tenant, it is available in all
tenants and will not be cloned by default. If a re-usable objects was defined
in the source tenant, the script looks for an object with the same name in the
destination tenant first, but if no identically-named object is available, the
object will be cloned to the destination.

This behaviour can be overridden using the "forceclone" option, which ensures
that the specified references are always cloned rather than re-used.

For example, to forcibly clone health monitors, use the option:

--forceclone pool-healthmonitor

The full list of supported options is displayed in the help.

If the object to be cloned uses features specific to a particular minimum Avi
Vantage s/w release, it may be necessary to specify the API version using the
-x parameter.

Some known limitations:
* Cloning a VS with automatic address allocation to a different cloud is likely
  to fail (unless static VIPs/FIPs are specified)
* Cloning a VS to a cloud of a different type to the source cloud is more
  likely to fail as it may reference shared objects which do not make sense in
  the destination cloud
* Cloning an application profile with caching/compression policies to a
  different tenant or controller will not work currently. As a workaround,
  manually pre-create an application profile with the same name in the target
  prior to cloning the VS.
  currently succeed in most cases. This can be worked around
* Cloning of an SSL/TLS certificate will not succeed due to the private key
  being protected. If cloning between tenants or to a different controller,
  ensure an SSL/TLS certificate with the same name as the source is available
  in the destination prior to cloning.
* Cloning a VS to a different tenant/cloud will try to find an SE group with
  the same name as referenced in the source VS but if no match is found, will
  place into the Default SE group instead
* The script has been primarily written for and tested with Linux/VMWare/AWS
  clouds - it may not work as-is for other clouds
* Under bash on Linux, remember to escape the * character with a backslash if
  passed as a parameter (e.g. in -v).
'''
