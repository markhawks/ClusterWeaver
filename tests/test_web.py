from clusterweaver.persistence import db
from clusterweaver.persistence.models import NodeRecord, ProjectRecord
import subprocess
from types import SimpleNamespace


def test_new_project_suggests_two_node_ha_examples(client):
    response = client.get("/projects/new")
    assert b"postgres-ha-prod" in response.data
    assert b"db2-ha-prod" in response.data
    assert b"apache-ha-prod" in response.data
    assert b'Two-node PostgreSQL HA cluster' in response.data
    assert b'name="node_count"' in response.data and b'value="2"' in response.data
    assert b'<option selected value="10">RHEL 10</option>' in response.data
    assert b'<option selected value="2">2</option>' in response.data
    assert b'<option selected value="virtual">Virtual</option>' in response.data
    assert b'<option selected value="kvm">KVM</option>' in response.data
    assert b'>VMware</option>' in response.data and b'>Proxmox</option>' in response.data


def test_project_creation_writes_database_yaml_and_git(client, app):
    response = client.post("/projects/new", data={
        "name": "DB2 PROD", "customer": "Example", "description": "Test",
        "rhel_major": "9", "rhel_minor": "8", "platform_type": "physical", "node_count": "2",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"DB2 PROD" in response.data
    assert b"All projects" in response.data
    assert b">Home</a>" in response.data
    assert b"Created" in response.data
    assert b"Last modified" in response.data
    assert b"clusterweaver-sphere-logo.png" in response.data
    assert b'rel="icon"' in response.data
    assert b"Generated workflow" in response.data
    assert response.data.count(b"Show script") == 4
    assert response.data.count(b"Full screen") == 4
    assert b'id="script-viewer"' in response.data
    assert b'id="project-configuration" class="collapse show"' in response.data
    assert b"cw-icon-settings" in response.data
    assert b"cw-icon-cluster" in response.data
    with app.app_context():
        assert db.session.query(ProjectRecord).count() == 1
    root = app.config["PROJECTS_ROOT"]
    assert (root / "db2-prod" / "project.yaml").exists()
    assert (root / ".git").exists()
    project_list = client.get("/")
    assert b'class="clickable-row"' in project_list.data
    assert b'role="link"' in project_list.data
    history = subprocess.run(["git", "log", "--oneline"], cwd=root, check=True, capture_output=True, text=True)
    assert "Create DB2 PROD project" in history.stdout


def test_node_creation_updates_generated_script(client, app):
    response = client.post("/projects/new", data={
        "name": "Web Cluster", "customer": "Example", "rhel_major": "9", "rhel_minor": "8",
        "platform_type": "virtual", "node_count": "2",
    })
    project_url = response.headers["Location"]
    response = client.post(f"{project_url}/nodes/new", data={
        "hostname": "node01", "nodename": "node01lanc", "fqdn": "node01.example.test", "site": "Roma",
        "management_ip": "10.0.0.11/24", "management_gateway": "10.0.0.1", "cluster_ip": "192.168.0.11/24", "cluster_gateway": "",
        "primary_interface": "ens160", "secondary_interface": "custom1",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"node01.example.test" in response.data
    assert b"cw-icon-vm" in response.data
    assert b"ens160 / custom1" in response.data
    add_node_page = client.get(f"{project_url}/nodes/new")
    assert b'<option value="custom1">' in add_node_page.data
    duplicate = client.post(f"{project_url}/nodes/new", data={
        "hostname": "node01", "nodename": "node01lanc", "fqdn": "node01.example.test",
        "management_ip": "10.0.0.11/24", "management_gateway": "10.0.0.1", "cluster_ip": "192.168.0.12/24", "cluster_gateway": "",
        "primary_interface": "ens160",
    })
    assert b"already used by another node" in duplicate.data
    with app.app_context():
        node_id = db.session.query(NodeRecord.id).scalar()
    clone_page = client.get(f"{project_url}/nodes/{node_id}/clone")
    assert b"Clone node node01" in clone_page.data
    clone = client.post(f"{project_url}/nodes/{node_id}/clone", data={
        "hostname": "node02", "nodename": "node02lanc", "fqdn": "node02.example.test", "site": "Roma",
        "management_ip": "10.0.0.12/24", "management_gateway": "10.0.0.1", "cluster_ip": "192.168.0.12/24", "cluster_gateway": "",
        "primary_interface": "ens160", "secondary_interface": "custom1",
    }, follow_redirects=True)
    assert b"Node cloned" in clone.data
    assert b"node02lanc" in clone.data
    assert b"02 \xc2\xb7 Network verification" in response.data
    network_download = client.get(f"{project_url}/network-check.sh")
    assert network_download.status_code == 200
    assert b"network verification" in network_download.data
    hosts_download = client.get(f"{project_url}/hosts-update.sh")
    assert hosts_download.status_code == 200
    assert b"192.168.0.11 node01lanc" in hosts_download.data
    assert b"192.168.0.12 node02lanc" in hosts_download.data
    connectivity_download = client.get(f"{project_url}/network-connectivity.sh")
    assert connectivity_download.status_code == 200
    assert b"cluster network connectivity" in connectivity_download.data


def test_invalid_ip_is_rejected(client):
    response = client.post("/projects/new", data={
        "name": "IP Test", "customer": "Example", "rhel_major": "7", "rhel_minor": "9", "platform_type": "physical", "node_count": "1",
    })
    response = client.post(f"{response.headers['Location']}/nodes/new", data={"hostname": "node01", "management_ip": "999.1.1.1"})
    assert b"Enter an IPv4 address with subnet prefix" in response.data


def test_management_gateway_is_required_and_must_match_subnet(client):
    response = client.post("/projects/new", data={
        "name": "Gateway Test", "customer": "Example", "rhel_major": "9", "rhel_minor": "8", "platform_type": "physical", "node_count": "1",
    })
    node_url = f"{response.headers['Location']}/nodes/new"
    page = client.get(node_url)
    assert b"gateway-suggestion" in page.data
    script = client.get("/static/js/app.js")
    assert b"Suggested gateway for this subnet" in script.data
    base = {
        "hostname": "node01", "nodename": "node01lanc", "management_ip": "192.168.27.24/24", "primary_interface": "ens160",
    }
    missing = client.post(node_url, data=base)
    assert b"This field is required" in missing.data
    outside = client.post(node_url, data={**base, "management_gateway": "192.168.28.1"})
    assert b"Management gateway must belong to the management subnet" in outside.data


def test_cluster_gateway_is_optional_but_requires_cluster_subnet(client):
    response = client.post("/projects/new", data={
        "name": "Private Gateway Test", "customer": "Example", "rhel_major": "9", "rhel_minor": "8", "platform_type": "physical", "node_count": "1",
    })
    node_url = f"{response.headers['Location']}/nodes/new"
    response = client.post(node_url, data={
        "hostname": "node01", "nodename": "node01lanc", "management_ip": "192.168.27.24/24",
        "management_gateway": "192.168.27.1", "primary_interface": "ens160", "cluster_gateway": "192.168.28.1",
    })
    assert b"Configure the cluster/private IP and subnet before its gateway" in response.data


def test_node_form_explains_site(client):
    response = client.post("/projects/new", data={
        "name": "Site Help", "customer": "Lab", "rhel_major": "10", "rhel_minor": "2",
        "platform_type": "virtual", "node_count": "1",
    })
    response = client.get(f"{response.headers['Location']}/nodes/new")
    assert b"Roma, Datacenter-A, VMware-DC1" in response.data
    assert b"Geographic cluster" in response.data


def test_rhel_10_kvm_project_suggests_node_network_defaults(client):
    project = client.post("/projects/new", data={
        "name": "KVM Cluster", "customer": "Lab", "rhel_major": "10", "rhel_minor": "2",
        "platform_type": "virtual", "hypervisor": "kvm", "node_count": "2",
    })
    response = client.get(f"{project.headers['Location']}/nodes/new")
    assert b'value="192.168.124.11/24"' in response.data
    assert b'value="192.168.124.1"' in response.data
    assert b'value="enp1s0"' in response.data
    assert b'value="192.168.200.11/24"' in response.data
    assert b'value="enp7s0"' in response.data
    assert b"Suggested RHEL 10/KVM defaults" in response.data


def test_project_warns_when_node_has_no_cluster_private_ip(client):
    project = client.post("/projects/new", data={
        "name": "Incomplete Network", "customer": "Lab", "rhel_major": "10", "rhel_minor": "2",
        "platform_type": "virtual", "hypervisor": "kvm", "node_count": "1",
    })
    detail_url = project.headers["Location"]
    response = client.post(f"{detail_url}/nodes/new", data={
        "hostname": "node01", "nodename": "node01lanc", "management_ip": "192.168.124.11/24",
        "management_gateway": "192.168.124.1", "primary_interface": "enp1s0",
    }, follow_redirects=True)
    assert b"node-network-warning" in response.data
    assert b"cluster/private IP is not configured" in response.data
    assert b"not configured" in response.data


def test_ssh_discovery_uses_bootstrap_endpoint_without_echoing_password(client, monkeypatch):
    project = client.post("/projects/new", data={
        "name": "SSH Test", "customer": "Lab", "rhel_major": "10", "rhel_minor": "2",
        "platform_type": "virtual", "hypervisor": "kvm", "node_count": "2",
    })
    project_url = project.headers["Location"]
    client.post(f"{project_url}/nodes/new", data={
        "hostname": "node01", "nodename": "node01lanc", "management_ip": "192.168.124.11/24",
        "management_gateway": "192.168.124.1", "primary_interface": "enp1s0", "bootstrap_ip": "192.168.124.101", "ssh_port": "22",
    })
    captured = {}
    def fake_discovery(node, password):
        captured["password"] = password
        return SimpleNamespace(hostname=node.hostname, endpoint=f"{node.bootstrap_ip}:22", ok=True, output="RHEL 10.2", fingerprint="SHA256:test")
    monkeypatch.setattr("clusterweaver.web.routes.projects.discover_node", fake_discovery)
    response = client.post(f"{project_url}/ssh-discovery", data={"password": "one-time-password"})
    assert response.status_code == 200
    assert b"RHEL 10.2" in response.data and b"SHA256:test" in response.data
    assert b"one-time-password" not in response.data
    assert captured["password"] == "one-time-password"


def test_network_apply_requires_confirmation_and_updates_bootstrap_ip(client, app, monkeypatch):
    project = client.post("/projects/new", data={
        "name": "Network Apply", "customer": "Lab", "rhel_major": "10", "rhel_minor": "2",
        "platform_type": "virtual", "hypervisor": "kvm", "node_count": "1",
    })
    project_url = project.headers["Location"]
    client.post(f"{project_url}/nodes/new", data={
        "hostname": "node01", "nodename": "node01lanc", "management_ip": "192.168.124.11/24",
        "management_gateway": "192.168.124.1", "primary_interface": "enp1s0",
        "bootstrap_ip": "192.168.124.101", "ssh_port": "22",
    })
    with app.app_context():
        node_id = db.session.query(NodeRecord.id).scalar()
    fake = SimpleNamespace(hostname="node01", endpoint="192.168.124.11:22", ok=True, output="configured", rollback_pending=False)
    monkeypatch.setattr("clusterweaver.web.routes.projects.configure_node_network", lambda node, password: fake)
    rejected = client.post(f"{project_url}/network-apply", data={"node_id": node_id, "password": "temporary"}, follow_redirects=True)
    assert b"confirm the network change" in rejected.data
    applied = client.post(f"{project_url}/network-apply", data={"node_id": node_id, "password": "temporary", "confirm": "y"})
    assert b"configured" in applied.data
    with app.app_context():
        assert db.session.get(NodeRecord, node_id).bootstrap_ip == "192.168.124.11"


def test_network_apply_shows_running_progress(client):
    project = client.post("/projects/new", data={
        "name": "Progress Test", "customer": "Lab", "rhel_major": "10", "rhel_minor": "2",
        "platform_type": "virtual", "hypervisor": "kvm", "node_count": "1",
    })
    response = client.get(project.headers["Location"])
    assert b'id="network-apply-form"' in response.data
    assert b'id="network-apply-progress"' in response.data
    assert b"/root/clusterweaver-backups/network/" in response.data
    script = client.get("/static/js/app.js")
    assert b"Configuration running" in script.data


def test_remote_prechecks_run_from_gui_and_report_per_node(client, monkeypatch):
    project = client.post("/projects/new", data={
        "name": "Remote Precheck", "customer": "Lab", "rhel_major": "10", "rhel_minor": "2",
        "platform_type": "virtual", "hypervisor": "kvm", "node_count": "1",
    })
    project_url = project.headers["Location"]
    client.post(f"{project_url}/nodes/new", data={
        "hostname": "node01", "nodename": "node01lanc", "management_ip": "192.168.124.11/24",
        "management_gateway": "192.168.124.1", "primary_interface": "enp1s0",
        "bootstrap_ip": "192.168.124.11", "ssh_port": "22",
    })
    page = client.get(project_url)
    assert b"Run on nodes" in page.data and b'id="precheck-run-dialog"' in page.data
    captured = {}
    def fake_run(node, password, script):
        captured.update(password=password, script=script)
        return SimpleNamespace(hostname=node.hostname, endpoint="192.168.124.11:22", ok=True, output="precheck complete", fingerprint="SHA256:test")
    monkeypatch.setattr("clusterweaver.web.routes.projects.run_read_only_script", fake_run)
    response = client.post(f"{project_url}/run-prechecks", data={"password": "temporary-password"})
    assert response.status_code == 200
    assert b"Remote pre-checks" in response.data and b"precheck complete" in response.data
    assert b"temporary-password" not in response.data
    assert captured["password"] == "temporary-password"
    assert captured["script"].startswith("#!/bin/bash")


def test_remote_network_check_is_available_from_gui(client, monkeypatch):
    project = client.post("/projects/new", data={
        "name": "Remote Network Check", "customer": "Lab", "rhel_major": "10", "rhel_minor": "2",
        "platform_type": "virtual", "hypervisor": "kvm", "node_count": "1",
    })
    project_url = project.headers["Location"]
    client.post(f"{project_url}/nodes/new", data={
        "hostname": "node01", "nodename": "node01lanc", "management_ip": "192.168.124.11/24",
        "management_gateway": "192.168.124.1", "primary_interface": "enp1s0",
        "cluster_ip": "192.168.200.11/24", "cluster_gateway": "192.168.200.1", "secondary_interface": "enp7s0",
        "bootstrap_ip": "192.168.124.11", "ssh_port": "22",
    })
    page = client.get(project_url)
    assert b'id="network-check-run-dialog"' in page.data
    captured = {}
    def fake_run(node, password, script):
        captured.update(password=password, script=script)
        return SimpleNamespace(hostname=node.hostname, endpoint="192.168.124.11:22", ok=True, output="Network verification PASSED", fingerprint="SHA256:test")
    monkeypatch.setattr("clusterweaver.web.routes.projects.run_read_only_script", fake_run)
    response = client.post(f"{project_url}/run-network-checks", data={"network-check-password": "temporary"})
    assert response.status_code == 200 and b"Network verification PASSED" in response.data
    assert "RHEL 10.2 network verification" in captured["script"]


def test_copy_script_has_http_fallback(client):
    response = client.get("/static/js/app.js")
    assert response.status_code == 200
    assert b'document.execCommand("copy")' in response.data
    assert b"window.isSecureContext" in response.data
