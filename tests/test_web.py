from clusterweaver.persistence import db
from clusterweaver import create_app
from clusterweaver.persistence.database import Base
from clusterweaver.persistence.models import NodeRecord, ProjectGroupRecord, ProjectRecord, StepExecutionRecord, UserRecord
from config import TestConfig
import subprocess
from io import BytesIO
from types import SimpleNamespace
from werkzeug.security import generate_password_hash


def test_login_protects_application_and_shows_project_identity(tmp_path):
    application = create_app(
        TestConfig,
        LOGIN_DISABLED=False,
        LOGIN_USERNAME="admin",
        LOGIN_PASSWORD="strong-test-password",
        SECRET_KEY="login-test-secret",
        DATABASE_URL=f"sqlite:///{tmp_path / 'login.db'}",
        PROJECTS_ROOT=tmp_path / "projects",
    )
    with application.app_context():
        Base.metadata.create_all(db.engine)
    login_client = application.test_client()
    protected = login_client.get("/")
    assert protected.status_code == 302 and "/login?next=/" in protected.headers["Location"]
    page = login_client.get("/login")
    assert b"ClusterWeaver project logo" in page.data
    assert b"Version 0.1.10" in page.data
    assert b"remotely executes controlled workflows" in page.data
    assert b'<html lang="en" data-bs-theme="dark">' in page.data
    assert b'<body class="login-page">' in page.data
    stylesheet = login_client.get("/static/css/app.css")
    assert b'.login-page .text-secondary { color: #fff !important; }' in stylesheet.data
    assert b'.workflow-description p { color: #343a40 !important; }' in stylesheet.data
    assert b'.workflow-run-summary { min-height: 7rem; }' in stylesheet.data
    assert b'<nav class="navbar' not in page.data
    assert b"Changelog" not in page.data and b"About ClusterWeaver" not in page.data
    rejected = login_client.post("/login", data={"username": "admin", "password": "wrong"})
    assert b"Invalid username or password" in rejected.data
    accepted = login_client.post("/login?next=/", data={"username": "admin", "password": "strong-test-password"})
    assert accepted.status_code == 302 and accepted.headers["Location"] == "/"
    assert login_client.get("/").status_code == 200
    assert login_client.post("/logout").status_code == 302
    assert login_client.get("/").status_code == 302


def test_role_permissions_and_user_configuration(tmp_path):
    application = create_app(
        TestConfig, LOGIN_DISABLED=False, SECRET_KEY="role-test-secret",
        DATABASE_URL=f"sqlite:///{tmp_path / 'roles.db'}", PROJECTS_ROOT=tmp_path / "projects",
    )
    with application.app_context():
        Base.metadata.create_all(db.engine)
        db.session.add_all([
            UserRecord(username="admin", password_hash=generate_password_hash("administrator-pass"), role="administrator"),
            UserRecord(username="viewer", password_hash=generate_password_hash("read-only-password"), role="user"),
            UserRecord(username="cluster", password_hash=generate_password_hash("cluster-admin-pass"), role="clusteradmin"),
        ])
        db.session.commit()

    client = application.test_client()
    client.post("/login", data={"username": "viewer", "password": "read-only-password"})
    assert client.get("/").status_code == 200
    assert client.get("/configuration").status_code == 200
    assert b"available only to administrators" in client.get("/configuration").data
    assert client.get("/projects/new").status_code == 403
    assert client.post("/projects/new", data={}).status_code == 403
    assert client.post("/projects/1/delete", data={}).status_code == 403
    assert client.post("/configuration/users", data={}).status_code == 403

    client.post("/logout")
    client.post("/login", data={"username": "cluster", "password": "cluster-admin-pass"})
    assert client.get("/projects/new").status_code == 200
    assert client.post("/configuration/users", data={}).status_code == 403

    client.post("/logout")
    client.post("/login", data={"username": "admin", "password": "administrator-pass"})
    configuration = client.get("/configuration")
    assert configuration.status_code == 200
    assert b"Create user" in configuration.data and b"Access roles" in configuration.data
    assert b"Password last changed" in configuration.data
    assert b"Soft dark grey" in configuration.data
    assert b'class="btn btn-primary"' in configuration.data
    assert b'class="btn btn-danger"' in configuration.data
    assert b"btn-outline-primary" not in configuration.data
    assert b"btn-outline-danger" not in configuration.data
    themed = client.post("/configuration/theme", data={"theme-theme": "light"}, follow_redirects=True)
    assert b"Interface theme updated" in themed.data
    assert b'data-bs-theme="light"' in themed.data
    created = client.post("/configuration/users", data={
        "create-username": "operator", "create-password": "operator-password",
        "create-confirm_password": "operator-password", "create-role": "clusteradmin",
    }, follow_redirects=True)
    assert b"User operator created" in created.data
    with application.app_context():
        operator = db.session.query(UserRecord).filter_by(username="operator").one()
        assert operator.password_changed_at is not None


