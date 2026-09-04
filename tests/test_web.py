from clusterweaver.persistence import db
from clusterweaver.persistence.models import NodeRecord, ProjectRecord
import subprocess


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
        "name": "Web Cluster", "customer": "Example", "rhel_major": "10", "rhel_minor": "2",
        "platform_type": "virtual", "node_count": "2",
    })
    project_url = response.headers["Location"]
    response = client.post(f"{project_url}/nodes/new", data={
        "hostname": "node01", "nodename": "node01lanc", "fqdn": "node01.example.test", "site": "Roma",
        "management_ip": "10.0.0.11", "cluster_ip": "192.168.0.11",
        "primary_interface": "ens160", "secondary_interface": "custom1",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"node01.example.test" in response.data
    assert b"ens160 / custom1" in response.data
    add_node_page = client.get(f"{project_url}/nodes/new")
    assert b'<option value="custom1">' in add_node_page.data
    duplicate = client.post(f"{project_url}/nodes/new", data={
        "hostname": "node01", "nodename": "node01lanc", "fqdn": "node01.example.test",
        "management_ip": "10.0.0.11", "cluster_ip": "192.168.0.12",
    })
    assert b"already used by another node" in duplicate.data
    with app.app_context():
        node_id = db.session.query(NodeRecord.id).scalar()
    clone_page = client.get(f"{project_url}/nodes/{node_id}/clone")
    assert b"Clone node node01" in clone_page.data
    clone = client.post(f"{project_url}/nodes/{node_id}/clone", data={
        "hostname": "node02", "nodename": "node02lanc", "fqdn": "node02.example.test", "site": "Roma",
        "management_ip": "10.0.0.12", "cluster_ip": "192.168.0.12",
        "primary_interface": "ens160", "secondary_interface": "custom1",
    }, follow_redirects=True)
    assert b"Node cloned" in clone.data
    assert b"node02lanc" in clone.data


def test_invalid_ip_is_rejected(client):
    response = client.post("/projects/new", data={
        "name": "IP Test", "customer": "Example", "rhel_major": "7", "rhel_minor": "9", "platform_type": "physical", "node_count": "1",
    })
    response = client.post(f"{response.headers['Location']}/nodes/new", data={"hostname": "node01", "management_ip": "999.1.1.1"})
    assert b"Invalid IP address" in response.data


def test_node_form_explains_site(client):
    response = client.post("/projects/new", data={
        "name": "Site Help", "customer": "Lab", "rhel_major": "10", "rhel_minor": "2",
        "platform_type": "virtual", "node_count": "1",
    })
    response = client.get(f"{response.headers['Location']}/nodes/new")
    assert b"Roma, Datacenter-A, VMware-DC1" in response.data
    assert b"Geographic cluster" in response.data
