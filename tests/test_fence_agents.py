from pathlib import Path
from types import SimpleNamespace
import subprocess
import time

import pytest

from clusterweaver.core.services.fence_agents import check_cluster_agents, generate_agent_check_script
from clusterweaver.core.services.ssh_bootstrap import SSHResult
from clusterweaver.persistence import db
from clusterweaver.persistence.models import StepExecutionRecord
from test_stonith import stonith_project, profile_data


def test_agent_script_missing_healthy_broken_and_oem(tmp_path):
    rpm = tmp_path / 'rpm'
    rpm.write_text('#!/bin/sh\nexit 1\n')
    rpm.chmod(0o755)
    def run(mode):
        script = generate_agent_check_script(mode).replace('export PATH=/usr/sbin:/usr/bin:/sbin:/bin', f'export PATH={tmp_path}:/usr/bin:/bin')
        return subprocess.run(['bash'], input=script, text=True, capture_output=True)
    result = run('ipmi')
    assert result.returncode == 1 and 'required agent fence_ipmilan is missing' in result.stdout
    assert 'dnf install fence-agents-all' in result.stdout
    result = run('oem')
    assert result.returncode == 1 and 'no fence_* executable' in result.stdout
    agent = tmp_path / 'fence_ipmilan'
    agent.write_text('''#!/bin/sh
[ "$#" -eq 1 ] && [ "$1" = "--action=metadata" ] || exit 99
printf '<resource-agent name="fence_ipmilan"></resource-agent>\n'
''')
    agent.chmod(0o755)
    result = run('ipmi')
    assert result.returncode == 0 and 'metadata is readable' in result.stdout
    # Installing every agent is optional if the required individual package works.
    assert 'fence-agents-all: not installed' in result.stdout
    result = run('oem')
    assert result.returncode == 0 and 'not an agent compatibility test' in result.stdout
    agent.write_text('#!/bin/sh\necho dependency-error >&2\nexit 2\n')
    result = run('ipmi')
    assert result.returncode == 1 and 'installed but metadata cannot be read (exit 2)' in result.stdout
    with pytest.raises(ValueError):
        generate_agent_check_script('anything; reboot')


def test_agent_checks_use_ssh_ip_collect_all_nodes_and_redact(monkeypatch):
    from clusterweaver.core.services import fence_agents
    nodes = [SimpleNamespace(hostname=f'node{i}', bootstrap_ip=f'10.0.0.{i}', ssh_port=22) for i in (1, 2)]
    calls = []
    def check(node, password, script, deadline):
        calls.append((node.bootstrap_ip, password, script, deadline))
        return SSHResult(node.hostname, node.bootstrap_ip, node.hostname == 'node1', 'secret-root node result')
    monkeypatch.setattr(fence_agents, '_check_node', check)
    results = check_cluster_agents(nodes, 'secret-root', 'ipmi')
    assert [r.hostname for r in results] == ['node1', 'node2']
    assert results[0].ok and not results[1].ok
    assert all('secret-root' not in r.output for r in results)
    assert {call[0] for call in calls} == {'10.0.0.1', '10.0.0.2'}
    assert all('required=fence_ipmilan' in call[2] for call in calls)
    assert all(time.monotonic() < call[3] <= time.monotonic() + 45 for call in calls)


def test_node_agent_route_prerequisites_results_and_invalidation(client, app, stonith_project, monkeypatch):
    project = stonith_project
    check_path = f'/projects/{project.id}/stonith/check-agents'
    profile_path = f'/projects/{project.id}/stonith/profiles'
    app.config['SSH_BOOTSTRAP_PASSWORD'] = ''
    assert b'Enter the root SSH password' in client.post(check_path, follow_redirects=True).data
    data = {'agents-password': 'root-secret'}
    assert b'Save the STONITH profiles' in client.post(check_path, data=data, follow_redirects=True).data
    client.post(profile_path, data=profile_data(project))
    assert b'Configure an SSH bootstrap IP' in client.post(check_path, data=data, follow_redirects=True).data
    for index, node in enumerate(project.nodes):
        node.bootstrap_ip = f'10.0.0.{index + 1}'
    db.session.commit()
    calls = []
    def check(nodes, password, mode):
        calls.append((nodes, password, mode))
        return [SSHResult(node.hostname, node.bootstrap_ip, index == 0,
                         'agent present' if index == 0 else 'FAIL: missing agent\ndnf install fence-agents-all')
                for index, node in enumerate(nodes)]
    monkeypatch.setattr('clusterweaver.web.routes.stonith.check_cluster_agents', check)
    result = client.post(check_path, data=data)
    assert result.status_code == 200 and b'Cluster-node fence-agent verification' in result.data
    assert b'dnf install fence-agents-all' in result.data and b'root-secret' not in result.data
    assert calls[0][1:] == ('root-secret', 'oem')
    records = db.session.query(StepExecutionRecord).filter_by(step='08a-fa').all()
    assert {r.status for r in records} == {'pass', 'fail'}
    page = client.get(profile_path)
    assert b'Latest' in page.data and b'missing agent' in page.data
    assert b'<title>08a' in page.data
    assert b'<script>' not in page.data.split(b'</title>')[0]
    data = profile_data(project)
    data['profiles-0-profile_name'] = 'changed'
    client.post(profile_path, data=data)
    assert db.session.query(StepExecutionRecord).filter_by(step='08a-fa').count() == 0


def test_agent_route_read_only_role(client, stonith_project):
    from clusterweaver.persistence.models import UserRecord
    from werkzeug.security import generate_password_hash
    client.application.config['LOGIN_DISABLED'] = False
    db.session.add(UserRecord(username='agent-viewer', role='user', password_hash=generate_password_hash('viewer-password')))
    db.session.commit()
    client.post('/login', data={'username': 'agent-viewer', 'password': 'viewer-password'})
    result = client.post(f'/projects/{stonith_project.id}/stonith/check-agents', data={'agents-password': 'secret'})
    assert result.status_code == 403


def test_agent_transport_errors_and_total_budget(monkeypatch):
    from clusterweaver.core.services import fence_agents
    node = SimpleNamespace(hostname='node1', bootstrap_ip='10.0.0.1', ssh_port=22)
    def reject(*args, **kwargs):
        raise ConnectionError('SSH connection refused root-secret')
    monkeypatch.setattr(fence_agents, '_connect', reject)
    result = check_cluster_agents([node], 'root-secret', 'ipmi')[0]
    assert not result.ok and 'via SSH' in result.output and 'root-secret' not in result.output
    assert 'dnf install' not in result.output
    # Exercise the total-budget result without waiting or opening any real SSH connection.
    monkeypatch.setattr(fence_agents, 'wait', lambda futures, timeout: (set(), set(futures)))
    result = check_cluster_agents([node], 'root-secret', 'ipmi')[0]
    assert not result.ok and 'installation status is unknown' in result.output
    assert 'dnf install' not in result.output
