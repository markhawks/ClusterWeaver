from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4
import subprocess

import pytest
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from clusterweaver.core.services import cluster_operations as ops
from clusterweaver.core.services.ssh_credentials import SSHCredentials
from clusterweaver.persistence import db
from clusterweaver.persistence.models import ClusterOperationRecord, StepExecutionRecord, UserRecord, utcnow
from clusterweaver.web.ssh_credentials import project_key_store
from test_stonith import stonith_project


def snapshot_text(project, *, active=True, enabled=False, standby=None, quorum=True, resources_running=0):
    names = [n.nodename for n in project.nodes]
    config = 'totem {\n cluster_name: ' + project.cluster_name + '\n}\nnodelist {\n'
    config += ''.join(' node {\n name: ' + name + '\n ring0_addr: 10.0.0.1\n }\n' for name in names) + '}\n'
    xml = '<crm_mon><summary><current_dc present="true" with_quorum="' + str(quorum).lower() + '"/></summary><nodes>'
    xml += ''.join(f'<node name="{name}" online="true" standby="{str(name == standby).lower()}" maintenance="false" unclean="false" shutdown="false" resources_running="{resources_running if name == standby else 0}"/>' for name in names)
    xml += '</nodes><resources/><failures/></crm_mon>'
    state, boot = ('active' if active else 'inactive'), ('enabled' if enabled else 'disabled')
    return '\n__CW_CONFIG__\n' + config + '\n__CW_SERVICES__\npacemaker ' + state + '\ncorosync ' + state + '\n__CW_BOOT__\npacemaker ' + boot + '\ncorosync ' + boot + '\n__CW_XML__\n' + (xml if active else '') + '\n__CW_STATUS__\nCluster name: ' + project.cluster_name + '\nFull cluster status\n__CW_END__\n'


@pytest.fixture
def ready_project(app, stonith_project):
    project = stonith_project
    for index, node in enumerate(project.nodes):
        node.bootstrap_ip = f'10.0.0.{index+1}'
        db.session.add(StepExecutionRecord(project=project, node=node, step='00k', status='pass', output='key verified'))
    db.session.commit()
    from clusterweaver.persistence.repositories.projects import to_domain
    dto = to_domain(project)
    store = project_key_store(dto)
    store.activate(store.prepare())
    return dto


def make_job(project, action, target=''):
    record = ClusterOperationRecord(id=str(uuid4()), project_id=project.id, active_project_id=project.id,
        action=action, target_node=target, username='tester', status='queued', phase='Queued', results=[])
    db.session.add(record)
    db.session.commit()
    return record.id


def read_job(job_id):
    with Session(db.engine) as session:
        return session.get(ClusterOperationRecord, job_id)


def test_snapshot_checks_identity_membership_stopped_nodes_and_xml(ready_project):
    project = ready_project
    text = snapshot_text(project)
    snapshot = ops.parse_snapshot(text, project)
    assert snapshot['quorum'] is True and len(snapshot['nodes']) == 2
    assert snapshot['services']['pacemaker'] == 'active'
    stopped = ops.parse_snapshot(snapshot_text(project, active=False), project)
    assert stopped['quorum'] is None and not stopped['nodes']
    assert ops.desired_state(stopped, 'stop')
    with pytest.raises(ValueError, match='uppercase/lowercase'):
        ops.parse_snapshot(text.replace('cluster_name: oem-test', 'cluster_name: OEM-TEST'), project)
    with pytest.raises(ValueError, match='membership differs'):
        ops.parse_snapshot(text.replace('name: node01lanc', 'name: wrong'), project)
    with pytest.raises(ValueError, match='Live Pacemaker cluster name'):
        ops.parse_snapshot(text.replace('Cluster name: oem-test', 'Cluster name: unrelated'), project)
    with pytest.raises(ValueError, match='Malformed'):
        ops.parse_snapshot(text.replace('</crm_mon>', 'invalid'), project)
    with pytest.raises(ValueError, match='incomplete'):
        ops.parse_snapshot(text.replace('online="true"', ''), project)
    with pytest.raises(ValueError, match='Live Pacemaker node membership'):
        ops.parse_snapshot(text.replace('name="node01lanc"', 'name="wrong"'), project)


def test_standby_guard_and_wait_for_resources_to_drain(ready_project):
    project = ready_project
    target = project.nodes[0].nodename
    snapshot = ops.parse_snapshot(snapshot_text(project), project)
    ops.standby_guard(snapshot, target)
    snapshot['nodes'][project.nodes[1].nodename]['standby'] = True
    with pytest.raises(ValueError, match='last node'):
        ops.standby_guard(snapshot, target)
    snapshot['quorum'] = False
    with pytest.raises(ValueError, match='quorum'):
        ops.standby_guard(snapshot, target)
    draining = ops.parse_snapshot(snapshot_text(project, standby=target, resources_running=2), project)
    assert not ops.desired_state(draining, 'standby', target)
    drained = ops.parse_snapshot(snapshot_text(project, standby=target), project)
    assert ops.desired_state(drained, 'standby', target)
    assert not ops.desired_state(drained, 'unstandby', target)


