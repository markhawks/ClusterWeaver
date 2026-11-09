"""Remote stdlib-only, staged pcs fencing creation. Secrets arrive on SSH stdin."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from xml.etree import ElementTree as ET


class UncertainResult(Exception):
    pass


def desired_attributes(profile, options):
    return dict(ipaddr=profile['controller_endpoint'], login=profile['username'], passwd=profile['password'], lanplus='1', power_wait=str(options['power_wait']), pcmk_host_list=profile['nodename'])


def _seconds(value):
    match = re.fullmatch(r'(\d+)(ms|s|min|m|h)?', str(value or ''))
    if not match:
        return None
    return int(match[1]) * {'ms':.001,'s':1,'min':60,'m':60,'h':3600,None:1}[match[2]]


def matching_resource(root, profile, options):
    resource_id = profile['resource_name']
    elements = [e for e in root.findall('./configuration/resources//*') if e.get('id') == resource_id]
    if not elements:
        # IDs are shared by all CIB elements, not only resources.
        if any(e.get('id') == resource_id for e in root.iter()):
            raise ValueError(f'ID {resource_id} is already used by another CIB element.')
        return False
    if len(elements) != 1 or elements[0].tag != 'primitive':
        raise ValueError(f'Resource {resource_id} is ambiguous or is not a primitive.')
    primitive = elements[0]
    if primitive.get('class') != 'stonith' or primitive.get('type') != 'fence_ipmilan':
        raise ValueError(f'Resource {resource_id} uses a different class or fencing agent.')
    attrs = {}
    aliases = {'ip':'ipaddr', 'username':'login', 'password':'passwd'}
    for group in primitive.findall('instance_attributes'):
        if group.find('rule') is not None:
            raise ValueError(f'Resource {resource_id} uses conditional attributes; review it manually.')
        for pair in group.findall('nvpair'):
            name = aliases.get(pair.get('name'), pair.get('name'))
            if name in attrs:
                raise ValueError(f'Resource {resource_id} has duplicate or aliased attributes.')
            attrs[name] = pair.get('value', '')
    if attrs.get('lanplus', '').lower() in {'true','yes','on'}:
        attrs['lanplus'] = '1'
    if 'pcmk_host_list' in attrs:
        attrs['pcmk_host_list'] = ' '.join(attrs['pcmk_host_list'].split())
    expected = desired_attributes(profile, options)
    conflicts = [name for name, value in expected.items() if attrs.get(name) != value]
    for name in ('pcmk_host_map', 'action'):
        if name in attrs:
            conflicts.append(name)
    if attrs.get('method', 'onoff') != 'onoff':
        conflicts.append('method')
    if attrs.get('pcmk_host_check', 'static-list') != 'static-list':
        conflicts.append('pcmk_host_check')
    if options.get('monitor'):
        monitor = options['monitor']
        operations = primitive.findall('./operations/op')
        if not any(op.get('name') == 'monitor' and _seconds(op.get('interval')) == monitor['interval'] and _seconds(op.get('timeout')) == monitor['timeout'] for op in operations):
            conflicts.append('monitor operation')
    if options.get('failure_timeout') is not None:
        meta = {p.get('name'):p.get('value') for p in primitive.findall('./meta_attributes/nvpair')}
        if any(group.find('rule') is not None for group in primitive.findall('meta_attributes')) or _seconds(meta.get('failure-timeout')) != options['failure_timeout']:
            conflicts.append('failure-timeout')
    for name, default in [('pcmk_reboot_action','reboot'),('pcmk_off_action','off'),('pcmk_on_action','on'),('pcmk_status_action','status'),('pcmk_monitor_action','monitor')]:
        if name in attrs and attrs[name] != default:
            conflicts.append(name)
    if conflicts:
        raise ValueError(f'Resource {resource_id} conflicts with the saved configuration: ' + ', '.join(conflicts) + '. No existing resource was changed.')
    return True


def create_devices(payload, run=None):
    deadline = time.monotonic() + min(180, payload.get('budget', 180))
    profiles, options = payload['profiles'], payload['options']
    pushed = False
    previous_umask = os.umask(0o077)
    if run is None:
        def run(args):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Fencing creation budget expired.')
            result = subprocess.run(args, capture_output=True, text=True, timeout=min(35, remaining), env=dict(os.environ, PATH='/usr/sbin:/usr/bin:/sbin:/bin', LC_ALL='C'))
            if result.returncode:
                # Do not return pcs/CIB output: it may contain other resources' secrets.
                raise ValueError('pcs/cluster command failed (exit '+str(result.returncode)+'). Review the cluster locally; no command output containing credentials was recorded.')
            return result.stdout
    def guard():
        status = run(['pcs', 'status', '--full'])
        match = re.search(r'^\s*Cluster name:\s*(.+)$', status, re.M)
        if match is None or match[1].strip() != payload['cluster_name']:
            raise ValueError('Live cluster name differs from the expected project.')
        root = ET.fromstring(run(['crm_mon', '--one-shot', '--as-xml']))
        dc = root.find('.//summary/current_dc')
        if dc is None or dc.get('present') != 'true' or dc.get('with_quorum') != 'true':
            raise ValueError('Cluster coordinator with quorum is required.')
        nodes = root.findall('.//nodes/node')
        if sorted(n.get('name') for n in nodes) != sorted(payload['nodes']):
            raise ValueError('Live cluster membership differs from the project.')
        if any(n.get('online') != 'true' or any(n.get(k) == 'true' for k in ('unclean','maintenance','shutdown')) for n in nodes) or root.findall('.//failures/*') or any(r.get('failed')=='true' for r in root.findall('.//resources//resource')):
            raise ValueError('All nodes must be online and clean, without maintenance or unresolved failures.')
    def load_cib(path):
        run(['pcs', 'cluster', 'cib', str(path)])
        root = ET.parse(path).getroot()
        if sorted(n.get('uname') for n in root.findall('./configuration/nodes/node')) != sorted(payload['nodes']):
            raise ValueError('CIB node membership differs from the project.')
        return root
    try:
        guard()
        with tempfile.TemporaryDirectory(prefix='clusterweaver-fencing-') as directory:
            original, staged = Path(directory)/'original.xml', Path(directory)/'staged.xml'
            original_root = load_cib(original)
            missing = [p for p in profiles if not matching_resource(original_root, p, options)]
            if missing:
                shutil.copyfile(original, staged)
                for index, profile in enumerate(missing):
                    attrs = desired_attributes(profile, options)
                    # Actual passwords are injected into protected XML only, never argv.
                    attrs['passwd'] = '__CW_PASSWORD_PLACEHOLDER_'+str(index)+'__'
                    args = ['pcs','-f',str(staged),'stonith','create',profile['resource_name'],'fence_ipmilan'] + [k+'='+v for k,v in attrs.items()]
                    if options.get('monitor'):
                        args += ['op','monitor','interval='+str(options['monitor']['interval'])+'s','timeout='+str(options['monitor']['timeout'])+'s']
                    if options.get('failure_timeout') is not None:
                        args += ['meta','failure-timeout='+str(options['failure_timeout'])+'s']
                    if options.get('disabled'):
                        args += ['--disabled']
                    run(args)
                tree = ET.parse(staged)
                for profile in missing:
                    primitive = next(p for p in tree.getroot().findall('./configuration/resources//primitive') if p.get('id') == profile['resource_name'])
                    pairs = [p for p in primitive.findall('./instance_attributes/nvpair') if p.get('name') in {'passwd','password'}]
                    if len(pairs) != 1:
                        raise ValueError('Cannot safely identify the staged password attribute.')
                    pairs[0].set('value', profile['password'])
                tree.write(staged, encoding='utf-8', xml_declaration=True)
                for profile in profiles:
                    if not matching_resource(tree.getroot(), profile, options):
                        raise ValueError('Staged fencing definition is incomplete.')
                guard()
                current = load_cib(Path(directory)/'current.xml')
                if ET.tostring(current.find('configuration')) != ET.tostring(original_root.find('configuration')):
                    raise ValueError('Cluster configuration changed during preparation. Reload and retry; no changes were pushed.')
                pushed = True
                run(['pcs','cluster','cib-push',str(staged),'diff-against='+str(original)])
            final = load_cib(Path(directory)/'verified.xml')
            reports = []
            for profile in profiles:
                if not matching_resource(final, profile, options):
                    raise UncertainResult('Resource is not visible after the CIB update. Refresh cluster state before retrying.')
                primitive = next(p for p in final.findall('./configuration/resources//primitive') if p.get('id') == profile['resource_name'])
                reports.append(dict(resource=profile['resource_name'], nodename=profile['nodename'], outcome='created' if profile in missing else 'already configured', operations=[{key: op.get(key) for key in ('name','interval','timeout')} for op in primitive.findall('./operations/op')]))
            return dict(status='pass', resources=reports, message='Fencing definitions verified. No power action was requested. Creating enabled devices makes them available to Pacemaker.')
    except Exception as exc:
        if pushed:
            raise UncertainResult('CIB update outcome requires review. No automatic retry was made.') from None
        raise
    finally:
        os.umask(previous_umask)


def verify_devices(payload, run=None):
    """Read CIB/runtime state only; never stage, push, enable, cleanup or fence."""
    deadline = time.monotonic() + min(60, payload.get('budget',60))
    if run is None:
        def run(args):
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Fencing verification budget expired.')
            result = subprocess.run(args,capture_output=True,text=True,timeout=min(20,remaining),env=dict(os.environ,PATH='/usr/sbin:/usr/bin:/sbin:/bin',LC_ALL='C'))
            if result.returncode:
                raise ValueError('Cannot read the current fencing configuration or cluster status. No cluster changes were requested.')
            return result.stdout
    cib = ET.fromstring(run(['pcs','cluster','cib']))
    runtime = ET.fromstring(run(['crm_mon','--one-shot','--as-xml']))
    status = run(['pcs','status','--full'])
    match = re.search(r'^\s*Cluster name:\s*(.+)$',status,re.M)
    if match is None or match[1].strip() != payload['cluster_name']:
        raise ValueError('Live cluster name differs from the expected project.')
    if sorted(n.get('uname') for n in cib.findall('./configuration/nodes/node')) != sorted(payload['nodes']):
        raise ValueError('CIB membership differs from the expected project.')
    properties = {p.get('name'):p.get('value') for p in cib.findall('./configuration/crm_config/cluster_property_set/nvpair')}
    defaults = {p.get('name'):p.get('value') for p in cib.findall('./configuration/rsc_defaults/meta_attributes/nvpair')}
    false = {'false','0','no','off'}
    true = {'true','1','yes','on'}
    cluster_errors = []
    dc = runtime.find('.//summary/current_dc')
    if dc is None or dc.get('present') != 'true' or dc.get('with_quorum') != 'true':
        cluster_errors.append('No cluster coordinator with quorum.')
    nodes = runtime.findall('.//nodes/node')
    if sorted(n.get('name') for n in nodes) != sorted(payload['nodes']) or any(n.get('online')!='true' or n.get('unclean')=='true' or n.get('maintenance')=='true' or n.get('shutdown')=='true' for n in nodes):
        cluster_errors.append('All expected nodes must be online, clean and outside maintenance mode.')
    if properties.get('stonith-enabled','true').lower() in false:
        cluster_errors.append('Cluster property stonith-enabled is false.')
    if properties.get('maintenance-mode','false').lower() in true:
        cluster_errors.append('Cluster maintenance mode is enabled.')
    if cib.findall('./configuration/crm_config/cluster_property_set/rule') or cib.findall('./configuration/rsc_defaults/meta_attributes/rule'):
        cluster_errors.append('Conditional cluster or resource-default policies require manual review.')
    if runtime.findall('.//failures/*'):
        cluster_errors.append('The cluster reports unresolved failed actions; review status before power testing.')
    reports = []
    for profile in payload['profiles']:
        resource_id = profile['resource_name']
        errors, warnings = list(cluster_errors), []
        primitive = next((p for p in cib.findall('./configuration/resources//primitive') if p.get('id')==resource_id),None)
        operations, counts, meta = [], [], {}
        power_wait = None
        if primitive is None:
            errors.append('Expected fencing resource is missing.')
        else:
            attrs = {p.get('name'):p.get('value') for p in primitive.findall('./instance_attributes/nvpair')}
            try:
                power_wait = int(attrs.get('power_wait','2'))
                if power_wait < 0:
                    raise ValueError()
            except ValueError:
                errors.append('power_wait is not a valid non-negative integer.')
            if power_wait is not None:
                try:
                    if not matching_resource(cib,profile,dict(power_wait=power_wait,monitor=None,failure_timeout=None)):
                        errors.append('Expected fencing resource is missing.')
                except ValueError as exc:
                    errors.append(str(exc))
            if primitive.findall('./meta_attributes/rule'):
                errors.append('Conditional resource policies require manual review.')
            meta = dict(defaults)
            meta.update({p.get('name'):p.get('value') for p in primitive.findall('./meta_attributes/nvpair')})
            if meta.get('target-role','Started').lower()=='stopped':
                errors.append('Fencing resource is disabled. Enable it before power testing.')
            if meta.get('is-managed','true').lower() in false or meta.get('maintenance','false').lower() in true:
                errors.append('Fencing resource is unmanaged or in maintenance mode.')
            operations = [{key:op.get(key) for key in ('name','interval','timeout','on-fail','enabled')} for op in primitive.findall('./operations/op')]
            if not any(op['name']=='monitor' and (_seconds(op['interval']) or 0)>0 and str(op['enabled']).lower() not in false for op in operations):
                warnings.append('No enabled recurring monitor operation is configured.')
            live = [r for r in runtime.findall('.//resources//resource') if r.get('id')==resource_id]
            if not live or not any(r.get('active')=='true' and r.get('role')=='Started' for r in live):
                errors.append('Fencing resource is not active in Pacemaker.')
            if any(r.get('failed')=='true' or r.get('blocked')=='true' or r.get('managed')=='false' for r in live):
                errors.append('Pacemaker reports this fencing resource failed, blocked or unmanaged.')
            for state in cib.findall('./status/node_state'):
                for pair in state.findall('.//transient_attributes//nvpair'):
                    name = pair.get('name','')
                    if name == 'fail-count-'+resource_id or name.startswith('fail-count-'+resource_id+'#'):
                        value = pair.get('value','0')
                        counts.append(dict(node=state.get('uname',state.get('id')),operation=name,value=value))
                        if value != '0':
                            errors.append('Non-zero failure count on '+str(state.get('uname',state.get('id')))+'. Review the cause; no cleanup was performed.')
        reports.append(dict(resource=resource_id,nodename=profile['nodename'],status='fail' if errors else 'pass',outcome='configuration checked',enabled=primitive is not None and meta.get('target-role','Started').lower()!='stopped',power_wait=power_wait,failure_timeout=meta.get('failure-timeout','0'),operations=operations,failcounts=counts,errors=errors,warnings=warnings))
    ok = all(r['status']=='pass' for r in reports)
    return dict(status='pass' if ok else 'fail',resources=reports,message='Read-only fencing configuration verification completed. No power action, configuration change or failure cleanup was requested.')


if __name__ == '__main__':
    import sys
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(verify_devices(payload) if payload.get('verify_only') else create_devices(payload)))
    except UncertainResult as exc:
        print(json.dumps(dict(status='unknown', message=str(exc))))
        raise SystemExit(2)
    except Exception as exc:
        print(json.dumps(dict(status='fail', message=str(exc))))
        raise SystemExit(1)
