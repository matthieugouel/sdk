import csv
import logging
import os
import copy
import re
import avi.netscaler_converter.ns_constants as ns_constants

from avi.netscaler_converter.ns_constants import (STATUS_SKIPPED,
                                                  STATUS_SUCCESSFUL,
                                                  STATUS_INDIRECT,
                                                  STATUS_NOT_APPLICABLE,
                                                  STATUS_PARTIAL,
                                                  STATUS_DATASCRIPT,
                                                  STATUS_INCOMPLETE_CONFIGURATION,
                                                  STATUS_COMMAND_NOT_SUPPORTED)

LOG = logging.getLogger(__name__)

csv_writer = None
csv_writer_dict_list = []


def upload_file(file_path):
    """
    Reads the given file and returns the UTF-8 string
    :param file_path: Path of file to read
    :return: UTF-8 string read from file
    """

    file_str = None
    try:
        with open(file_path, "r") as file_obj:
            file_str = file_obj.read()
            file_str = file_str.decode("utf-8")
    except UnicodeDecodeError:
        try:
            file_str = file_str.decode('latin-1')
        except:
            LOG.error("Error to read file %s" % file_path, exc_info=True)
    except:
        LOG.error("Error to read file %s" % file_path, exc_info=True)
    return file_str


def add_conv_status(line_no, cmd, object_type, full_command, conv_status,
                    avi_object=None):
    """
    Adds as status row in conversion status csv
    :param cmd: netscaler command
    :param conv_status: dict of conversion status
    :param avi_object: Converted objectconverted avi object
    """

    row = {
        'Line Number': line_no if line_no else '',
        'Netscaler Command': cmd if cmd else '',
        'Object Name': object_type if object_type else '',
        'Full Command': full_command if full_command else '',
        'Status': conv_status.get('status', ''),
        'Skipped settings': str(conv_status.get('skipped', '')),
        'Indirect mapping': str(conv_status.get('indirect', '')),
        'Not Applicable': str(conv_status.get('na_list', '')),
        'User Ignored': str(conv_status.get('user_ignore', '')),
        'AVI Object': str(avi_object) if avi_object else ''
    }
    csv_writer_dict_list.append(row)


def add_complete_conv_status(csv_file, ns_config):
    """
    Adds as status row in conversion status csv
    :param cmd: netscaler command
    :param conv_status: dict of conversion status
    :param avi_object: Converted objectconverted avi object
    """

    global csv_writer_dict_list
    global csv_writer
    for config_key in ns_config:
        config_object = ns_config[config_key]
        for element_key in config_object:
            element_object_list = config_object[element_key]
            if isinstance(element_object_list, dict):
                element_object_list = [element_object_list]
            for element_object in element_object_list:
                match = [match for match in csv_writer_dict_list
                         if match['Line Number'] == element_object['line_no']]
                if not match:
                    ns_complete_command = \
                        get_netscalar_full_command(config_key, element_object)
                    # Add status incomplete configuration
                    add_status_row(element_object['line_no'], config_key,
                                   element_object['attrs'][0],
                                   ns_complete_command,
                                   STATUS_INCOMPLETE_CONFIGURATION)

    unique_line_number_list = set()
    row_list = []
    for dict_row in csv_writer_dict_list:
        if dict_row['Line Number'] not in unique_line_number_list:
            unique_line_number_list.add(dict_row['Line Number'])
            row_list.append(dict_row)
        else:
            row = [row for row in row_list
                   if row['Line Number'] == dict_row['Line Number']]
            if dict_row.get('AVI Object', None):
                row[0]['AVI Object'] += ' %s' % dict_row['AVI Object']

    for row in row_list:
        csv_writer.writerow(row)


def add_status_row(line_no, cmd, object_type, full_command, status,
                   avi_object=None):
    """
    Adds as status row in conversion status csv
    :param cmd: netscaler command
    :param status: conversion status
    """

    global csv_writer_dict_list
    row = {
        'Line Number': line_no if line_no else '',
        'Netscaler Command': cmd,
        'Object Name': object_type,
        'Full Command': full_command,
        'Status': status,
        'AVI Object': str(avi_object) if avi_object else ''
    }
    csv_writer_dict_list.append(row)