@pytest.mark.parametrize('action', ['start', 'stop', 'enable', 'disable', 'standby', 'unstandby'])
def test_jobs_issue_local_commands_once_and_verify_state(ready_project, monkeypatch, action):
    project = ready_project
    target = project.nodes[0].nodename if action in {'standby', 'unstandby'} else ''
    initial_active = action != 'start'
    initial_enabled = action == 'disable'
    state = {'changed': False}
    calls = []
    def snapshot(node, credentials, project, deadline):
        after = state['changed']
        active = (action != 'stop') if after else initial_active
        enabled = (action == 'enable') if after else initial_enabled
        standby = target if (action == 'standby' and after) or (action == 'unstandby' and not after) else None
        return ops.parse_snapshot(snapshot_text(project, active=active, enabled=enabled, standby=standby), project)
    def remote(node, credentials, script, timeout, deadline):
        calls.append((node.id, script))
        state['changed'] = True
        return 0, 'command accepted', 'fingerprint'
    monkeypatch.setattr(ops, 'snapshot_node', snapshot)
    monkeypatch.setattr(ops, 'remote_script', remote)
    job_id = make_job(project, action, target)
    ops.run_operation(db.engine, job_id, project, SSHCredentials(), action, target, poll_seconds=0)
    job = read_job(job_id)
    assert job.status == 'pass', job.results
    assert job.active_project_id is None and job.finished_at is not None
    assert len(calls) == (1 if target else 2)
    assert all('pcs node ' + action in script if target else 'pcs cluster ' + action in script for _, script in calls)
    assert all('--all' not in script for _, script in calls)
    assert all('cluster name differs' in script and 'cluster node names differ' in script for _, script in calls)


def test_failed_preflight_sends_no_mutation_and_timeout_is_never_retried(ready_project, monkeypatch):
    project = ready_project
    def fail(node, *args):
        raise ValueError('SSH key rejected or wrong cluster name')
    sent = []
    monkeypatch.setattr(ops, 'snapshot_node', fail)
    monkeypatch.setattr(ops, 'remote_script', lambda *args: sent.append(args))
    job_id = make_job(project, 'stop')
    ops.run_operation(db.engine, job_id, project, SSHCredentials(), 'stop')
    assert not sent and read_job(job_id).status == 'fail'
    state = {'changed': False}
    monkeypatch.setattr(ops, 'snapshot_node', lambda node, credentials, project, deadline: ops.parse_snapshot(snapshot_text(project, active=not state['changed']), project))
    def timeout(node, credentials, script, *args):
        sent.append(node.id)
        state['changed'] = True
        return 124, 'deadline exceeded', 'fingerprint'
    monkeypatch.setattr(ops, 'remote_script', timeout)
    job_id = make_job(project, 'stop')
    ops.run_operation(db.engine, job_id, project, SSHCredentials(), 'stop', poll_seconds=0)
    job = read_job(job_id)
    assert job.status == 'unknown' and len(sent) == 2
    assert all(result['snapshot']['services']['pacemaker'] == 'inactive' for result in job.results)
    assert all(result['state'] == 'unknown' for result in job.results)


def test_idempotent_boot_action_does_not_send_command(ready_project, monkeypatch):
    project = ready_project
    monkeypatch.setattr(ops, 'snapshot_node', lambda node, credentials, project, deadline: ops.parse_snapshot(snapshot_text(project, enabled=True), project))
    monkeypatch.setattr(ops, 'remote_script', lambda *args: pytest.fail('already enabled; no mutation expected'))
    job_id = make_job(project, 'enable')
    ops.run_operation(db.engine, job_id, project, SSHCredentials(), 'enable', poll_seconds=0)
    assert read_job(job_id).status == 'pass'


