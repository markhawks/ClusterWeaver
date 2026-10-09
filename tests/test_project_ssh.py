from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import os
import subprocess

import paramiko
import pytest

from clusterweaver.core.services.project_ssh import ProjectSSHKeys, install_project_key, authorized_key_line, public_key_install_script
from clusterweaver.core.services.ssh_bootstrap import ProjectHostKeyPolicy, _connect, SSHResult
from clusterweaver.core.services.ssh_credentials import SSHCredentials
from clusterweaver.persistence import db
from clusterweaver.persistence.models import StepExecutionRecord
from clusterweaver.web.ssh_credentials import project_key_store, project_credentials
from test_stonith import stonith_project, profile_data


@pytest.fixture
def key_store(tmp_path):
    store = ProjectSSHKeys(tmp_path / 'keys', uuid4())
    pending = store.prepare()
    store.activate(pending)
    return store


def test_project_key_permissions_isolation_selection_and_rotation(key_store):
    store = key_store
    initial = store.key().get_base64()
    assert store.key().get_bits() == 3072
    assert store.directory.stat().st_mode & 0o777 == 0o700
    assert store.private.stat().st_mode & 0o777 == 0o600
    other = ProjectSSHKeys(store.directory.parent, uuid4())
    assert not other.available()
    assert store.prepare() == store.private
    assert store.key().get_base64() == initial
    assert isinstance(store.credentials(default='yesterday-password'), SSHCredentials)
    assert store.credentials(default='yesterday-password').password is None
    override = store.credentials('current-password')
    assert override.password == 'current-password' and override.private_key is None
    assert 'current-password' not in repr(override)
    rotated = store.prepare(rotate=True)
    assert store.prepare(rotate=True) == rotated and store.key().get_base64() == initial
    store.activate(rotated)
    assert store.key(store.previous).get_base64() == initial
    assert store.key().get_base64() != initial
    with pytest.raises(ValueError, match='Revoke the previous'):
        store.prepare(rotate=True)
    store.private.chmod(0o644)
    with pytest.raises(ValueError, match='0600'):
        store.key()


def test_authorized_key_payload_is_idempotent_and_preserves_existing_keys(key_store, tmp_path):
    directory = tmp_path / 'node-ssh'
    directory.mkdir()
    authorized = directory / 'authorized_keys'
    authorized.write_text('ssh-rsa EXTERNAL existing-key')
    line = authorized_key_line(key_store, key_store.private, '192.0.2.50')
    assert line.startswith('from="192.0.2.50",restrict ssh-rsa ')
    script = public_key_install_script(line).replace('/root/.ssh', str(directory))
    for _ in range(2):
        result = subprocess.run(['bash'], input=script, text=True, capture_output=True)
        assert result.returncode == 0, result.stderr
    assert authorized.read_text().splitlines().count(line) == 1
    assert 'ssh-rsa EXTERNAL existing-key' in authorized.read_text()
    assert authorized.stat().st_mode & 0o777 == 0o600
    assert 'PRIVATE KEY' not in script
    with pytest.raises(ValueError):
        authorized_key_line(key_store, key_store.private, 'source; reboot')


def test_host_key_enrollment_change_rejection_and_network_alias(key_store):
    first = paramiko.RSAKey.generate(1024)
    second = paramiko.RSAKey.generate(1024)
    keys = paramiko.HostKeys()
    client = SimpleNamespace(get_host_keys=lambda: keys)
    credentials = SSHCredentials(known_hosts=key_store.known_hosts, password='temporary', enroll_host=True)
    policy = ProjectHostKeyPolicy(credentials)
    policy.missing_host_key(client, '10.0.0.1', first)
    assert keys.check('10.0.0.1', first)
    assert key_store.known_hosts.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match='changed'):
        policy.missing_host_key(client, '10.0.0.1', second)
    strict = SSHCredentials(private_key=key_store.private, known_hosts=key_store.known_hosts)
    with pytest.raises(ValueError, match='not enrolled'):
        ProjectHostKeyPolicy(strict).missing_host_key(client, '10.0.0.2', first)
    reconnect = strict.for_reconnect(first)
    with pytest.raises(ValueError, match='does not match'):
        ProjectHostKeyPolicy(reconnect).missing_host_key(client, '10.0.0.2', second)
    ProjectHostKeyPolicy(reconnect).missing_host_key(client, '10.0.0.2', first)
    assert paramiko.HostKeys(str(key_store.known_hosts)).check('10.0.0.2', first)