def add_csv_headers(csv_file):
    """
    Adds header line in conversion status file
    :param csv_file: File to which header is to be added
    """

    global csv_writer
    fieldnames = ['Line Number', 'Netscaler Command', 'Object Name',
                  'Full Command', 'Status', 'Skipped settings',
                  'Indirect mapping', 'Not Applicable', 'User Ignored',
                  'AVI Object']
    csv_writer = csv.DictWriter(csv_file, fieldnames=fieldnames,
                                lineterminator='\n',)

    csv_writer.writeheader()


def get_avi_lb_algorithm(ns_algorithm):
    """
    Converts f5 LB algorithm to equivalent avi LB algorithm
    :param ns_algorithm: f5 algorithm name
    :return: Avi LB algorithm enum value
    """

    avi_algorithm = 'LB_ALGORITHM_ROUND_ROBIN'
    if not ns_algorithm or ns_algorithm == 'ROUNDROBIN':
        avi_algorithm = 'LB_ALGORITHM_ROUND_ROBIN'
    elif ns_algorithm in ['LEASTRESPONSETIME', 'LRTM']:
        avi_algorithm = 'LB_ALGORITHM_FASTEST_RESPONSE'
    elif ns_algorithm == 'SOURCEIPHASH':
        avi_algorithm = 'LB_ALGORITHM_CONSISTENT_HASH'
    elif ns_algorithm == 'URLHASH':
        avi_algorithm = 'LB_ALGORITHM_CONSISTENT_HASH_URI'
    return avi_algorithm


def get_avi_resp_code(respCode):
    """
    This function used for getting appropriate response code for avi.
    :param respCode: response code
    :return: returns list of unique responses.
    """

    avi_resp_codes = []
    codes = respCode.split(' ')
    for code in codes:
        if code < 200:
            avi_resp_codes.append({"code": "HTTP_1XX"})
        elif code < 300:
            avi_resp_codes.append({"code": "HTTP_2XX"})
        elif code < 400:
            avi_resp_codes.append({"code": "HTTP_3XX"})
        elif code < 500:
            avi_resp_codes.append({"code": "HTTP_4XX"})
        elif code < 600:
            avi_resp_codes.append({"code": "HTTP_5XX"})
    return list(set(avi_resp_codes))


def get_conv_status(ns_object, skipped_list, na_list, indirect_list,
                    ignore_for_val=None, indirect_commands = None):
    """
    This function used for getting status detail for command like
    skipped or indirect.
    :param ns_object: Netscaler parsed config
    :param skipped_list: list of skipped commands list.
    :param na_list: not applicable commands list.
    :param indirect_list: indirect command list
    :param ignore_for_val: optional field
    :param indirect_commands: indirect commands
    :return: returns dict of coversion status.
    """

    skipped = [attr for attr in ns_object.keys() if attr in skipped_list]
    na = [attr for attr in ns_object.keys() if attr in na_list]
    indirect = [attr for attr in ns_object.keys() if attr in indirect_list]
    if ignore_for_val:
        for key in ignore_for_val.keys():
            if key not in ns_object:
                continue
            ns_val = ns_object.get(key)
            ignore_val = ignore_for_val.get(key)
            if key in skipped and str(ns_val) == str(ignore_val):
                skipped.remove(key)
    if skipped:
        status = STATUS_PARTIAL
    else:
        status = STATUS_SUCCESSFUL

    conv_status = {
        'skipped': skipped,
        'indirect': indirect,
        'na_list': na,
        'status': status
    }
    return conv_status



def get_key_cert_obj(name, key_file_name, cert_file_name, input_dir):
    """
    :param name:name of ssl cert.
    :param key_file_name:  key file (ie.pem)
    :param cert_file_name: certificate file name
    :param input_dir: input directory for certificate file name
    :return: returns dict of ssl object
    """
    folder_path = input_dir + os.path.sep
    key = upload_file(folder_path + key_file_name)
    cert = upload_file(folder_path + cert_file_name)
    ssl_kc_obj = None
    if key and cert:
        cert = {"certificate": cert}
        ssl_kc_obj = {
            'name': name,
            'key': key,
            'certificate': cert,
            'key_passphrase': ''
        }
    return ssl_kc_obj


def get_command_from_line(line):
    """
    This function is used for getting command and line number from conf file.
    :param line: line
    :return: returns command name and line
    """

    cmd = ''
    line_no = 0
    for member in line:
        if 'line_no' in member:
            line_no = member[1]
            continue
        if isinstance(member, str):
            cmd += ' %s' % member
        else:
            cmd += ' -%s' % ' '.join(member)
    return cmd, line_no