def mark_step_00_complete(app, through="00c"):
    steps = ("00a", "00b", "00c")
    with app.app_context():
        project = db.session.query(ProjectRecord).one()
        for node in project.nodes:
            for step in steps[:steps.index(through) + 1]:
                db.session.add(StepExecutionRecord(project_id=project.id, node_id=node.id, step=step, status="pass", output="test pass"))
        db.session.commit()


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
    assert b'id="hardware-field"' in response.data
    assert b'<option value="dell">Dell</option>' in response.data
    assert b'<option value="cisco">Cisco</option>' in response.data


def test_physical_project_requires_supported_hardware(client):
    rejected = client.post("/projects/new", data={
        "name": "Physical Cluster", "customer": "Lab", "rhel_major": "9", "rhel_minor": "8",
        "platform_type": "physical", "node_count": "2",
    }, follow_redirects=True)
    assert b"Select the hardware vendor for a physical project" in rejected.data
    assert b"Physical Cluster" not in client.get("/").data


def test_project_groups_are_unique_selectable_and_rendered_on_home(client, app):
    new_group = client.get("/groups/new")
    assert new_group.status_code == 200
    assert b'type="color"' in new_group.data
    created = client.post("/groups/new", data={
        "name": "PostgreSQL", "description": "PostgreSQL HA clusters", "color": "#198754",
    }, follow_redirects=True)
    assert b"Project group PostgreSQL created." in created.data
    assert b"PostgreSQL" in created.data and b"0 projects" in created.data

    duplicate = client.post("/groups/new", data={
        "name": "postgresql", "description": "Duplicate", "color": "#0d6efd",
    }, follow_redirects=True)
    assert b"A project group with this name already exists." in duplicate.data

    with app.app_context():
        group = db.session.query(ProjectGroupRecord).one()
        group_id = group.id
        assert group.color == "#198754"

    project_form = client.get("/projects/new")
    assert b'value="0">Ungrouped</option>' in project_form.data
    assert f'<option value="{group_id}">PostgreSQL</option>'.encode() in project_form.data
    project = client.post("/projects/new", data={
        "name": "PG PROD", "customer": "Example", "description": "Primary database",
        "group_id": str(group_id), "rhel_major": "10", "rhel_minor": "2",
        "platform_type": "virtual", "hypervisor": "kvm", "node_count": "2",
    })
    assert project.status_code == 302

    home = client.get("/")
    assert b"Project Groups" in home.data
    assert b"PostgreSQL" in home.data and b"1 project" in home.data
    assert b"PG PROD" in home.data and b'id="group-' in home.data
    assert f'id="group-{group_id}" class="collapse"'.encode() in home.data
    assert f'data-bs-target="#group-{group_id}" aria-expanded="false"'.encode() in home.data
    assert b"project-group-heading-name" in home.data
    assert b"group-collapse-chevron" in home.data and b"cw-icon-chevron" in home.data
    assert b"cw-icon-group" in home.data and b"project-entry-icon" in home.data
    assert b"Hide" not in home.data and b"Show" not in home.data
    app_script = client.get("/static/js/app.js")
    assert b'!toggle.classList.contains("collapse-toggle")' in app_script.data

    projects = client.get("/projects?column=group&q=PostgreSQL&sort=group&direction=asc")
    assert b">Group" in projects.data
    assert b"PG PROD" in projects.data and b"PostgreSQL" in projects.data
    assert b"Sorted asc" in projects.data

    renamed = client.post(f"/groups/{group_id}/edit", data={
        "name": "Postgres", "description": "Renamed group", "color": "#6f42c1",
    }, follow_redirects=True)
    assert b"Project group Postgres updated." in renamed.data
    with app.app_context():
        group = db.session.get(ProjectGroupRecord, group_id)
        assert group.name == "Postgres" and group.color == "#6f42c1"