def test_api_requires_verified_keys_confirmation_and_serializes_jobs(client, app, ready_project, monkeypatch):
    project = ready_project
    launched = []
    monkeypatch.setattr('clusterweaver.web.routes.cluster_operations.start_background_job', lambda *args: launched.append(args))
    url = f'/projects/{project.id}/operations'
    assert client.post(url, data={'action': 'stop'}).status_code == 400
    assert client.post(url, data={'action': 'reboot', 'confirm': 'y'}).status_code == 400
    assert client.post(url, data={'action': 'standby', 'node_id': '999999', 'confirm': 'y'}).status_code == 400
    response = client.post(url, data={'action': 'start', 'confirm': 'y'})
    assert response.status_code == 202
    assert len(launched) == 1 and isinstance(launched[0][3], SSHCredentials)
    assert launched[0][3].password is None
    assert client.post(url, data={'action': 'stop', 'confirm': 'y'}).status_code == 409
    jobs = client.get(url).json['jobs']
    assert len(jobs) == 1 and jobs[0]['status'] == 'queued' and jobs[0]['username'] == 'test'
    assert 'private_key' not in str(jobs) and 'password' not in str(jobs)
    # Other modifying workflows and inventory changes cannot race this job.
    assert client.post(f'/projects/{project.id}/edit').status_code == 409
    assert client.post(f'/projects/{project.id}/run-cluster-setup').status_code == 409
    assert client.post(f'/projects/{project.id}/ssh-access').status_code == 409
    assert client.post(f'/projects/{project.id}/delete').status_code == 409
    page = client.get(f'/projects/{project.id}')
    assert b'Cluster Operations and Status' in page.data and b'Gestisci cluster' in page.data
    assert b'data-ready="true"' in page.data and b'Abilita al boot' in page.data
    # Expired/interrupted jobs are marked unknown and never replayed.
    job = db.session.get(ClusterOperationRecord, jobs[0]['id'])
    job.created_at = utcnow() - timedelta(seconds=ops.STALE_AFTER + 1)
    db.session.commit()
    assert client.get(url).json['jobs'][0]['status'] == 'unknown'
    assert len(launched) == 1
    assert client.post(url, data={'action': 'stop', 'confirm': 'y'}).status_code == 409
    assert client.post(url, data={'action': 'status'}).status_code == 202


def test_api_readers_can_refresh_but_not_modify(client, ready_project, monkeypatch):
    from werkzeug.security import generate_password_hash
    project = ready_project
    client.application.config['LOGIN_DISABLED'] = False
    db.session.add(UserRecord(username='cluster-reader', role='user', password_hash=generate_password_hash('reader-pass')))
    db.session.commit()
    client.post('/login', data={'username': 'cluster-reader', 'password': 'reader-pass'})
    monkeypatch.setattr('clusterweaver.web.routes.cluster_operations.start_background_job', lambda *args: None)
    url = f'/projects/{project.id}/operations'
    assert client.get(url).status_code == 200
    assert client.post(url, data={'action': 'stop', 'confirm': 'y'}).status_code == 403
    assert client.post(url, data={'action': 'status'}).status_code == 202


def test_missing_key_proof_disables_menu_and_rejects_operations(client, stonith_project):
    project = stonith_project
    page = client.get(f'/projects/{project.id}')
    assert b'data-ready="false"' in page.data
    assert client.post(f'/projects/{project.id}/operations', data={'action': 'status'}).status_code == 409


def test_guarded_script_rejects_wrong_identity_and_shell_injection(ready_project, tmp_path):
    project = ready_project
    configuration = tmp_path / 'corosync.conf'
    configuration.write_text('totem {\n cluster_name: unrelated\n}\n')
    script = ops.generate_operation_script(project, 'stop').replace('/etc/corosync/corosync.conf', str(configuration))
    result = subprocess.run(['bash'], input=script, text=True, capture_output=True)
    assert result.returncode != 0 and 'cluster name differs' in result.stdout
    with pytest.raises(ValueError):
        ops.generate_operation_script(project, 'stop; reboot')
    with pytest.raises(ValueError):
        ops.generate_operation_script(project, 'standby', 'node; reboot')


def test_real_background_worker_commits_status_and_releases_project_lock(client, ready_project, monkeypatch):
    import time
    project = ready_project
    monkeypatch.setattr(ops, 'snapshot_node', lambda node, credentials, project, deadline: ops.parse_snapshot(snapshot_text(project), project))
    response = client.post(f'/projects/{project.id}/operations', data={'action': 'status'})
    assert response.status_code == 202
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = read_job(response.json['id'])
        if job.status not in {'queued', 'running'}:
            break
        time.sleep(0.02)
    assert job.status == 'pass' and job.active_project_id is None
    assert len(job.results) == 2 and all(row['state'] == 'pass' for row in job.results)
    data = client.get(f'/projects/{project.id}/operations').json
    assert data['jobs'][0]['results'][0]['snapshot']['quorum'] is True


def test_failed_refresh_does_not_clear_uncertain_mutation(client, ready_project, monkeypatch):
    project = ready_project
    unknown = ClusterOperationRecord(id=str(uuid4()), project_id=project.id, action='stop', username='tester', status='unknown', phase='Interrupted', results=[], created_at=utcnow() - timedelta(seconds=3))
    failed_refresh = ClusterOperationRecord(id=str(uuid4()), project_id=project.id, action='status', username='tester', status='fail', phase='No SSH', results=[], created_at=utcnow() - timedelta(seconds=2))
    db.session.add_all([unknown, failed_refresh])
    db.session.commit()
    monkeypatch.setattr('clusterweaver.web.routes.cluster_operations.start_background_job', lambda *args: None)
    url = f'/projects/{project.id}/operations'
    assert client.post(url, data={'action': 'start', 'confirm': 'y'}).status_code == 409
    db.session.add(ClusterOperationRecord(id=str(uuid4()), project_id=project.id, action='status', username='tester', status='pass', phase='Fresh state', results=[]))
    db.session.commit()
    assert client.post(url, data={'action': 'start', 'confirm': 'y'}).status_code == 202