def test_key_transport_uses_only_explicit_key_and_closes_failed_connection(key_store, monkeypatch):
    from clusterweaver.core.services import ssh_bootstrap
    captured = []
    hostkey = paramiko.RSAKey.generate(1024)
    class Client:
        def __init__(self):
            self.closed = False
        def load_host_keys(self, path):
            pass
        def set_missing_host_key_policy(self, policy):
            self.policy = policy
        def connect(self, **kwargs):
            captured.append(kwargs)
        def get_transport(self):
            return SimpleNamespace(get_remote_server_key=lambda: hostkey)
        def close(self):
            self.closed = True
    client = Client()
    monkeypatch.setattr(ssh_bootstrap.paramiko, 'SSHClient', lambda: client)
    credentials = SSHCredentials(private_key=key_store.private, known_hosts=key_store.known_hosts)
    node = SimpleNamespace(bootstrap_ip='10.0.0.1', ssh_port=2222)
    connected, fingerprint = _connect(node, credentials)
    assert connected is client and fingerprint.startswith('SHA256:')
    assert captured[0]['pkey'].get_base64() == key_store.key().get_base64()
    assert captured[0]['password'] is None and captured[0]['username'] == 'root'
    assert not captured[0]['allow_agent'] and not captured[0]['look_for_keys']
    assert captured[0]['hostname'] == '10.0.0.1' and captured[0]['port'] == 2222
    _connect(node, credentials.for_reconnect(hostkey))
    assert "ssh-ed25519" in captured[-1]["disabled_algorithms"]["keys"]
    assert "rsa-sha2-256" not in captured[-1]["disabled_algorithms"]["keys"]
    def reject(**kwargs):
        captured.append(kwargs)
        raise paramiko.AuthenticationException('key refused')
    client.connect = reject
    with pytest.raises(paramiko.AuthenticationException):
        _connect(node, credentials)
    assert client.closed and len(captured) == 3  # One attempt each, no password fallback.


def test_partial_installation_rotation_recovery_and_previous_revocation(key_store, monkeypatch):
    from clusterweaver.core.services import project_ssh
    store = key_store
    original = store.key().get_base64()
    nodes = [SimpleNamespace(id=i, hostname=f'node{i}', bootstrap_ip=f'10.0.0.{i}', ssh_port=22) for i in (1, 2)]
    fail = {2}
    calls = []
    def connect(node, credentials):
        calls.append((node.id, credentials))
        return SimpleNamespace(close=lambda: None), 'host-fingerprint'
    monkeypatch.setattr(project_ssh, '_connect', connect)
    monkeypatch.setattr(project_ssh, '_run', lambda client, command: (0, 'public key installed'))
    def verify(node, credentials):
        if node.id in fail:
            raise ValueError('node unavailable temporary-secret')
        assert credentials.private_key is not None and credentials.password is None
        return 'host-fingerprint', 'key verified'
    monkeypatch.setattr(project_ssh, '_verify', verify)
    results = install_project_key(store, nodes, {2: 'temporary-secret'}, '192.0.2.1', rotate=True)
    assert [r.ok for r in results] == [True, False]
    assert all('temporary-secret' not in r.output for r in results)
    assert store.pending.exists() and store.key().get_base64() == original
    assert 'not active yet' in results[0].output
    assert next(credentials for node_id, credentials in calls if node_id == 2).password == 'temporary-secret'
    fail.clear()
    results = install_project_key(store, nodes, {}, '192.0.2.1')
    assert all(r.ok for r in results) and not store.pending.exists()
    assert store.key().get_base64() != original and store.previous.exists()
    results = project_ssh.revoke_previous_key(store, nodes)
    assert all(r.ok for r in results) and not store.previous.exists()


def access_data(project, **kwargs):
    data = dict(source_ip='192.0.2.50', password='current-shared', confirm='y', install='y')
    for index, node in enumerate(project.nodes):
        data[f'nodes-{index}-node_id'] = str(node.id)
        data[f'nodes-{index}-hostname'] = node.hostname
        data[f'nodes-{index}-password'] = f'current-node{index}'
    data.update(kwargs)
    return data


