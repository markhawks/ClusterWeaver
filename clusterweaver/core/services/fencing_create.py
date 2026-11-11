"""Step 08b gating, safe previews and a reserved background creation job."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import re
import shlex
import time

from sqlalchemy.orm import Session
from clusterweaver.core.services.cluster_operations import snapshot_node, expected_nodes
from clusterweaver.core.services.fence_agents import check_cluster_agents
from clusterweaver.core.services.stonith import verify_ipmi_profiles_on_nodes
from clusterweaver.core.services.ssh_bootstrap import _connect, _collect_channel
from clusterweaver.persistence.models import ClusterOperationRecord, ProjectRecord, StepExecutionRecord, utcnow
from clusterweaver.persistence.repositories.projects import to_domain
from clusterweaver.core.services.dell_ipmi import validate_ipmi_definition


ACTION = 'fencing_create'
VERIFY_ACTION = 'fencing_verify'


def default_resource_name(hostname):
    suffix = re.search(r'(\d+)$', hostname)
    return 'STONITH-' + (suffix[1][-2:].zfill(2) if suffix else hostname)


def creation_profiles(project):
    if not project.stonith or project.stonith['mode'] != 'ipmi':
        raise ValueError('Step 08b currently supports direct iDRAC/IPMI only; OEM and VMware device creation are not implemented yet.')
    nodes = {node.hostname:node for node in project.nodes}
    expected_nodes(project)
    if any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,252}', n.nodename) for n in project.nodes):
        raise ValueError('Pacemaker nodenames must be valid single host names.')
    profiles = project.stonith['profiles']
    if not nodes or len(profiles) != len(nodes) or {p['hostname'] for p in profiles} != set(nodes):
        raise ValueError('Save one iDRAC definition for every current cluster node.')
    names, controllers, result = set(), set(), []
    for profile in profiles:
        validate_ipmi_definition(profile['controller_endpoint'], profile['resource_name'])
        if profile['resource_name'].casefold() in names or profile['controller_endpoint'].casefold() in controllers:
            raise ValueError('Resource names and controller endpoints must be unique.')
        if not profile['username'] or any(c in profile['username'] for c in '\r\n\x00'):
            raise ValueError('Each controller needs a valid userid.')
        names.add(profile['resource_name'].casefold())
        controllers.add(profile['controller_endpoint'].casefold())
        result.append(dict(profile, node_id=nodes[profile['hostname']].id, nodename=nodes[profile['hostname']].nodename))
    return result


def readiness(project, results, key_available):
    reasons = []
    try:
        creation_profiles(project)
    except ValueError as exc:
        reasons.append(str(exc))
    if len(project.nodes) < 2:
        reasons.append('At least two cluster nodes are required for peer fencing verification.')
    ids = {n.id for n in project.nodes}
    for step, label in [('00k','SSH key verification'),('08a','iDRAC status verification'),('08a-fa','cluster-node fence-agent verification')]:
        passed = {r.node_id for r in results.get(step, []) if r.status == 'pass'}
        if not ids or passed != ids:
            reasons.append(label + ' must pass on every current node.')
    if not key_available or any(not n.bootstrap_ip for n in project.nodes):
        reasons.append('An active project SSH key and SSH IP for every node are required.')
    return reasons


def preview_command(profile, options):
    from clusterweaver.core.services.fencing_device import desired_attributes
    attrs = desired_attributes(dict(profile, password='YOUR_IDRAC_PASSWORD'), options)
    args = ['pcs','stonith','create',profile['resource_name'],'fence_ipmilan'] + [k+'='+v for k,v in attrs.items()]
    if options.get('monitor'):
        args += ['op','monitor','interval='+str(options['monitor']['interval'])+'s','timeout='+str(options['monitor']['timeout'])+'s']
    if options.get('failure_timeout') is not None:
        args += ['meta','failure-timeout='+str(options['failure_timeout'])+'s']
    if options.get('disabled'):
        args += ['--disabled']
    return shlex.join(args)


def run_creation(engine, job_id, project, credentials, profiles, options, verify_only=False):
    deadline = time.monotonic() + 360
    results = [dict(node_id=p['node_id'],hostname=p['hostname'],nodename=p['nodename'],resource=p['resource_name'],ip=next(n.bootstrap_ip for n in project.nodes if n.id==p['node_id']),phase='waiting',state='pending',snapshot=None,command='Read-only CIB, monitor and failure-count inspection' if verify_only else preview_command(p,options),output='') for p in profiles]
    attempted = False
    secrets = [p['password'] for p in profiles if p.get('password')]
    def clean(message):
        for secret in secrets:
            message = message.replace(secret,'[redacted]')
        return message[-16000:]
    def save(phase, status='running', finished=False):
        with Session(engine) as session:
            job = session.get(ClusterOperationRecord, job_id)
            current = session.get(ProjectRecord, project.id)
            if job is None or job.active_project_id != project.id or current is None:
                raise ValueError('The reserved fencing job is no longer active.')
            dto = to_domain(current)
            if dto.uuid != project.uuid or dto.stonith != project.stonith or dto.cluster_name != project.cluster_name or sorted((n.id,n.hostname,n.nodename,n.bootstrap_ip,n.ssh_port) for n in dto.nodes) != sorted((n.id,n.hostname,n.nodename,n.bootstrap_ip,n.ssh_port) for n in project.nodes):
                raise ValueError('Project identity or fencing definitions changed. Refresh before another action.')
            job.phase, job.status, job.results = phase, status, results
            if finished:
                job.active_project_id, job.finished_at = None, utcnow()
                existing = {r.node_id:r for r in session.query(StepExecutionRecord).filter_by(project_id=project.id,step='08c' if verify_only else '08b')}
                for result in results:
                    record = existing.get(result['node_id'])
                    if record is None:
                        record = StepExecutionRecord(project_id=project.id,node_id=result['node_id'],step='08c' if verify_only else '08b')
                        session.add(record)
                    record.status, record.output, record.executed_at = (result['state'] if verify_only else status), clean(result['output']), utcnow()
            session.commit()
    try:
        save('Verifying every node and cluster identity')
        snapshots = {}
        with ThreadPoolExecutor(max_workers=min(8,len(project.nodes))) as pool:
            futures = {pool.submit(snapshot_node,n,credentials,project,deadline):n for n in project.nodes}
            for future in as_completed(futures):
                node = futures[future]
                snap = future.result()
                if not verify_only and (snap['quorum'] is not True or snap['failures'] or any(r.get('failed')=='true' for r in snap['resources']) or not snap['nodes'] or any(not n['online'] or n['unclean'] or n['maintenance'] or n['shutdown'] for n in snap['nodes'].values())):
                    raise ValueError('All nodes must be online and clean, with quorum and no unresolved failures.')
                snapshots[node.id] = snap
        checks = check_cluster_agents(project.nodes,credentials,'ipmi')
        if len(checks) != len(project.nodes) or not all(r.ok for r in checks):
            raise ValueError('Live fence_ipmilan agent verification failed; repeat 08a agent checks.')
        save('Checking controller access from surviving peer nodes')
        peer_access = {p['node_id']:[] for p in profiles}
        candidates = [(p,n) for p in profiles for n in project.nodes if n.id != p['node_id']]
        if not candidates:
            raise ValueError('At least two nodes are required to verify peer fencing access.')
        peer_deadline = min(deadline-40,time.monotonic()+120)
        def check_peer(profile,node):
            remaining = peer_deadline-time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Peer controller verification budget expired before creation.')
            return verify_ipmi_profiles_on_nodes([node],credentials,[dict(profile,hostname=node.hostname)],remaining)
        with ThreadPoolExecutor(max_workers=min(8,len(candidates))) as pool:
            futures = {pool.submit(check_peer,p,node):(p,node) for p,node in candidates}
            for future in as_completed(futures):
                profile,node = futures[future]
                checked = future.result()
                if checked and all(r.ok for r in checked):
                    peer_access[profile['node_id']].append(node.hostname)
        unreachable = [p['resource_name'] for p in profiles if not peer_access[p['node_id']]]
        if unreachable and not verify_only:
            raise ValueError('Read-only status must succeed from at least one other cluster node for: '+', '.join(unreachable)+'. No resources were created.')
        for result in results:
            result['phase'] = 'preflight passed'
            result['output'] = ('Peer controller access verified from: '+', '.join(peer_access[result['node_id']])) if peer_access[result['node_id']] else 'FAIL: no surviving peer can read this controller status.'
        save('Reading fencing configuration on one cluster coordinator' if verify_only else 'Staging fencing devices on one cluster coordinator')
        node = project.nodes[0]
        client, _ = _connect(node,credentials)
        try:
            remaining = min(190,deadline-time.monotonic())
            if remaining < (10 if verify_only else 40):
                raise TimeoutError('Insufficient budget remains for fencing verification.' if verify_only else 'Insufficient budget remains to safely create fencing devices.')
            payload = dict(cluster_name=project.cluster_name or project.name,nodes=expected_nodes(project),profiles=profiles,options=options,budget=min(180,remaining-5),verify_only=verify_only)
            source = Path(__file__).with_name('fencing_device.py').read_text()
            stdin, stdout, _stderr = client.exec_command('python3 -c '+shlex.quote(source),timeout=remaining)
            attempted = True
            stdin.write(json.dumps(payload))
            stdin.channel.shutdown_write()
            code,output = _collect_channel(stdout.channel,timeout=remaining)
        finally:
            client.close()
        try:
            report = json.loads(output.strip())
        except (ValueError,TypeError):
            raise ValueError('Remote result is incomplete. Refresh cluster state before retrying.') from None
        status = report.get('status')
        if verify_only and unreachable:
            status = 'fail'
        if status not in {'pass','fail','unknown'}:
            raise ValueError('Remote creation returned an unrecognized state.')
        for result in results:
            item = next((r for r in report.get('resources',[]) if r['resource']==result['resource']),None)
            if status == 'pass' and (code != 0 or item is None):
                raise ValueError('Remote verification did not confirm every requested resource.')
            item_status = item.get('status',status) if verify_only and item else status
            if verify_only and not peer_access[result['node_id']]:
                item_status = 'fail'
            result['state'], result['phase'] = item_status, 'completed' if item_status=='pass' else 'review required'
            result['output'] = clean(result['output']+'\n'+report.get('message','')+ ('\n'+json.dumps(item) if item else ''))
        save(('Fencing configuration verified' if verify_only else 'Fencing definitions verified') if status=='pass' else 'Review fencing configuration',status,True)
    except Exception as exc:
        status = 'unknown' if attempted and not verify_only else 'fail'
        for result in results:
            result['state'], result['phase'], result['output'] = status,'review required',clean(str(exc))
        try:
            save('Fencing verification requires review' if verify_only else 'Fencing creation requires review',status,True)
        except Exception:
            with Session(engine) as session:
                job = session.get(ClusterOperationRecord,job_id)
                if job is not None:
                    job.status,job.phase,job.results,job.active_project_id,job.finished_at = 'unknown','Project changed or worker interrupted',results,None,utcnow()
                    session.commit()
