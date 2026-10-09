"""Bounded read-only snapshots and guarded local pcs actions via project SSH keys."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timezone
import re
import shlex
import time
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session
from clusterweaver.persistence.models import ClusterOperationRecord, ProjectRecord, utcnow
from clusterweaver.core.services.ssh_bootstrap import _connect, _collect_channel

ACTIONS = {
    'status': ('Aggiorna stato', 'Read-only: updates cluster and node status.'),
    'start': ('Avvia cluster', 'Starts cluster services on all configured nodes; application resources may start.'),
    'stop': ('Arresta cluster', 'Stops cluster services on all configured nodes, including application resources.'),
    'enable': ('Abilita al boot', 'Enables cluster services at boot on every node; does not start them.'),
    'disable': ('Disabilita al boot', 'Disables cluster services at boot on every node; does not stop them.'),
    'standby': ('Standby nodo', 'Prevents the selected node from hosting resources; resources may move to another node.'),
    'unstandby': ('Unstandby nodo', 'Allows the selected node to host resources; resources may remain on other nodes.'),
}
JOB_BUDGET = 360
STALE_AFTER = 600

SNAPSHOT_SCRIPT = r'''#!/usr/bin/env bash
export PATH=/usr/sbin:/usr/bin:/sbin:/bin LC_ALL=C
command -v pcs >/dev/null || { echo 'pcs is missing'; exit 1; }
[ "$(id -u)" = 0 ] || { echo 'Root access is required'; exit 1; }
command -v timeout >/dev/null || { echo 'timeout is missing'; exit 1; }
printf '\n__CW_CONFIG__\n'
cat /etc/corosync/corosync.conf || exit 1
printf '\n__CW_SERVICES__\n'
for unit in pacemaker corosync; do
    printf '%s ' "$unit"; systemctl is-active "$unit" 2>/dev/null || true
done
printf '\n__CW_BOOT__\n'
for unit in pacemaker corosync; do
    printf '%s ' "$unit"; systemctl is-enabled "$unit" 2>/dev/null || true
done
printf '\n__CW_XML__\n'
timeout -k 2s 10s crm_mon --one-shot --as-xml 2>/dev/null || true
printf '\n__CW_STATUS__\n'
timeout -k 2s 10s pcs status --full 2>&1 || true
printf '\n__CW_END__\n'
'''


def expected_nodes(project):
    names = [node.nodename for node in project.nodes]
    if not names or any(not name for name in names) or len(set(names)) != len(names):
        raise ValueError('Every node needs a unique Pacemaker nodename before cluster operations.')
    return sorted(names)


def command_for(action, target=''):
    if action not in ACTIONS:
        raise ValueError('Unsupported cluster operation.')
    if action == 'status':
        return SNAPSHOT_SCRIPT
    if action in {'standby', 'unstandby'}:
        if not target:
            raise ValueError('Select a configured node.')
        return 'pcs node ' + action + ' ' + shlex.quote(target)
    return 'pcs cluster ' + action


def generate_operation_script(project, action, target=''):
    command = command_for(action, target)
    if action == 'status':
        return command
    names = expected_nodes(project)
    if action in {'standby', 'unstandby'} and target not in names:
        raise ValueError('The target is not a configured Pacemaker node.')
    cluster = project.cluster_name or project.name
    return ("#!/usr/bin/env bash\nset -euo pipefail\nexport PATH=/usr/sbin:/usr/bin:/sbin:/bin LC_ALL=C\n"
        "# Execute start/stop/boot actions locally on each project node via SSH.\n"
        "# Standby/unstandby is issued once from a healthy cluster coordinator.\n"
        "# ClusterWeaver performs live SSH, identity and status checks before this payload.\n"
        f"expected_cluster={shlex.quote(cluster)}\n"
        f"expected_nodes={shlex.quote(chr(10).join(names))}\n"
        "actual_cluster=$(awk '$1==\"cluster_name:\" {gsub(/\"/,\"\",$2); print $2}' /etc/corosync/corosync.conf)\n"
        "actual_nodes=$(awk '$1==\"name:\" {gsub(/\"/,\"\",$2); print $2}' /etc/corosync/corosync.conf | sort)\n"
        "[ \"$actual_cluster\" = \"$expected_cluster\" ] || { echo 'FAIL: cluster name differs from project'; exit 1; }\n"
        "[ \"$actual_nodes\" = \"$expected_nodes\" ] || { echo 'FAIL: cluster node names differ from project'; exit 1; }\n"
        "command -v timeout >/dev/null\n"
        "timeout --signal=TERM --kill-after=5s 120s " + command + "\n")


def _section(output, name):
    match = re.search(r'__CW_' + name + r'__\n(.*?)(?=\n__CW_[A-Z]+__)', output, re.S)
    return match.group(1).strip() if match else ''


def parse_snapshot(output, project):
    configuration = re.sub(r'#[^\n]*', '', _section(output, 'CONFIG'))
    values = re.findall(r'\bcluster_name\s*:\s*("[^"\n]*"|[^\s{}]+)', configuration)
    cluster = values[0].strip('"') if len(values) == 1 else ''
    blocks = re.findall(r'\bnode\s*\{([^{}]*)\}', configuration, re.S)
    names = []
    for block in blocks:
        matches = re.findall(r'\bname\s*:\s*("[^"\n]*"|[^\s{}]+)', block)
        if len(matches) != 1:
            raise ValueError('Corosync node identity is not explicit or is ambiguous; review corosync.conf.')
        names.append(matches[0].strip('"'))
    if cluster != (project.cluster_name or project.name):
        case = ' (uppercase/lowercase mismatch)' if cluster.casefold() == (project.cluster_name or project.name).casefold() else ''
        raise ValueError(f'Cluster name mismatch{case}: detected {cluster!r}, expected {(project.cluster_name or project.name)!r}.')
    if sorted(names) != expected_nodes(project):
        raise ValueError(f'Corosync node membership differs from project: detected {sorted(names)!r}, expected {expected_nodes(project)!r}. Names are case sensitive.')
    def states(name):
        return dict(line.split(maxsplit=1) for line in _section(output, name).splitlines() if len(line.split(maxsplit=1)) == 2)
    services, boot = states('SERVICES'), states('BOOT')
    if set(services) != {'pacemaker', 'corosync'} or set(boot) != {'pacemaker', 'corosync'}:
        raise ValueError('Incomplete service/boot state returned by the node.')
    snapshot = dict(cluster_name=cluster, services=services, boot=boot, quorum=None, nodes={}, resources=[], failures=[], details=_section(output, 'STATUS'))
    xml = _section(output, 'XML')
    if xml:
        try:
            root = ET.fromstring(xml)
            dc = root.find('.//summary/current_dc')
            if dc is not None and dc.get('present', 'true') == 'true':
                snapshot['quorum'] = dc.get('with_quorum') == 'true'
            for node in root.findall('.//nodes/node'):
                if node.get('type') == 'remote':
                    continue
                if any(node.get(key) not in {'true', 'false'} for key in ('online', 'standby')):
                    raise ValueError('Live node online/standby attributes are incomplete.')
                snapshot['nodes'][node.get('name', '')] = {key: node.get(key) == 'true' for key in ('online', 'standby', 'maintenance', 'unclean', 'shutdown')}
                running = node.get('resources_running')
                snapshot['nodes'][node.get('name', '')]['resources_running'] = int(running) if running and running.isdigit() else None
            for resource in root.findall('.//resources//resource'):
                snapshot['resources'].append(dict(id=resource.get('id', ''), role=resource.get('role', ''), active=resource.get('active'), failed=resource.get('failed'), managed=resource.get('managed'), nodes=[n.get('name') for n in resource.findall('node')]))
            for failure in root.findall('.//failures/*'):
                snapshot['failures'].append(dict(failure.attrib))
        except ET.ParseError as exc:
            raise ValueError('Malformed or truncated crm_mon XML; live cluster state cannot be verified.') from exc
    if services.get('pacemaker') == 'active':
        if sorted(snapshot['nodes']) != expected_nodes(project):
            raise ValueError('Live Pacemaker node membership is incomplete or differs from the project.')
        live_name = re.search(r'^\s*Cluster name:\s*(.+)$', snapshot['details'], re.M)
        if live_name is None or live_name.group(1).strip() != cluster:
            raise ValueError('Live Pacemaker cluster name could not be verified against Corosync/project identity.')
    return snapshot


def remote_script(node, credentials, script, timeout, deadline):
    if time.monotonic() >= deadline:
        raise TimeoutError('The cluster operation deadline expired.')
    client, fingerprint = _connect(node, credentials)
    try:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('The cluster operation deadline expired.')
        limit = min(timeout, remaining)
        if script != SNAPSHOT_SCRIPT:
            if remaining <= 6:
                raise TimeoutError('Insufficient time remains to issue a modifying command safely.')
            script = script.replace('120s pcs ', str(min(120, int(remaining) - 5)) + 's pcs ')
        stdin, stdout, _stderr = client.exec_command('bash -s --', timeout=limit)
        stdin.write(script)
        stdin.channel.shutdown_write()
        code, output = _collect_channel(stdout.channel, timeout=limit)
        return code, output, fingerprint
    finally:
        client.close()


def snapshot_node(node, credentials, project, deadline):
    code, output, fingerprint = remote_script(node, credentials, SNAPSHOT_SCRIPT, 35, deadline)
    if code:
        raise ValueError('Cluster snapshot failed: ' + output[-4000:])
    snapshot = parse_snapshot(output, project)
    snapshot['fingerprint'] = fingerprint
    return snapshot


def standby_guard(snapshot, target):
    if snapshot['quorum'] is not True:
        raise ValueError('Standby blocked: the coordinator does not report quorum.')
    nodes = snapshot['nodes']
    if target not in nodes or not nodes[target]['online']:
        raise ValueError('Standby blocked: selected node is not online in Pacemaker.')
    if nodes[target]['standby']:
        return
    if snapshot['failures'] or any(resource['failed'] == 'true' for resource in snapshot['resources']) or any(n['unclean'] for n in nodes.values()):
        raise ValueError('Standby blocked: unresolved cluster failures or unclean nodes require review.')
    available = [name for name, node in nodes.items() if node['online'] and not any(node[key] for key in ('standby', 'maintenance', 'unclean', 'shutdown'))]
    if target not in available or len(available) <= 1:
        raise ValueError('Standby blocked: this is the last node available to host resources.')


def desired_state(snapshot, action, target=''):
    if action == 'start':
        return all(value == 'active' for value in snapshot['services'].values()) and snapshot['quorum'] is True and bool(snapshot['nodes']) and all(n['online'] for n in snapshot['nodes'].values())
    if action == 'stop':
        return all(value in {'inactive', 'failed'} for value in snapshot['services'].values())
    if action in {'enable', 'disable'}:
        return all(value == ('enabled' if action == 'enable' else 'disabled') for value in snapshot['boot'].values())
    if action in {'standby', 'unstandby'}:
        node = snapshot['nodes'].get(target)
        if node is None or node['standby'] != (action == 'standby'):
            return False
        if action == 'standby':
            if node.get('resources_running') is not None:
                return node['resources_running'] == 0
            return not any(target in resource['nodes'] for resource in snapshot['resources'])
        return True
    return True


def serialize_job(job):
    created = job.created_at.replace(tzinfo=timezone.utc) if job.created_at.tzinfo is None else job.created_at
    return dict(id=job.id, action=job.action, target_node=job.target_node, username=job.username, status=job.status, phase=job.phase,
        created_at=created.isoformat(), finished_at=(job.finished_at.replace(tzinfo=timezone.utc) if job.finished_at.tzinfo is None else job.finished_at).isoformat() if job.finished_at else None,
        budget=JOB_BUDGET, results=job.results)


class JobStopped(Exception):
    pass


def run_operation(engine, job_id, project, credentials, action, target='', poll_seconds=3):
    """Run outside the HTTP request, using private sessions and bounded SSH calls."""
    deadline = time.monotonic() + JOB_BUDGET
    results = [dict(node_id=n.id, hostname=n.hostname, nodename=n.nodename, ip=n.bootstrap_ip, phase='waiting', command=None, command_exit=None, state='pending', output='', snapshot=None) for n in project.nodes]
    def save(phase, status='running', finished=False):
        with Session(engine) as session:
            job = session.get(ClusterOperationRecord, job_id)
            current = session.get(ProjectRecord, project.id)
            if job is None or current is None or job.active_project_id != project.id:
                raise JobStopped()
            if (current.cluster_name or current.name) != (project.cluster_name or project.name) or sorted((n.id, n.nodename, n.bootstrap_ip, n.ssh_port) for n in current.nodes) != sorted((n.id, n.nodename, n.bootstrap_ip, n.ssh_port) for n in project.nodes):
                raise ValueError('Project identity or node inventory changed during the operation; refresh status before proceeding.')
            job.results = [dict(result) for result in results]
            job.phase, job.status = phase[:80], status
            if finished:
                job.finished_at, job.active_project_id = utcnow(), None
            session.commit()
    def collect(indices, phase):
        for i in indices:
            results[i]['phase'] = phase
        save(phase)
        with ThreadPoolExecutor(max_workers=min(8, len(indices))) as executor:
            futures = {executor.submit(snapshot_node, project.nodes[i], credentials, project, deadline): i for i in indices}
            for future in as_completed(futures):
                i = futures[future]
                try:
                    results[i]['snapshot'] = future.result()
                    results[i]['phase'] = 'checked'
                except Exception as exc:
                    results[i]['snapshot'] = None
                    results[i]['state'], results[i]['phase'] = 'fail', 'unreachable / invalid identity'
                    results[i]['output'] = str(exc)[:8000]
                save(phase)
    try:
        indices = list(range(len(project.nodes)))
        collect(indices, 'Checking SSH keys and cluster identity')
        if any(result['snapshot'] is None for result in results):
            save('Preflight failed; no mutating command was sent', 'fail', True)
            return
        if action == 'status':
            for result in results:
                result['state'], result['phase'] = 'pass', 'status collected'
            save('Status updated', 'pass', True)
            return
        targets = indices
        if action in {'standby', 'unstandby'}:
            candidates = [i for i in indices if results[i]['snapshot']['services']['pacemaker'] == 'active' and results[i]['snapshot']['quorum'] is True]
            if not candidates:
                raise ValueError('No online coordinator with quorum is available for the node operation.')
            coordinator = candidates[0]
            # Read a fresh view immediately before deciding placement changes.
            fresh = snapshot_node(project.nodes[coordinator], credentials, project, deadline)
            results[coordinator]['snapshot'] = fresh
            if action == 'standby':
                standby_guard(fresh, target)
            if target not in fresh['nodes']:
                raise ValueError('The selected nodename is absent from the live cluster.')
            targets = [coordinator]
        script = generate_operation_script(project, action, target)
        pending = []
        for i in targets:
            result = results[i]
            if desired_state(result['snapshot'], action, target):
                result['command_exit'], result['phase'] = 0, 'already in requested state'
            else:
                result['command'] = command_for(action, target)
                result['phase'] = 'executing'
                pending.append(i)
        save('Executing ' + action)
        if pending:
            with ThreadPoolExecutor(max_workers=min(8, len(pending))) as executor:
                futures = {executor.submit(remote_script, project.nodes[i], credentials, script, 130, deadline): i for i in pending}
                for future in as_completed(futures):
                    i = futures[future]
                    try:
                        code, output, _fingerprint = future.result()
                        results[i]['command_exit'] = code
                        results[i]['output'] = output[-8000:]
                        results[i]['state'] = 'unknown' if code in {124, 137} else ('pending' if code == 0 else 'fail')
                    except Exception as exc:
                        # The SSH stream may break after the remote command has started.
                        results[i]['state'], results[i]['output'] = 'unknown', str(exc)[:8000]
                    results[i]['phase'] = 'verifying'
                    save('Verifying state after ' + action)
        verification_deadline = min(deadline, time.monotonic() + (180 if action in {'start', 'stop'} else 60))
        while True:
            collect(indices, 'Reading current state after ' + action)
            checked = targets if action in {'standby', 'unstandby'} else indices
            achieved = all(results[i]['snapshot'] is not None and desired_state(results[i]['snapshot'], action, target) for i in checked)
            if achieved or time.monotonic() >= verification_deadline or any(results[i]['state'] in {'fail', 'unknown'} for i in targets):
                break
            time.sleep(min(poll_seconds, max(0, verification_deadline - time.monotonic())))
        for i, result in enumerate(results):
            if result['snapshot'] is None:
                result['state'] = 'unknown'
            elif i in targets and result['state'] in {'fail', 'unknown'}:
                pass
            elif action in {'standby', 'unstandby'}:
                result['state'] = 'pass' if achieved else 'unknown'
            elif desired_state(result['snapshot'], action, target):
                result['state'] = 'pass'
            else:
                result['state'] = 'unknown'
                result['output'] += '\nRequested state not reached within the verification limit; refresh status before another command.'
            result['phase'] = 'completed' if result['state'] == 'pass' else 'review required'
        states = {result['state'] for result in results}
        status = 'unknown' if 'unknown' in states else ('fail' if 'fail' in states else 'pass')
        save('Operation finished; ' + ('state verified' if status == 'pass' else 'review current state'), status, True)
    except JobStopped:
        return
    except Exception as exc:
        for result in results:
            if result['state'] == 'pending':
                result['state'], result['output'] = 'fail', str(exc)[:8000]
        try:
            save(str(exc)[:500], 'fail', True)
        except (JobStopped, ValueError):
            # Inventory edits or deletion invalidate the immutable job plan.
            with Session(engine) as session:
                job = session.get(ClusterOperationRecord, job_id)
                if job is not None:
                    job.status, job.phase, job.active_project_id = 'unknown', str(exc)[:80], None
                    job.finished_at, job.results = utcnow(), results
                    session.commit()