def update_status_for_skipped(skipped_cmds):
    """
    :param skipped_cmds: separation of non converted commands
     to NA, Indirect,DataScript,NotSupported
    :return: None
    """

    na_cmds = ns_constants.netscalar_command_status['NotApplicableCommands']
    indirect_cmds = ns_constants.netscalar_command_status['IndirectCommands']
    datascript_cmds = ns_constants.netscalar_command_status['DatascriptCommands']
    not_supported = ns_constants.netscalar_command_status['NotSupported']
    if not skipped_cmds:
        return
    for cmd in skipped_cmds:
        line_no = cmd['line_no']
        cmd = cmd['cmd']
        cmd = cmd.strip()
        for na_cmd in na_cmds:
            if cmd.startswith(na_cmd):
                # Add status not applicable in csv/report
                add_status_row(line_no, na_cmd, None, cmd,
                               STATUS_NOT_APPLICABLE)
                break
        for id_cmd in indirect_cmds:
            if cmd.startswith(id_cmd):
                # Add status indirect in csv/report
                add_status_row(line_no, id_cmd, None, cmd, STATUS_INDIRECT)
                break
        for datascript_cmd in datascript_cmds:
            if cmd.startswith(datascript_cmd):
                # Add status datascript in csv/report
                add_status_row(line_no, datascript_cmd, None, cmd,
                               STATUS_DATASCRIPT)
                break
        for not_commands in not_supported:
            if cmd.startswith(not_commands):
                # Add status not not supported in csv/report
                add_status_row(line_no, not_commands, None, cmd,
                               STATUS_COMMAND_NOT_SUPPORTED)
                break


def remove_duplicate_objects(obj_type, obj_list):
    """
    Remove duplicate objects from list
    :param obj_type: Object type
    :param obj_list: list of all objects
    :return: return list which has no duplicates objects
    """

    if len(obj_list) == 1:
        return obj_list
    for source_obj in obj_list:
        for index, tmp_obj in enumerate(obj_list):
            if tmp_obj["name"] == source_obj["name"]:
                continue
            src_cp = copy.deepcopy(source_obj)
            tmp_cp = copy.deepcopy(tmp_obj)
            del src_cp["name"]
            if "description" in src_cp:
                del src_cp["description"]

            del tmp_cp["name"]
            if "description" in tmp_cp:
                del tmp_cp["description"]
            if cmp(src_cp, tmp_cp) == 0:
                LOG.warn('Remove duplicate %s object : %s' % (obj_type,
                                                              tmp_obj["name"]))
                del obj_list[index]
                remove_duplicate_objects(obj_type, obj_list)
    return obj_list

def cleanup_config(config):
    """
    This function is used for deleting temp variables created for conversion
    :param config: dict type
    :return: None
    """

    del config

def clone_pool(pool_name, prefix, avi_config):
    """
    This function used for cloning shared pools in netscaler.
    :param pool_name: name of pool
    :param prefix: cloned for
    :param avi_config: avi config dict
    :return: None
    """

    pools = [pool for pool in avi_config['Pool'] if pool['name'] == pool_name]
    if pools:
        pool_obj = copy.deepcopy(pools[0])
        pool_name = re.sub('[:]', '-', prefix + pool_obj['name'])
        pool_obj['name'] = pool_name
        avi_config['Pool'].append(pool_obj)
        LOG.info("Same pool reference to other object. Clone Pool %s for %s" %
                 (pool_name, prefix))
        return pool_obj['name']
    return None

def get_vs_if_shared_vip(avi_config):
    """
    This function checks if same vip is used for other vs
    :param avi_config: avi config dict
    :return: None
    """

    vs_list = [v for v in avi_config['VirtualService'] if 'port_range_end' in
               v['services'][0]]
    for vs in vs_list:
        vs_port_list = [int(v['services'][0]['port']) for v in
                        avi_config['VirtualService']
                        if v['ip_address']['addr'] == vs['ip_address']['addr']
                        and 'port_range_end' not in v['services'][0]]
        if vs_port_list:
            min_port = min(vs_port_list)
            max_port = max(vs_port_list)
            vs['services'][0]['port_range_end'] = str(min_port - 1)
            service = {
                'enable_ssl': False,
                'port': str(max_port + 1),
                'port_range_end': '65535'
            }
            vs['services'].append(service)


