from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
import os
import subprocess
import sys
import time

import pytest
import yaml

from clusterweaver.core.services import dell_oem
from clusterweaver.core.services.dell_oem import OEMCheckError, OEMClient, inspect_profile, validate_oem_endpoint
from clusterweaver.core.services.stonith import generate_oem_verification_script, verify_oem_profiles
from clusterweaver.persistence import db
from clusterweaver.persistence.models import NodeRecord, ProjectRecord, StonithConfigurationRecord, StonithProfileRecord, StepExecutionRecord


@pytest.fixture
def stonith_project(app):
    project = ProjectRecord(name="OEM test", slug="oem-test", cluster_name="oem-test", customer="Example",
        rhel_major=9, rhel_minor="8", platform_type="physical", hardware="dell", node_count=2)
    db.session.add(project)
    for index in (1, 2):
        db.session.add(NodeRecord(project=project, hostname=f"node0{index}", nodename=f"node0{index}lanc",
            management_ip=f"10.0.0.{10 + index}/24", management_gateway="10.0.0.1",
            cluster_ip=f"192.168.1.{10 + index}/24", primary_interface="ens160", secondary_interface="ens224"))
    db.session.commit()
    return project


def profile_data(project, verify=False):
    data = {"hardware": "dell", "endpoint": "ome.example.test", "verify" if verify else "save": "y"}
    for index, node in enumerate(project.nodes):
        data.update({f"profiles-{index}-node_id": str(node.id), f"profiles-{index}-hostname": node.hostname,
                     f"profiles-{index}-profile_name": f"Profile {node.hostname}",
                     f"profiles-{index}-username": "oem-reader", f"profiles-{index}-password": "not-a-real-secret"})
    return data


def test_stonith_save_roundtrip_and_never_persists_password(client, app, stonith_project):
    project = stonith_project
    path = f"/projects/{project.id}/stonith/profiles"
    page = client.get(f"/projects/{project.id}")
    assert b"Cluster STONITH Configuration and Testing" in page.data
    assert b"08a" in page.data
    assert client.get(path).status_code == 200
    result = client.post(path, data=profile_data(project), follow_redirects=True)
    assert result.status_code == 200
    assert b"DELL OEM profiles saved" in result.data
    assert b"not-a-real-secret" not in result.data
    assert db.session.query(StonithConfigurationRecord).count() == 1
    assert db.session.query(StonithProfileRecord).count() == 2
    document = yaml.safe_load((Path(app.config["PROJECTS_ROOT"]) / project.slug / "project.yaml").read_text())
    assert document["stonith"]["endpoint"] == "ome.example.test"
    assert "not-a-real-secret" not in str(document)
    page = client.get(path)
    assert b"Profile node01" in page.data and b"not-a-real-secret" not in page.data
    exported = client.get(f"/projects/{project.id}/export.cwp")
    imported = client.post("/projects/import", data={"archive": (BytesIO(exported.data), "oem.cwp")}, content_type="multipart/form-data", follow_redirects=True)
    assert imported.status_code == 200
    assert db.session.query(StonithProfileRecord).count() == 4
    assert db.session.query(StonithConfigurationRecord).count() == 2
    assert db.session.query(StepExecutionRecord).count() == 0


