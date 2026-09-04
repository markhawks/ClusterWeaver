from datetime import datetime, timezone
from uuid import uuid4
import yaml

from clusterweaver.core.generators import generate_hosts_update, generate_network_check, generate_precheck
from clusterweaver.core.models import NodeData, ProjectData
from clusterweaver.core.serializers import project_to_yaml, write_project_yaml
from clusterweaver.core.services.slugs import make_slug
from clusterweaver.core.services.git import GitService


def sample_project():
    now = datetime.now(timezone.utc)
    return ProjectData(
        uuid=uuid4(), name="DB2 PROD", slug="db2-prod", customer="Example", description="Database cluster",
        rhel_major=9, rhel_minor="8", platform_type="physical", node_count=2,
        nodes=[NodeData(hostname="node01", nodename="node01lanc", fqdn="node01.example.test", site="Firenze", management_ip="10.0.0.11", cluster_ip="192.168.1.11", primary_interface="ens160", secondary_interface="ens224")],
        created_at=now, updated_at=now,
    )


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
    path, changed = write_project_yaml(project, tmp_path)
    assert changed and path.read_text() == text
    assert write_project_yaml(project, tmp_path)[1] is False


def test_generator_contains_project_and_node_data():
    script = generate_precheck(sample_project())
    assert script.startswith("#!/bin/bash")
    assert "DB2 PROD" in script and "node01.example.test" in script
    assert "RHEL 9.8" in script and "set -o pipefail" in script
    assert "interfaces=ens160,ens224" in script


def test_rhel_98_network_check_is_read_only_and_node_aware():
    script = generate_network_check(sample_project())
    assert "RHEL 9.8 network verification" in script
    assert "node01)" in script
    assert "PRIMARY_IFACE=ens160" in script
    assert "EXPECTED_CLUSTER_IP=192.168.1.11" in script
    assert "no changes made" in script
    assert "nmcli" in script and "ip -brief link" in script


def test_hosts_update_uses_private_ips_nodenames_and_safety_guards():
    project = sample_project()
    project.nodes.append(NodeData(hostname="node02", nodename="node02lanc", cluster_ip="192.168.1.12"))
    script = generate_hosts_update(project)
    assert "192.168.1.11 node01lanc" in script
    assert "192.168.1.12 node02lanc" in script
    assert "cp -a" in script and "mktemp" in script
    assert 'MARKER=\'ClusterWeaver ' in script
    assert 'echo "# BEGIN ${MARKER}"' in script
    assert "EUID" in script


def test_git_commits_changes_only_once(tmp_path):
    service = GitService(tmp_path)
    service.initialize()
    project_file = tmp_path / "example" / "project.yaml"
    project_file.parent.mkdir()
    project_file.write_text("project: example\n", encoding="utf-8")
    assert service.commit_path(project_file, "Create example project") is True
    assert service.commit_path(project_file, "No changes") is False