def add_clttimeout_for_http_profile(profile_name, avi_config, cltimeout):
    """
    :param object_type:Type of object need to check for name
    :param name: name of object
    :param avi_config: avi config dict
    :return: Bool Value
    """

    profile = [p for p in avi_config['ApplicationProfile']
               if p['name'] == profile_name]
    if profile:
        profile[0]['client_header_timeout'] = int(cltimeout)
        profile[0]['client_body_timeout'] = int(cltimeout)

def object_exist(object_type, name, avi_config):
    data = avi_config[object_type]
    obj_list = [obj for obj in data if obj['name'] == name]
    if obj_list:
        return True
    return False


def is_shared_same_vip(vs, avi_config):
    """
    This function check for vs sharing same vip
    :param vs: name of vs
    :param avi_config:  avi config dict
    :return: Bool value
    """

    shared_vip = [v for v in avi_config['VirtualService']
                  if v['ip_address']['addr'] == vs['ip_address']['addr']
                  and v['services'][0]['port'] == vs['services'][0]['port']]
    if shared_vip:
        return True

def clone_http_policy_set(policy, prefix, avi_config):
    """
    This function clone pool reused in context switching rule
    :param policy: name of policy
    :param prefix: clone for
    :param avi_config: avi config dict
    :return:None
    """

    policy_name = policy['name']
    for rule in policy['http_request_policy']['rules']:
        if rule.get('switching_action', None):
            pool_group_ref = clone_pool_group(rule['switching_action']
                                              ['pool_group_ref'], policy_name,
                                              avi_config)
            if pool_group_ref:
                rule['switching_action']['pool_group_ref'] = pool_group_ref
    policy['name'] += '-%s-clone' % prefix

def set_rules_index_for_http_policy_set(avi_config):
    """
    Update index as per avi protobuf requirements
    :param avi_config: avi config dict
    :return: None
    """

    http_policy_sets = avi_config['HTTPPolicySet']
    for http_policy_set in http_policy_sets:
        rules = http_policy_set['http_request_policy']['rules']
        rules = sorted(rules, key=lambda d: int(d['index']))
        for index, rule in enumerate(rules):
            rule['index'] = index

def get_netscalar_full_command(netscalar_command, obj):
    """
    Generate netscaler command from the parse dict
    :param netscalar_command: name of command
    :param obj: object with attributes
    :return: Full command
    """

    for attr in obj['attrs']:
        netscalar_command += ' %s' % attr
    for key in obj:
        if isinstance(obj[key], list):
            continue
        if key == 'line_no':
            continue
        netscalar_command += ' -%s %s' % (key, obj[key])
    return netscalar_command

def clone_pool_group(pg_name, prefix, avi_config):
    """
    Used for cloning shared pool group.
    :param pg_name: pool group name
    :param prefix: clone for
    :param avi_config: avi config dict
    :return: None
    """

    pool_groups = [pg for pg in avi_config['PoolGroup'] if pg['name'] == pg_name]
    if pool_groups:
        pool_group = copy.deepcopy(pool_groups[0])
        pool_group_name = re.sub('[:]', '-', prefix + pg_name)
        pool_group['name'] = pool_group_name
        for member in pool_group.get('members', []):
            pool_ref = clone_pool(member['pool_ref'], prefix, avi_config)
            if pool_ref:
                member['pool_ref'] = pool_ref
        avi_config['PoolGroup'].append(pool_group)
        LOG.info("Same pool group reference to other object. Clone Pool group "
                 "%s for %s" % (pg_name, prefix))
        return pool_group['name']
    return None


def remove_http_mon_from_pool(avi_config, pool):
    """
    This function is used for removing http type from health monitor for https
    vs.
    :param avi_config: avi config dict
    :param pool: name of pool
    :return: None
    """
    if pool:
        hm_refs = copy.deepcopy(pool['health_monitor_refs'])
        for hm_ref in hm_refs:
            hm = [h for h in avi_config['HealthMonitor'] if h['name'] == hm_ref]
            if hm and hm[0]['type'] == 'HEALTH_MONITOR_HTTP':
                pool['health_monitor_refs'].remove(hm_ref)
                LOG.warning('Skipping %s this reference from %s pool because of '
                            'health monitor type is '
                            'HTTPS and VS has no ssl profile.' % (hm_ref,
                                                                  pool['name']))