def test_stonith_validation_and_result_invalidation(client, stonith_project, monkeypatch):
    project = stonith_project
    path = f"/projects/{project.id}/stonith/profiles"
    data = profile_data(project, verify=True)
    data["profiles-0-password"] = ""
    assert b"Enter the OEM password" in client.post(path, data=data).data
    assert db.session.query(StonithConfigurationRecord).count() == 0
    data = profile_data(project)
    data["profiles-0-hostname"] = "Node01"
    assert b"including uppercase/lowercase" in client.post(path, data=data).data
    assert db.session.query(StonithConfigurationRecord).count() == 0
    data = profile_data(project)
    data["profiles-1-profile_name"] = data["profiles-0-profile_name"]
    assert b"unique DELL profile" in client.post(path, data=data).data
    data = profile_data(project)
    data["endpoint"] = "https://ome.example.test/api"
    assert b"without a URL" in client.post(path, data=data).data
    monkeypatch.setattr("clusterweaver.web.routes.stonith.verify_oem_profiles", lambda endpoint, profiles, ca_file: [
        SimpleNamespace(hostname=item["hostname"], endpoint=endpoint, ok=True, output="verified", fingerprint="") for item in profiles])
    result = client.post(path, data=profile_data(project, verify=True))
    assert b"DELL OEM profile verification" in result.data
    assert db.session.query(StepExecutionRecord).filter_by(step="08a", status="pass").count() == 2
    data = profile_data(project)
    data["profiles-0-profile_name"] = "New profile"
    client.post(path, data=data)
    assert db.session.query(StepExecutionRecord).filter_by(step="08a").count() == 0


def test_stonith_read_only_role_cannot_submit(client, stonith_project):
    # The same application-wide allowlist that protects existing operations must
    # reject POST even though readers can inspect the new definitions page.
    from clusterweaver.persistence.models import UserRecord
    from werkzeug.security import generate_password_hash
    client.application.config["LOGIN_DISABLED"] = False
    user = UserRecord(username="viewer", role="user", password_hash=generate_password_hash("viewer-password"))
    db.session.add(user)
    db.session.commit()
    client.post("/login", data={"username": "viewer", "password": "viewer-password"})
    path = f"/projects/{stonith_project.id}/stonith/profiles"
    assert client.get(path).status_code == 200
    assert client.post(path, data=profile_data(stonith_project)).status_code == 403
    assert db.session.query(StonithConfigurationRecord).count() == 0


class InventoryClient:
    def __init__(self, profile=None, device=None):
        self.profile = profile or {"ProfileName": "Profile node01", "TargetId": 11, "TargetTypeId": 1000, "ProfileState": 10, "LastRunStatus": 2060}
        self.device = device or {"DeviceName": "node01", "Id": 11, "ConnectionState": True, "Status": 1000, "PowerState": 17}
        self.paths = []

    def collection(self, path):
        self.paths.append(path)
        return [self.device] if "DeviceService" in path else [self.profile]


def test_oem_names_assignment_and_status():
    client = InventoryClient()
    output = inspect_profile(client, "node01", "Profile node01")
    assert "profile state=10" in output
    assert "power state=17" in output
    assert client.paths == ["/api/DeviceService/Devices", "/api/ProfileService/Profiles"]
    client = InventoryClient(device={"DeviceName": "Node01", "Id": 11})
    with pytest.raises(OEMCheckError, match="uppercase/lowercase"):
        inspect_profile(client, "node01", "Profile node01")
    client = InventoryClient(profile={"ProfileName": "profile node01", "TargetId": 11})
    with pytest.raises(OEMCheckError, match="uppercase/lowercase"):
        inspect_profile(client, "node01", "Profile node01")
    client = InventoryClient(profile={"ProfileName": "Profile node01", "TargetId": 12, "TargetTypeId": 1000})
    with pytest.raises(OEMCheckError, match="not 'node01'"):
        inspect_profile(client, "node01", "Profile node01")
    client = InventoryClient(profile={"ProfileName": "Profile node01", "TargetId": 11, "TargetTypeId": 1000})
    with pytest.raises(OEMCheckError, match="no status"):
        inspect_profile(client, "node01", "Profile node01")
    client = InventoryClient(device={"DeviceName": "node01", "Id": 11, "ConnectionState": False})
    with pytest.raises(OEMCheckError, match="disconnected"):
        inspect_profile(client, "node01", "Profile node01")