def test_project_creation_writes_database_yaml_and_git(client, app):
    response = client.post("/projects/new", data={
        "name": "DB2 PROD", "customer": "Example", "description": "Test",
        "rhel_major": "9", "rhel_minor": "8", "platform_type": "physical", "hardware": "dell", "node_count": "2",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"DB2 PROD" in response.data
    assert b"All projects" in response.data
    assert b">Home</a>" in response.data
    assert b"Created" in response.data
    assert b"Last modified" in response.data
    assert b"clusterweaver-sphere-logo.png" in response.data
    assert b"cw-icon-home" in response.data
    assert b"cw-icon-projects" in response.data
    assert b'<span>Home</span>' in response.data and b'<span>Project</span>' in response.data
    assert b"cw-icon-notebook" in response.data
    assert b"Changelog" in response.data and b"Changelog <small" not in response.data
    assert b"Configuration" in response.data and b"About ClusterWeaver" in response.data
    assert b"github.com/markhawks/ClusterWeaver" in response.data and b"Author: Mark Hawks" in response.data and b"Gunicorn" in response.data
    assert "ClusterWeaver</strong><span>– Version 0.1.10</span>".encode() in response.data
    assert b"Linux High Availability Cluster Builder &amp; Lifecycle Manager" in response.data
    assert b'rel="icon"' in response.data
    assert b'/static/css/app.css?v=' in response.data and b'/static/js/app.js?v=' in response.data
    assert b"Generated workflow" in response.data
    assert b"Step 00" in response.data
    assert b"SSH discovery" in response.data and b"Peer SSH trust" in response.data and b"Network configuration" in response.data
    assert b"cw-icon-oscilloscope" in response.data
    assert b"cw-icon-cluster-settings" in response.data
    assert response.data.count(b"cw-icon-footprints") == 8
    assert b"0/5 complete" in response.data and b"5/5 remaining" in response.data
    assert b"0/3 complete" in response.data and b"3/3 remaining" in response.data
    assert b'id="pre-cluster-workflow" class="collapse show"' in response.data
    assert b'id="cluster-base-workflow" class="collapse"' in response.data
    assert b'id="workflow-run-01" class="btn btn-outline-secondary"' in response.data
    assert response.data.count(b"Show script") == 7
    assert response.data.count(b"Full screen") == 7
    assert b'id="script-viewer"' in response.data
    assert b'id="project-configuration" class="collapse show"' in response.data
    assert b'class="btn btn-primary" href="/projects/' in response.data
    assert b"btn-outline-primary" not in response.data
    assert b"cw-icon-settings" in response.data
    assert b"cw-icon-cluster" in response.data
    with app.app_context():
        assert db.session.query(ProjectRecord).count() == 1
        assert db.session.query(ProjectRecord).one().hardware == "dell"
    root = app.config["PROJECTS_ROOT"]
    assert (root / "db2-prod" / "project.yaml").exists()
    assert (root / ".git").exists()
    project_list = client.get("/projects")
    assert b'class="clickable-row"' in project_list.data
    assert b"Hypervisor/HW" in project_list.data and b"Dell" in project_list.data
    assert b'class="project-name">DB2 PROD' in project_list.data
    assert b'class="cluster-name"><span>Cluster:</span> db2-prod' in project_list.data
    assert b'class="project-notes text-truncate" title="Test"' in project_list.data
    assert b'class="btn btn-primary d-inline-flex align-items-center gap-2"' in project_list.data
    assert b"cw-icon-projects" in project_list.data
    assert b"cw-icon-search" in project_list.data
    assert b'btn btn-primary d-inline-flex justify-content-center align-items-center gap-2' in project_list.data
    assert b"cw-icon-open" in project_list.data
    assert b"cw-icon-export" in project_list.data
    assert b"cw-icon-delete" in project_list.data
    assert project_list.data.index(b"> Open</a>") < project_list.data.index(b"> Export</a>") < project_list.data.index(b"> Delete</button>")
    assert b"btn btn-sm btn-primary" in project_list.data
    assert b"btn btn-sm btn-warning" in project_list.data
    assert b"btn btn-sm btn-danger" in project_list.data
    assert b">01</td>" in project_list.data
    assert b"Remote Ready" in project_list.data and b"Remote setup incomplete" in project_list.data
    assert b'<thead><tr><th class="text-center"><a' in project_list.data
    assert b"Project number" in project_list.data
    filtered = client.get("/projects?column=customer&q=Example&sort=name&direction=asc")
    assert b"DB2 PROD" in filtered.data and b"Sorted asc" in filtered.data
    no_match = client.get("/projects?column=name&q=does-not-exist")
    assert b"No matching projects" in no_match.data
    assert b'role="link"' in project_list.data
    history = subprocess.run(["git", "log", "--oneline"], cwd=root, check=True, capture_output=True, text=True)
    assert "Create DB2 PROD project" in history.stdout


def test_project_delete_removes_database_state_and_versions_file_removal(client, app):
    response = client.post("/projects/new", data={
        "name": "Disposable HA", "customer": "Example", "description": "Delete test",
        "rhel_major": "10", "rhel_minor": "2", "platform_type": "virtual", "hypervisor": "kvm", "node_count": "1",
    })
    project_id = int(response.headers["Location"].rsplit("/", 1)[-1])
    client.post(f"/projects/{project_id}/nodes/new", data={
        "hostname": "delete01", "nodename": "delete01", "fqdn": "delete01.example.test", "site": "Lab",
        "management_ip": "192.168.124.31/24", "management_gateway": "192.168.124.1",
        "cluster_ip": "192.168.200.31/24", "cluster_gateway": "192.168.200.1",
        "primary_interface": "enp1s0", "secondary_interface": "enp7s0", "bootstrap_ip": "192.168.124.131", "ssh_port": "22",
    })
    with app.app_context():
        node = db.session.query(NodeRecord).filter_by(project_id=project_id).one()
        db.session.add(StepExecutionRecord(project_id=project_id, node_id=node.id, step="00a", status="pass", output="done"))
        db.session.commit()

    root = app.config["PROJECTS_ROOT"]
    assert (root / "disposable-ha" / "project.yaml").exists()
    deleted = client.post(f"/projects/{project_id}/delete", follow_redirects=True)
    assert deleted.status_code == 200
    assert b"Project Disposable HA deleted." in deleted.data
    assert b'class="project-name">Disposable HA' not in deleted.data
    assert not (root / "disposable-ha").exists()
    with app.app_context():
        assert db.session.query(ProjectRecord).count() == 0
        assert db.session.query(NodeRecord).count() == 0
        assert db.session.query(StepExecutionRecord).count() == 0
    history = subprocess.run(["git", "log", "--oneline", "-1"], cwd=root, check=True, capture_output=True, text=True)
    assert "Delete Disposable HA project" in history.stdout
    assert client.post(f"/projects/{project_id}/delete").status_code == 404


def test_project_export_and_import_create_safe_editable_copy(client, app):
    response = client.post("/projects/new", data={
        "name": "Portable HA", "customer": "Example", "description": "Move between environments",
        "rhel_major": "10", "rhel_minor": "2", "platform_type": "virtual", "hypervisor": "kvm", "node_count": "2",
    })
    project_url = response.headers["Location"]
    client.post(f"{project_url}/nodes/new", data={
        "hostname": "node01", "nodename": "node01", "fqdn": "node01.example.test", "site": "Lab",
        "management_ip": "192.168.124.11/24", "management_gateway": "192.168.124.1",
        "cluster_ip": "192.168.200.11/24", "cluster_gateway": "192.168.200.1",
        "primary_interface": "enp1s0", "secondary_interface": "enp7s0", "bootstrap_ip": "192.168.124.101", "ssh_port": "22",
    })
    project_id = int(project_url.rsplit("/", 1)[-1])
    with app.app_context():
        node = db.session.query(NodeRecord).filter_by(project_id=project_id).one()
        db.session.add(StepExecutionRecord(project_id=project_id, node_id=node.id, step="00a", status="pass", output="sensitive log"))
        db.session.commit()
    exported = client.get(f"/projects/{project_id}/export.cwp")
    assert exported.status_code == 200
    assert exported.headers["Content-Disposition"].endswith('filename=portable-ha.cwp')
    assert b"sensitive log" not in exported.data
    imported = client.post(
        "/projects/import", data={"archive": (BytesIO(exported.data), "portable-ha.cwp")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    assert imported.status_code == 200
    assert b"Portable HA (Imported)" in imported.data
    assert b"Remote execution state was reset" in imported.data
    with app.app_context():
        projects = db.session.query(ProjectRecord).order_by(ProjectRecord.id).all()
        assert len(projects) == 2
        assert projects[0].uuid != projects[1].uuid
        assert projects[1].slug == "portable-ha-2"
        assert len(projects[1].nodes) == 1
        assert projects[1].nodes[0].management_ip == "192.168.124.11/24"
        assert db.session.query(StepExecutionRecord).filter_by(project_id=projects[1].id).count() == 0
    index = client.get("/projects")
    assert b"Import project" in index.data
    assert b"cw-icon-import" in index.data and b"cw-icon-export" in index.data


def test_project_import_rejects_modified_or_invalid_archive(client):
    response = client.post("/projects/import", data={
        "archive": (BytesIO(b"not a tar archive"), "broken.cwp"),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert response.status_code == 200
    assert b"Project import failed" in response.data


def test_project_can_be_imported_from_server_directory(client, app):
    response = client.post("/projects/new", data={
        "name": "Server Archive", "customer": "Example", "description": "Offline transfer",
        "rhel_major": "10", "rhel_minor": "2", "platform_type": "virtual", "hypervisor": "kvm", "node_count": "2",
    })
    project_id = int(response.headers["Location"].rsplit("/", 1)[-1])
    exported = client.get(f"/projects/{project_id}/export.cwp")
    import_root = app.config["PROJECT_IMPORT_ROOT"]
    archive_path = import_root / "offline-project.cwp"
    archive_path.write_bytes(exported.data)

    index = client.get("/projects")
    assert b"Import from server" in index.data
    assert b"offline-project.cwp" in index.data
    imported = client.post(
        "/projects/import/server", data={"archive_name": "offline-project.cwp"}, follow_redirects=True,
    )
    assert imported.status_code == 200
    assert b"Project imported from server archive offline-project.cwp" in imported.data
    with app.app_context():
        assert db.session.query(ProjectRecord).count() == 2


def test_server_import_rejects_unlisted_paths_and_ignores_symlinks(client, app, tmp_path):
    import_root = app.config["PROJECT_IMPORT_ROOT"]
    outside = tmp_path / "outside.cwp"
    outside.write_bytes(b"not-an-archive")
    (import_root / "linked.cwp").symlink_to(outside)

    index = client.get("/projects")
    assert b"linked.cwp" not in index.data
    response = client.post(
        "/projects/import/server", data={"archive_name": "../outside.cwp"}, follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Select a valid .cwp archive from the server import directory" in response.data


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
        "name": "IP Test", "customer": "Example", "rhel_major": "7", "rhel_minor": "9", "platform_type": "physical", "hardware": "cisco", "node_count": "1",
    })
    response = client.post(f"{response.headers['Location']}/nodes/new", data={"hostname": "node01", "management_ip": "999.1.1.1"})
    assert b"Enter an IPv4 address with subnet prefix" in response.data


def test_hostname_is_limited_to_30_characters(client):
    project = client.post("/projects/new", data={
        "name": "Hostname Limit", "customer": "Example", "rhel_major": "10", "rhel_minor": "2",
        "platform_type": "virtual", "hypervisor": "kvm", "node_count": "1",
    })
    response = client.post(f"{project.headers['Location']}/nodes/new", data={
        "hostname": "n" * 31, "nodename": "node01lanc", "management_ip": "192.168.124.11/24",
        "management_gateway": "192.168.124.1", "primary_interface": "enp1s0", "ssh_port": "22",
    })
    assert b"Field cannot be longer than 30 characters" in response.data
    injected = client.post(f"{project.headers['Location']}/nodes/new", data={
        "hostname": "node$(touch-pwned)", "nodename": "node01lanc", "management_ip": "192.168.124.11/24",
        "management_gateway": "192.168.124.1", "primary_interface": "enp1s0", "ssh_port": "22",
    })
    assert b"letters, numbers, or hyphens" in injected.data


def test_management_gateway_is_required_and_must_match_subnet(client):
    response = client.post("/projects/new", data={
        "name": "Gateway Test", "customer": "Example", "rhel_major": "9", "rhel_minor": "8", "platform_type": "physical", "hardware": "dell", "node_count": "1",
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
        "name": "Private Gateway Test", "customer": "Example", "rhel_major": "9", "rhel_minor": "8", "platform_type": "physical", "hardware": "dell", "node_count": "1",
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
    project_page = client.get(project_url)
    assert b'id="bootstrap-run-00b" class="btn btn-sm btn-success"' in project_page.data
    monkeypatch.setattr("clusterweaver.web.routes.projects.discover_node", lambda node, password: SimpleNamespace(hostname=node.hostname, endpoint="test:22", ok=False, output="discovery failed"))
    client.post(f"{project_url}/ssh-discovery", data={"password": "one-time-password"})
    failed_page = client.get(project_url)
    assert b'id="bootstrap-run-00a" class="btn btn-sm btn-danger"' in failed_page.data
    assert b"</span> Failed</button>" in failed_page.data
    project_list = client.get("/projects")
    assert b'text-danger" role="img" aria-label="SSH bootstrap discovery failed"' in project_list.data


def test_network_apply_requires_confirmation_and_updates_bootstrap_ip(client, app, monkeypatch):
    project = client.post("/projects/new", data={
        "name": "Network Apply", "customer": "Lab", "rhel_major": "9", "rhel_minor": "8",
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
    mark_step_00_complete(app, through="00b")
    fake = SimpleNamespace(hostname="node01", endpoint="192.168.124.11:22", ok=True, output="configured", rollback_pending=False)
    captured = {}
    def fake_network_config(node, password, *, expected_release):
        captured["expected_release"] = expected_release
        return fake
    monkeypatch.setattr("clusterweaver.web.routes.projects.configure_node_network", fake_network_config)
    rejected = client.post(f"{project_url}/network-apply", data={"node_id": node_id, "password": "temporary"}, follow_redirects=True)
    assert b"confirm the network change" in rejected.data
    applied = client.post(f"{project_url}/network-apply", data={"node_id": node_id, "password": "temporary", "confirm": "y"})
    assert b"configured" in applied.data
    assert captured["expected_release"] == "9.8"
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


def test_remote_prechecks_run_from_gui_and_report_per_node(client, app, monkeypatch):
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
    mark_step_00_complete(app)
    assert b'aria-label="Remote ready"' in client.get("/projects").data
    page = client.get(project_url)
    assert b"Run on nodes" in page.data and b'id="precheck-run-dialog"' in page.data
    assert b'id="workflow-run-01" class="btn btn-success"' in page.data
    captured = {}
    def fake_run(node, password, script):
        captured.update(password=password, script=script)
        return SimpleNamespace(hostname=node.hostname, endpoint="192.168.124.11:22", ok=True, output="precheck complete", fingerprint="SHA256:test")
    monkeypatch.setattr("clusterweaver.web.routes.projects.run_remote_script", fake_run)
    response = client.post(f"{project_url}/run-prechecks", data={"password": "temporary-password"})
    assert response.status_code == 200
    assert b"Remote pre-checks" in response.data and b"precheck complete" in response.data
    assert b"temporary-password" not in response.data
    assert captured["password"] == "temporary-password"
    assert captured["script"].startswith("#!/bin/bash")
    project_page = client.get(project_url)
    assert b"Latest execution" in project_page.data
    assert b"node01" in project_page.data and b">PASS<" in project_page.data
    assert b'data-for-collapse="precheck-collapse"' in project_page.data
    monkeypatch.setattr("clusterweaver.web.routes.projects.run_remote_script", lambda node, password, script: SimpleNamespace(hostname=node.hostname, endpoint="test:22", ok=False, output="precheck failed"))
    client.post(f"{project_url}/run-prechecks", data={"password": "temporary-password"})
    failed_page = client.get(project_url)
    assert b'id="workflow-run-01" class="btn btn-danger"' in failed_page.data
    assert "Failed — run again".encode() in failed_page.data


def test_remote_network_check_is_available_from_gui(client, app, monkeypatch):
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
    mark_step_00_complete(app)
    page = client.get(project_url)
    assert b'id="network-check-run-dialog"' in page.data
    captured = {}
    def fake_run(node, password, script):
        captured.update(password=password, script=script)
        return SimpleNamespace(hostname=node.hostname, endpoint="192.168.124.11:22", ok=True, output="Network verification PASSED", fingerprint="SHA256:test")
    monkeypatch.setattr("clusterweaver.web.routes.projects.run_remote_script", fake_run)
    precheck = client.post(f"{project_url}/run-prechecks", data={"password": "temporary"})
    assert precheck.status_code == 200
    response = client.post(f"{project_url}/run-network-checks", data={"network-check-password": "temporary"})
    assert response.status_code == 200 and b"Network verification PASSED" in response.data
    assert "RHEL 10.2 network verification" in captured["script"]
    project_page = client.get(project_url)
    assert b'data-for-collapse="network-collapse"' in project_page.data
    assert b">PASS<" in project_page.data
    hosts = client.post(f"{project_url}/run-hosts-update", data={"hosts-update-password": "temporary", "hosts-update-confirm": "y"})
    assert hosts.status_code == 200
    assert b"Remote /etc/hosts update" in hosts.data
    project_page = client.get(project_url)
    assert b'data-for-collapse="hosts-collapse"' in project_page.data
    assert b'id="workflow-run-04" class="btn btn-success"' in project_page.data
    assert b'id="connectivity-run-dialog"' in project_page.data
    connectivity = client.post(f"{project_url}/run-network-connectivity", data={"connectivity-password": "temporary"})
    assert connectivity.status_code == 200
    assert b"Remote cluster network connectivity" in connectivity.data
    assert "EXPECTED_RELEASE=10.2" in captured["script"]
    project_page = client.get(project_url)
    assert b'data-for-collapse="connectivity-collapse"' in project_page.data
    assert b"Pre-Cluster Configuration" in project_page.data
    assert b"Cluster Base Installation and Configuration" in project_page.data
    assert b'id="workflow-run-05" class="btn btn-success"' in project_page.data
    assert b"5/5 complete" in project_page.data
    assert b'id="pre-cluster-workflow" class="collapse"' in project_page.data
    assert b'id="cluster-base-workflow" class="collapse show"' in project_page.data
    package_install = client.post(f"{project_url}/run-package-install", data={
        "package-install-password": "temporary", "package-install-confirm": "y",
    })
    assert package_install.status_code == 200
    assert b"Base cluster package installation" in package_install.data
    assert "INSTALLER=dnf" in captured["script"]
    assert 'rpm -q "${package}"' in captured["script"]
    project_page = client.get(project_url)
    assert b'id="workflow-run-06" class="btn btn-success"' in project_page.data
    assert b"1/3 complete" in project_page.data and b"2/3 remaining" in project_page.data
    pcsd = client.post(f"{project_url}/run-pcsd-auth", data={
        "pcsd-auth-password": "temporary", "pcsd-auth-confirm": "y",
    })
    assert pcsd.status_code == 200 and b"pcsd service and host authentication" in pcsd.data
    assert "systemctl enable --now pcsd.service" in captured["script"]
    assert "node01lanc" in captured["script"]
    project_page = client.get(project_url)
    assert b'id="workflow-run-07" class="btn btn-success"' in project_page.data
    cluster_setup = client.post(f"{project_url}/run-cluster-setup", data={
        "cluster-setup-password": "temporary", "cluster-setup-confirm": "y",
    })
    assert cluster_setup.status_code == 200 and b"Cluster creation and quorum configuration" in cluster_setup.data
    assert 'pcs cluster setup "${CLUSTER_NAME}" --start "${NODES[@]}"' in captured["script"]
    assert "pcs quorum update wait_for_all=1" in captured["script"]


def test_copy_script_has_http_fallback(client):
    response = client.get("/static/js/app.js")
    assert response.status_code == 200
    assert b'document.execCommand("copy")' in response.data
    assert b"window.isSecureContext" in response.data
