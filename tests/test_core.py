from datetime import datetime, timezone
from uuid import uuid4
from types import SimpleNamespace
import yaml

from clusterweaver.core.generators import generate_hosts_update, generate_network_check, generate_network_connectivity, generate_precheck
from clusterweaver.core.models import NodeData, ProjectData
from clusterweaver.core.serializers import project_to_yaml, write_project_yaml
from clusterweaver.core.services.slugs import make_slug
from clusterweaver.core.services.git import GitService
from clusterweaver.core.services.network_config import configure_node_network


def sample_project():
    now = datetime.now(timezone.utc)
    return ProjectData(
        uuid=uuid4(), name="DB2 PROD", slug="db2-prod", customer="Example", description="Database cluster",
        rhel_major=9, rhel_minor="8", platform_type="physical", node_count=2,
        nodes=[NodeData(hostname="node01", nodename="node01lanc", fqdn="node01.example.test", site="Firenze", management_ip="10.0.0.11/24", management_gateway="10.0.0.1", cluster_ip="192.168.1.11/24", primary_interface="ens160", secondary_interface="ens224")],
        created_at=now, updated_at=now,
    )


def network_node():
    return SimpleNamespace(
        id=1, hostname="node01", bootstrap_ip="192.168.124.11", ssh_port=22,
        management_ip="192.168.124.11/24", management_gateway="192.168.124.1", primary_interface="enp1s0",
        cluster_ip="192.168.200.11/24", cluster_gateway="192.168.200.1", secondary_interface="enp7s0",
    )


def test_network_apply_is_noop_when_configuration_is_compliant(monkeypatch):
    calls = []
    monkeypatch.setattr("clusterweaver.core.services.network_config._connect", lambda node, password: (SimpleNamespace(close=lambda: None), "fingerprint"))

    def fake_run(_client, command):
        calls.append(command)
        if "os-release" in command or "ip link show" in command:
            return 0, ""
        if "address show dev enp1s0" in command:
            return 0, "2: enp1s0 inet 192.168.124.11/24 scope global enp1s0\n"
        if "route show default" in command:
            return 0, "default via 192.168.124.1 dev enp1s0 proto static\n"
        if "address show dev enp7s0" in command:
            return 0, "3: enp7s0 inet 192.168.200.11/24 scope global enp7s0\n"
        if "GENERAL.CONNECTION" in command:
            return 0, "clusterweaver-private-1\n"
        if "ipv4.never-default" in command:
            return 0, "yes\n"
        raise AssertionError(f"Unexpected modifying command: {command}")

    monkeypatch.setattr("clusterweaver.core.services.network_config._run", fake_run)
    result = configure_node_network(network_node(), "secret")
    assert result.ok
    assert "already compliant" in result.output
    assert not any("connection add" in command for command in calls)
    assert not any("systemd-run" in command for command in calls)


def test_private_network_change_is_blocked_when_pcs_reports_cluster(monkeypatch):
    monkeypatch.setattr("clusterweaver.core.services.network_config._connect", lambda node, password: (SimpleNamespace(close=lambda: None), "fingerprint"))

    def fake_run(_client, command):
        if "os-release" in command or "ip link show" in command:
            return 0, ""
        if "address show dev enp1s0" in command:
            return 0, "2: enp1s0 inet 192.168.124.11/24 scope global enp1s0\n"
        if "route show default" in command:
            return 0, "default via 192.168.124.1 dev enp1s0\n"
        if "address show dev enp7s0" in command:
            return 0, "3: enp7s0 inet 192.168.200.99/24 scope global enp7s0\n"
        if "GENERAL.CONNECTION" in command:
            return 0, "old-private\n"
        if "ipv4.never-default" in command:
            return 0, "yes\n"
        if command == "rpm -q pcs":
            return 0, "pcs-0.12\n"
        if command == "pcs status":
            return 0, "Cluster name: production\nCluster Summary:\n"
        raise AssertionError(command)

    monkeypatch.setattr("clusterweaver.core.services.network_config._run", fake_run)
    result = configure_node_network(network_node(), "secret")
    assert not result.ok
    assert "Private network changes are blocked" in result.output
    assert "Cluster name: production" in result.output


def test_slug_is_filesystem_safe():
    assert make_slug("  Caffè DB2 / PROD ") == "caffe-db2-prod"