def test_oem_https_credentials_are_not_forwarded_and_errors_are_sanitized(monkeypatch):
    client = OEMClient("ome.example.test", "reader", "secret", time.monotonic() + 45)
    with pytest.raises(OEMCheckError, match="not forwarded"):
        client.get("https://other.example.test/api/DeviceService/Devices")
    captured = []
    def reject(request, timeout):
        captured.append(request)
        raise HTTPError(request.full_url, 401, "secret in remote error", {}, None)
    monkeypatch.setattr(client.opener, "open", reject)
    with pytest.raises(OEMCheckError, match="HTTP 401") as exc:
        client.get("/api/DeviceService/Devices")
    assert "secret in remote error" not in str(exc.value)
    assert captured[0].get_method() == "GET"
    for endpoint in ("https://ome", "ome/path", "reader@ome", "10.0.0.999", "ome:443"):
        with pytest.raises(ValueError):
            validate_oem_endpoint(endpoint)
    assert validate_oem_endpoint("10.0.0.50") == "10.0.0.50"


def test_oem_verification_redacts_password_and_script_prompts(monkeypatch):
    profiles = [dict(hostname="node01", profile_name="Profile node01", username="reader", password="secret-value")]
    monkeypatch.setattr("clusterweaver.core.services.stonith.inspect_profile", lambda *args: "PASS: secret-value")
    results = verify_oem_profiles("ome.example.test", profiles)
    assert results[0].ok and results[0].output == "PASS: [redacted]"
    script = generate_oem_verification_script("ome.example.test", profiles)
    assert "secret-value" not in script and "getpass.getpass" in script
    compile(script, "oem-check.py", "exec")


def test_oem_pagination_and_timeout_fail_without_partial_success(monkeypatch):
    client = OEMClient("ome.example.test", "reader", "secret", time.monotonic() + 45)
    responses = iter([
        {"value": [{"DeviceName": "node01"}], "@odata.count": 2, "@odata.nextLink": "/api/DeviceService/Devices?$skip=1"},
        {"value": [{"DeviceName": "node02"}], "@odata.count": 2},
    ])
    monkeypatch.setattr(client, "get", lambda path: next(responses))
    assert len(client.collection("/api/DeviceService/Devices")) == 2
    monkeypatch.setattr(client, "get", lambda path: {"value": [], "@odata.count": 1})
    with pytest.raises(OEMCheckError, match="incomplete"):
        client.collection("/api/DeviceService/Devices")
    client = OEMClient("ome.example.test", "reader", "secret", time.monotonic() - 1)
    with pytest.raises(OEMCheckError, match="45-second"):
        client.get("/api/DeviceService/Devices")


def test_stonith_project_deletion_cascades_definitions(client, stonith_project):
    client.post(f"/projects/{stonith_project.id}/stonith/profiles", data=profile_data(stonith_project))
    db.session.delete(stonith_project)
    db.session.commit()
    assert db.session.query(StonithConfigurationRecord).count() == 0
    assert db.session.query(StonithProfileRecord).count() == 0