def test_ssh_access_route_per_node_passwords_and_secrets_excluded(client, app, stonith_project, monkeypatch):
    project = stonith_project
    for index, node in enumerate(project.nodes):
        node.bootstrap_ip = f'10.0.0.{index + 1}'
    db.session.commit()
    url = f'/projects/{project.id}/ssh-access'
    assert client.get(url).status_code == 200
    assert b'ClusterWeaver SSH key' in client.get(f'/projects/{project.id}').data
    calls = []
    def install(store, nodes, passwords, source_ip, rotate):
        calls.append((passwords, source_ip, rotate))
        pending = store.prepare()
        store.activate(pending)
        return [SSHResult(node.hostname, node.bootstrap_ip, True, 'key-only verified') for node in nodes]
    monkeypatch.setattr('clusterweaver.web.routes.ssh_access.install_project_key', install)
    data = access_data(project)
    result = client.post(url, data=data)
    assert result.status_code == 200 and b'key-only verified' in result.data
    assert calls[0][0] == {node.id: f'current-node{index}' for index, node in enumerate(project.nodes)}
    assert calls[0][1:] == ('192.0.2.50', False)
    assert b'current-node' not in result.data and b'current-shared' not in result.data
    assert db.session.query(StepExecutionRecord).filter_by(step='00k', status='pass').count() == 2
    page = client.get(url)
    assert b'PRIVATE KEY' not in page.data and b'ssh-rsa' in page.data
    assert b'current-node' not in page.data
    exported = client.get(f'/projects/{project.id}/export.cwp')
    from tarfile import open as open_archive
    from io import BytesIO
    assert exported.status_code == 200
    with open_archive(fileobj=BytesIO(exported.data), mode="r:gz") as archive:
        assert all("id_rsa" not in name and "ssh_keys" not in name and "known_hosts" not in name for name in archive.getnames())
        assert all(b"PRIVATE KEY" not in archive.extractfile(member).read() for member in archive.getmembers() if member.isfile())
    data.pop('confirm')
    assert b'Confirm the public-key changes' in client.post(url, data=data).data
    data['verify'] = 'y'
    data.pop('install')
    monkeypatch.setattr('clusterweaver.web.routes.ssh_access.verify_project_key', lambda store, nodes: [SSHResult(n.hostname, n.bootstrap_ip, True, 'verified without password') for n in nodes])
    assert b'verified without password' in client.post(url, data=data).data


def test_every_workflow_accepts_project_key_without_password(client, app, stonith_project, monkeypatch):
    project = stonith_project
    for index, node in enumerate(project.nodes):
        node.bootstrap_ip = f'10.0.0.{index + 1}'
        for step in ('00a', '00b', '00c', '01', '02', '03', '04', '05', '06'):
            db.session.add(StepExecutionRecord(project=project, node=node, step=step, status='pass', output='previously verified'))
    db.session.commit()
    store = project_key_store(project)
    store.activate(store.prepare())
    app.config['SSH_BOOTSTRAP_PASSWORD'] = 'obsolete-password'
    captures = []
    def result(node, credentials, *args, **kwargs):
        captures.append(credentials)
        assert isinstance(credentials, SSHCredentials) and credentials.private_key == store.private
        assert credentials.password is None
        return SSHResult(node.hostname, node.bootstrap_ip, True, 'key authenticated')
    monkeypatch.setattr('clusterweaver.web.routes.projects.run_remote_script', result)
    monkeypatch.setattr('clusterweaver.web.routes.projects.discover_node', result)
    monkeypatch.setattr('clusterweaver.web.routes.projects.configure_node_network', result)
    monkeypatch.setattr('clusterweaver.web.routes.projects.bootstrap_peer_keys', lambda nodes, credentials: [result(n, credentials) for n in nodes])
    actions = [('ssh-discovery', {}), ('ssh-key-bootstrap', {'confirm': 'y'}),
        ('network-apply', {'node_id': project.nodes[0].id, 'confirm': 'y'}),
        ('run-prechecks', {}), ('run-network-checks', {}), ('run-hosts-update', {'hosts-update-confirm': 'y'}),
        ('run-network-connectivity', {}), ('run-package-install', {'package-install-confirm': 'y'}),
        ('run-pcsd-auth', {'pcsd-auth-confirm': 'y'}), ('run-cluster-setup', {'cluster-setup-confirm': 'y'})]
    for action, data in actions:
        response = client.post(f'/projects/{project.id}/{action}', data=data)
        assert response.status_code == 200, (action, response.status_code)
    assert len(captures) >= 19
    client.post(f'/projects/{project.id}/stonith/profiles', data=profile_data(project))
    monkeypatch.setattr('clusterweaver.web.routes.stonith.check_cluster_agents', lambda nodes, credentials, mode: [result(n, credentials) for n in nodes])
    assert client.post(f'/projects/{project.id}/stonith/check-agents').status_code == 200
    assert isinstance(project_credentials(project), SSHCredentials)


def test_project_key_page_read_only_user_cannot_mutate(client, stonith_project):
    from clusterweaver.persistence.models import UserRecord
    from werkzeug.security import generate_password_hash
    client.application.config['LOGIN_DISABLED'] = False
    db.session.add(UserRecord(username='ssh-viewer', role='user', password_hash=generate_password_hash('viewer-password')))
    db.session.commit()
    client.post('/login', data={'username': 'ssh-viewer', 'password': 'viewer-password'})
    path = f'/projects/{stonith_project.id}/ssh-access'
    assert client.get(path).status_code == 200
    assert client.post(path, data=access_data(stonith_project)).status_code == 403