def test_yaml_is_human_readable_and_round_trips(tmp_path):
    project = sample_project()
    text = project_to_yaml(project)
    parsed = yaml.safe_load(text)
    assert parsed["project"]["os"] == {"distribution": "rhel", "major": 9, "minor": "8"}
    assert parsed["nodes"][0]["hostname"] == "node01"
    assert parsed["nodes"][0]["nodename"] == "node01lanc"
    assert parsed["nodes"][0]["primary_interface"] == "ens160"
    assert parsed["nodes"][0]["management_gateway"] == "10.0.0.1"
    path, changed = write_project_yaml(project, tmp_path)
    assert changed and path.read_text() == text
    assert write_project_yaml(project, tmp_path)[1] is False


def test_generator_contains_project_and_node_data():
    script = generate_precheck(sample_project())
    assert script.startswith("#!/bin/bash")
    assert "DB2 PROD" in script and "node01.example.test" in script
    assert "RHEL 9.8" in script and "set -o pipefail" in script
    assert "interfaces=ens160,ens224" in script
    assert "management=10.0.0.11/24 via 10.0.0.1" in script


def test_rhel_98_network_check_is_read_only_and_node_aware():
    script = generate_network_check(sample_project())
    assert "RHEL 9.8 network verification" in script
    assert "node01)" in script
    assert "PRIMARY_IFACE=ens160" in script
    assert "EXPECTED_CLUSTER_IP=192.168.1.11" in script
    assert "no changes made" in script
    assert "nmcli" in script and "ip -brief link" in script


def test_rhel_102_network_check_validates_routes_and_never_default():
    project = sample_project()
    project.rhel_major = 10
    project.rhel_minor = "2"
    script = generate_network_check(project)
    assert "RHEL 10.2 network verification" in script
    assert "EXPECTED_MGMT_GATEWAY=10.0.0.1" in script
    assert "default route uses" in script
    assert "ipv4.never-default" in script
    assert "Network verification PASSED" in script


def test_hosts_update_uses_private_ips_nodenames_and_safety_guards():
    project = sample_project()
    project.nodes.append(NodeData(hostname="node02", nodename="node02lanc", cluster_ip="192.168.1.12/24"))
    script = generate_hosts_update(project)
    assert "192.168.1.11 node01lanc" in script
    assert "192.168.1.12 node02lanc" in script
    assert "cp -a" in script and "mktemp" in script
    assert "/root/clusterweaver-backups/hosts" in script
    assert "manifest.txt" in script
    assert 'MARKER=\'ClusterWeaver ' in script
    assert 'echo "# BEGIN ${MARKER}"' in script
    assert "EUID" in script


def test_rhel_102_hosts_update_is_supported_and_release_guarded():
    project = sample_project()
    project.rhel_major = 10
    project.rhel_minor = "2"
    script = generate_hosts_update(project)
    assert "EXPECTED_RELEASE=10.2" in script
    assert "RHEL ${EXPECTED_RELEASE} detected" in script
    assert "not yet supported" not in script


def test_network_connectivity_checks_peer_route_ping_mtu_and_duplicates():
    project = sample_project()
    project.nodes.append(NodeData(hostname="node02", nodename="node02lanc", cluster_ip="192.168.1.12/24", secondary_interface="ens224"))
    script = generate_network_connectivity(project)
    assert "192.168.1.12|node02lanc" in script
    assert 'ip -4 route get "${peer_ip}"' in script
    assert 'ping -c 2 -W 2 "${peer_ip}"' in script
    assert 'ping -c 1 -W 2 -M do' in script
    assert "arping -D" in script
    assert "PASS=${PASS_COUNT} FAIL=${FAIL_COUNT}" in script


def test_rhel_102_network_connectivity_is_supported_and_release_guarded():
    project = sample_project()
    project.rhel_major = 10
    project.rhel_minor = "2"
    project.nodes.append(NodeData(hostname="node02", nodename="node02lanc", cluster_ip="192.168.1.12/24", secondary_interface="ens224"))
    script = generate_network_connectivity(project)
    assert "RHEL ${EXPECTED_RELEASE} cluster network connectivity" in script
    assert "EXPECTED_RELEASE=10.2" in script
    assert "RHEL ${EXPECTED_RELEASE} detected" in script
    assert "not yet supported" not in script


def test_git_commits_changes_only_once(tmp_path):
    service = GitService(tmp_path)
    service.initialize()
    project_file = tmp_path / "example" / "project.yaml"
    project_file.parent.mkdir()
    project_file.write_text("project: example\n", encoding="utf-8")
    assert service.commit_path(project_file, "Create example project") is True
    assert service.commit_path(project_file, "No changes") is False