def test_stonith_database_migration(tmp_path):
    env = dict(os.environ, CLUSTERWEAVER_DATABASE_URL=f"sqlite:///{tmp_path / 'migrated.db'}")
    executable = Path(sys.executable)
    result = subprocess.run([str(executable), "-m", "alembic", "upgrade", "head"], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    import sqlite3
    with sqlite3.connect(tmp_path / "migrated.db") as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0018_stonith_passwords"
        assert "password" not in {row[1] for row in connection.execute("PRAGMA table_info(stonith_profiles)")}
    result = subprocess.run([str(executable), "-m", "alembic", "downgrade", "0014_user_password_change"], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_ipmi_save_export_and_mode_change(client, app, stonith_project):
    project = stonith_project
    path = f'/projects/{project.id}/stonith/profiles'
    data = profile_data(project)
    data.update(mode='ipmi', endpoint='')
    for index in range(2):
        data[f'profiles-{index}-controller_endpoint'] = f'10.0.1.{index + 10}'
        data[f'profiles-{index}-resource_name'] = f'fence-node0{index + 1}'
        data.pop(f'profiles-{index}-profile_name')
    result = client.post(path, data=data, follow_redirects=True)
    assert result.status_code == 200 and b'DELL iDRAC profiles saved' in result.data
    config = db.session.query(StonithConfigurationRecord).one()
    assert config.mode == 'ipmi' and config.endpoint == ''
    assert config.profiles[0].controller_endpoint == '10.0.1.10'
    page = client.get(path)
    assert b'fence_ipmilan' in page.data and b'not-a-real-secret' not in page.data
    exported = client.get(f'/projects/{project.id}/export.cwp')
    result = client.post('/projects/import', data={'archive': (BytesIO(exported.data), 'ipmi.cwp')}, content_type='multipart/form-data')
    assert result.status_code == 302
    assert db.session.query(StonithConfigurationRecord).filter_by(mode='ipmi').count() == 2
    data['profiles-1-controller_endpoint'] = data['profiles-0-controller_endpoint']
    assert b'different iDRAC endpoint' in client.post(path, data=data).data
    assert client.post(path, data=profile_data(project)).status_code == 302
    assert config.mode == 'oem' and all(not p.controller_endpoint for p in config.profiles)


def test_ipmi_status_only_timeout_redaction_and_script(monkeypatch):
    from clusterweaver.core.services import dell_ipmi
    from clusterweaver.core.services.stonith import verify_ipmi_profiles, generate_ipmi_verification_script
    profile = dict(hostname='node01', controller_endpoint='10.0.1.10', resource_name='fence-node01', username='root', password='my-secret')
    calls = []
    monkeypatch.setattr(dell_ipmi.shutil, 'which', lambda name: '/usr/sbin/fence_ipmilan')
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout='Status: OFF\n', stderr='')
    monkeypatch.setattr(dell_ipmi.subprocess, 'run', run)
    results = verify_ipmi_profiles([profile])
    assert results[0].ok and 'Status: OFF' in results[0].output
    args, kwargs = calls[0]
    assert args == ['/usr/sbin/fence_ipmilan']
    assert 'action=status\n' in kwargs['input'] and 'lanplus=1\n' in kwargs['input']
    assert 'my-secret' not in str(args) and 0 < kwargs['timeout'] <= 20
    script = generate_ipmi_verification_script([profile])
    assert 'my-secret' not in script
    compile(script, 'ipmi-check.py', 'exec')
    monkeypatch.setattr(dell_ipmi.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=1, stdout='', stderr='my-secret error'))
    result = verify_ipmi_profiles([profile])[0]
    assert not result.ok and 'my-secret' not in result.output and '[redacted]' in result.output
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 20)
    monkeypatch.setattr(dell_ipmi.subprocess, 'run', timeout)
    assert 'timed out' in verify_ipmi_profiles([profile])[0].output
    monkeypatch.setattr(dell_ipmi.shutil, 'which', lambda name: None)
    monkeypatch.setattr(dell_ipmi.Path, 'is_file', lambda path: False)
    assert 'missing' in verify_ipmi_profiles([profile])[0].output
    profile['password'] = 'secret\naction=off'
    assert 'newlines' in verify_ipmi_profiles([profile])[0].output


def test_controller_password_encrypted_reused_revealed_and_not_exported(client, app, stonith_project, monkeypatch):
    import tarfile
    from cryptography.fernet import Fernet
    project = stonith_project
    path = f'/projects/{project.id}/stonith/profiles'
    data = profile_data(project)
    assert client.post(path, data=data).status_code == 302
    config = db.session.query(StonithConfigurationRecord).one()
    profile = config.profiles[0]
    token = profile.password_encrypted
    assert token and 'not-a-real-secret' not in token
    assert b'not-a-real-secret' not in client.get(path).data
    assert b'stonith-password-toggle' in client.get(path).data
    reveal = f'/projects/{project.id}/stonith/profiles/{profile.node_id}/password'
    response = client.post(reveal)
    assert response.json == {'password': 'not-a-real-secret'}
    assert response.headers['Cache-Control'] == 'no-store'
    assert client.get(reveal).status_code == 405
    assert client.post(f'/projects/{project.id}/stonith/profiles/999999/password').status_code == 404
    observed = []
    def verify(endpoint, profiles, ca_file):
        observed.extend(profiles)
        return [SimpleNamespace(hostname=p['hostname'], endpoint=endpoint, ok=True, output='verified', fingerprint='') for p in profiles]
    monkeypatch.setattr('clusterweaver.web.routes.stonith.verify_oem_profiles', verify)
    data = profile_data(project, verify=True)
    for index in range(2):
        data[f'profiles-{index}-password'] = ''
    assert client.post(path, data=data).status_code == 200
    assert [p['password'] for p in observed] == ['not-a-real-secret'] * 2
    assert profile.password_encrypted == token
    archive = client.get(f'/projects/{project.id}/export.cwp')
    with tarfile.open(fileobj=BytesIO(archive.data), mode='r:*') as package:
        contents = b''.join(package.extractfile(m).read() for m in package.getmembers() if m.isfile())
    assert b'not-a-real-secret' not in contents and token.encode() not in contents
    imported = client.post('/projects/import', data={'archive': (BytesIO(archive.data), 'example.cwp')}, content_type='multipart/form-data')
    assert imported.status_code == 302
    imported_config = db.session.query(StonithConfigurationRecord).filter(StonithConfigurationRecord.id != config.id).one()
    assert all(not p.password_encrypted for p in imported_config.profiles)
    data = profile_data(project)
    for index in range(2):
        data[f'profiles-{index}-password'] = ''
    data['profiles-0-username'] = 'another-user'
    assert client.post(path, data=data).status_code == 302
    assert profile.password_encrypted == ''
    # Ciphertext is never recoverable with a different service key.
    profile.password_encrypted = token
    db.session.commit()
    key = Path(app.config['PROJECTS_ROOT']).parent / 'stonith_secrets' / 'key'
    key.write_bytes(Fernet.generate_key())
    response = client.post(reveal)
    assert response.status_code == 409 and 'cannot be decrypted' in response.json['error']


def test_reveal_requires_role_and_csrf(client, app, stonith_project):
    from clusterweaver.persistence.models import UserRecord
    from werkzeug.security import generate_password_hash
    project = stonith_project
    client.post(f'/projects/{project.id}/stonith/profiles', data=profile_data(project))
    profile = db.session.query(StonithProfileRecord).first()
    path = f'/projects/{project.id}/stonith/profiles/{profile.node_id}/password'
    app.config['WTF_CSRF_ENABLED'] = True
    assert client.post(path).status_code == 400
    import re
    page = client.get(f'/projects/{project.id}/stonith/profiles')
    csrf_token = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', page.data).group(1).decode()
    assert client.post(path, data={'csrf_token': csrf_token}).json == {'password': 'not-a-real-secret'}
    app.config['WTF_CSRF_ENABLED'] = False
    user = UserRecord(username='reader', password_hash=generate_password_hash('example-password'), role='user')
    db.session.add(user)
    db.session.commit()
    app.config['LOGIN_DISABLED'] = False
    with client.session_transaction() as session:
        session['authenticated'], session['user_id'] = True, user.id
    assert client.post(path).status_code == 403
    assert b'stonith-password-toggle' not in client.get(f'/projects/{project.id}/stonith/profiles').data


def test_ipmi_finds_standard_sbin_agent_without_path(monkeypatch):
    from clusterweaver.core.services import dell_ipmi
    monkeypatch.setattr(dell_ipmi.shutil, 'which', lambda name: None)
    monkeypatch.setattr(dell_ipmi.Path, 'is_file', lambda path: str(path) == '/usr/sbin/fence_ipmilan')
    monkeypatch.setattr(dell_ipmi.os, 'access', lambda path, mode: True)
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout='Status: ON\n', stderr='')
    monkeypatch.setattr(dell_ipmi.subprocess, 'run', run)
    output = dell_ipmi.inspect_ipmi(dict(hostname='node01', controller_endpoint='192.0.2.10', resource_name='fence-node01', username='operator', password='example-secret'), time.monotonic() + 45)
    assert 'Status: ON' in output
    assert calls == [['/usr/sbin/fence_ipmilan']]


def test_ipmi_verification_runs_each_controller_on_its_cluster_node(monkeypatch):
    import json
    from io import StringIO
    from clusterweaver.core.services import ssh_bootstrap
    from clusterweaver.core.services.stonith import verify_ipmi_profiles_on_nodes
    from clusterweaver.core.services.ssh_credentials import SSHCredentials
    calls = []
    closed = []
    profiles = [dict(hostname=f'node0{i}', controller_endpoint=f'192.0.2.{i}', resource_name=f'fence-node0{i}', username='operator', password=f'controller-secret-{i}') for i in (1, 2)]
    nodes = [SimpleNamespace(hostname=f'node0{i}', bootstrap_ip=f'198.51.100.{i}') for i in (1, 2)]
    def connect(node, credentials):
        assert credentials.password == 'ssh-secret'
        stream = StringIO()
        stream.channel = SimpleNamespace(shutdown_write=lambda: None)
        def execute(command, timeout):
            assert 'controller-secret' not in command and 'ssh-secret' not in command
            assert 'python3 -c ' in command and 'action' in command
            assert 0 < timeout <= 25
            calls.append((node.hostname, stream))
            return stream, SimpleNamespace(channel=node.hostname), None
        return SimpleNamespace(exec_command=execute, close=lambda: closed.append(node.hostname)), 'SHA256:example'
    monkeypatch.setattr(ssh_bootstrap, '_connect', connect)
    monkeypatch.setattr(ssh_bootstrap, '_collect_channel', lambda channel, timeout: (0, 'Status: ON\ncontroller-secret-1 controller-secret-2 ssh-secret'))
    results = verify_ipmi_profiles_on_nodes(nodes, SSHCredentials(password='ssh-secret'), profiles)
    assert len(results) == 2 and all(r.ok for r in results)
    assert sorted(closed) == ['node01', 'node02']
    for name, stream in calls:
        payload = json.loads(stream.getvalue())
        assert payload['hostname'] == name
        assert payload['controller_endpoint'] == ('192.0.2.1' if name == 'node01' else '192.0.2.2')
        assert payload['password'] == ('controller-secret-1' if name == 'node01' else 'controller-secret-2')
    assert all('secret' not in r.output and 'via SSH' in r.output for r in results)
    assert all(not r.ok and 'SSH key' in r.output for r in verify_ipmi_profiles_on_nodes(nodes, None, profiles))


def test_ipmi_web_verification_dispatches_saved_credentials_to_nodes(client, app, stonith_project, monkeypatch):
    project = stonith_project
    data = profile_data(project)
    data.update(mode='ipmi', endpoint='')
    for index in range(2):
        data[f'profiles-{index}-controller_endpoint'] = f'192.0.2.{index+1}'
        data[f'profiles-{index}-resource_name'] = f'fence-node0{index+1}'
    path = f'/projects/{project.id}/stonith/profiles'
    assert client.post(path, data=data).status_code == 302
    observed = []
    monkeypatch.setattr('clusterweaver.web.routes.stonith.project_credentials', lambda project: 'ssh-credential')
    def verify(nodes, credentials, profiles):
        assert credentials == 'ssh-credential'
        assert [n.hostname for n in nodes] == ['node01', 'node02']
        observed.extend(profiles)
        return [SimpleNamespace(hostname=p['hostname'], endpoint=p['controller_endpoint'], ok=True, output='Status: ON via SSH', fingerprint='') for p in profiles]
    monkeypatch.setattr('clusterweaver.web.routes.stonith.verify_ipmi_profiles_on_nodes', verify)
    data.pop('save')
    data['verify'] = 'y'
    for index in range(2):
        data[f'profiles-{index}-password'] = ''
    response = client.post(path, data=data)
    assert response.status_code == 200 and b'Status: ON via SSH' in response.data
    assert len(observed) == 2 and all(p['password'] == 'not-a-real-secret' for p in observed)
    assert b'not-a-real-secret' not in response.data
