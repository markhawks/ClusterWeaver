from datetime import datetime, timezone
from io import BytesIO

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, url_for
from sqlalchemy.exc import IntegrityError

from clusterweaver.core.generators import generate_hosts_update, generate_network_check, generate_network_connectivity, generate_precheck
from clusterweaver.core.services.projects import ProjectFileService
from clusterweaver.core.services.changelog import read_changelog
from clusterweaver.core.services.slugs import make_slug
from clusterweaver.core.services.ssh_bootstrap import bootstrap_peer_keys, discover_node, run_read_only_script
from clusterweaver.core.services.network_config import configure_node_network
from clusterweaver.core.validators import host_address, validate_rhel_release
from clusterweaver.persistence import db
from clusterweaver.persistence.repositories import ProjectRepository
from clusterweaver.web.forms import NetworkApplyForm, NetworkCheckRunForm, NodeForm, PrecheckRunForm, ProjectForm, SSHDiscoveryForm, SSHKeyBootstrapForm


projects_bp = Blueprint("projects", __name__)


def repository() -> ProjectRepository:
    return ProjectRepository(db.session)


def unique_slug(name: str, excluding_id: int | None = None) -> str:
    base = make_slug(name)
    candidate = base
    suffix = 2
    while repository().slug_exists(candidate, excluding_id):
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def project_or_404(project_id: int):
    project = repository().get(project_id)
    if project is None:
        abort(404)
    return project


def persist_files(project_id: int, message: str) -> bool:
    project = project_or_404(project_id)
    service = ProjectFileService(current_app.config["PROJECTS_ROOT"])
    _path, committed = service.save(project, message)
    return committed


def node_form_values(form: NodeForm) -> dict[str, str]:
    fields = ("hostname", "nodename", "fqdn", "site", "management_ip", "management_gateway", "cluster_ip", "cluster_gateway", "primary_interface", "secondary_interface", "bootstrap_ip")
    values = {field: (getattr(form, field).data or "").strip() for field in fields}
    values["ssh_port"] = form.ssh_port.data
    return values


def add_conflict_errors(form: NodeForm, project_id: int, excluding_id: int | None = None) -> bool:
    conflicts = repository().node_conflicts(project_id, node_form_values(form), excluding_id)
    for field, message in conflicts.items():
        getattr(form, field).errors.append(message)
    return bool(conflicts)


@projects_bp.get("/")
def index():
    return render_template("projects/index.html", projects=repository().list())


@projects_bp.get("/changelog")
def changelog():
    releases = read_changelog(current_app.config["CHANGELOG_PATH"])
    return render_template("changelog.html", releases=releases)


@projects_bp.route("/projects/new", methods=["GET", "POST"])
def create_project():
    form = ProjectForm()
    if form.validate_on_submit():
        validate_rhel_release(form.rhel_major.data, form.rhel_minor.data)
        record = repository().add_project(
            name=form.name.data.strip(),
            slug=unique_slug(form.name.data),
            customer=form.customer.data.strip(),
            description=form.description.data.strip() if form.description.data else "",
            rhel_major=form.rhel_major.data,
            rhel_minor=form.rhel_minor.data.strip() if form.rhel_minor.data else "",
            platform_type=form.platform_type.data,
            hypervisor=form.hypervisor.data if form.platform_type.data == "virtual" else "",
            node_count=form.node_count.data,
        )
        db.session.commit()
        persist_files(record.id, f"Create {record.name} project")
        flash("Project created.", "success")
        return redirect(url_for("projects.detail", project_id=record.id))
    return render_template("projects/form.html", form=form, title="New project")


@projects_bp.get("/projects/<int:project_id>")
def detail(project_id: int):
    project = project_or_404(project_id)
    network_form = NetworkApplyForm()
    network_form.node_id.choices = [(node.id, f"{node.hostname} · {node.bootstrap_ip or 'no bootstrap IP'}") for node in project.nodes]
    return render_template("projects/detail.html", project=project, script=generate_precheck(project), network_script=generate_network_check(project), hosts_script=generate_hosts_update(project), connectivity_script=generate_network_connectivity(project), discovery_form=SSHDiscoveryForm(), key_form=SSHKeyBootstrapForm(), network_form=network_form, precheck_form=PrecheckRunForm(), network_check_form=NetworkCheckRunForm(prefix="network-check"), ssh_password_configured=bool(current_app.config["SSH_BOOTSTRAP_PASSWORD"]))


@projects_bp.post("/projects/<int:project_id>/run-prechecks")
def run_prechecks(project_id: int):
    project = project_or_404(project_id)
    form = PrecheckRunForm()
    password = form.password.data or current_app.config["SSH_BOOTSTRAP_PASSWORD"]
    if not form.validate_on_submit() or not password:
        flash("Enter the root password to run remote pre-checks.", "danger")
        return redirect(url_for("projects.detail", project_id=project_id))
    if not project.nodes or any(not node.bootstrap_ip for node in project.nodes):
        flash("Configure an SSH bootstrap IP on every node before running pre-checks.", "danger")
        return redirect(url_for("projects.detail", project_id=project_id))
    script = generate_precheck(project)
    results = [run_read_only_script(node, password, script) for node in project.nodes]
    return render_template("projects/ssh_results.html", project=project, results=results, title="Remote pre-checks", changed=False)


@projects_bp.post("/projects/<int:project_id>/run-network-checks")
def run_network_checks(project_id: int):
    project = project_or_404(project_id)
    form = NetworkCheckRunForm(prefix="network-check")
    password = form.password.data or current_app.config["SSH_BOOTSTRAP_PASSWORD"]
    if not form.validate_on_submit() or not password:
        flash("Enter the root password to run remote network verification.", "danger")
        return redirect(url_for("projects.detail", project_id=project_id))
    if not project.nodes or any(not node.bootstrap_ip for node in project.nodes):
        flash("Configure an SSH bootstrap IP on every node before running network verification.", "danger")
        return redirect(url_for("projects.detail", project_id=project_id))
    script = generate_network_check(project)
    results = [run_read_only_script(node, password, script) for node in project.nodes]
    return render_template("projects/ssh_results.html", project=project, results=results, title="Remote network verification", changed=False)


@projects_bp.post("/projects/<int:project_id>/ssh-discovery")
def ssh_discovery(project_id: int):
    project = project_or_404(project_id)
    form = SSHDiscoveryForm()
    password = form.password.data or current_app.config["SSH_BOOTSTRAP_PASSWORD"]
    if not form.validate_on_submit() or not password:
        flash("Enter the initial root password to run discovery.", "danger")
        return redirect(url_for("projects.detail", project_id=project_id))
    results = [discover_node(node, password) for node in project.nodes]
    return render_template("projects/ssh_results.html", project=project, results=results, title="SSH discovery", changed=False)


@projects_bp.post("/projects/<int:project_id>/ssh-key-bootstrap")
def ssh_key_bootstrap(project_id: int):
    project = project_or_404(project_id)
    form = SSHKeyBootstrapForm()
    password = form.password.data or current_app.config["SSH_BOOTSTRAP_PASSWORD"]
    if not form.validate_on_submit() or not password:
        flash("Password and explicit confirmation are required to create peer SSH trust.", "danger")
        return redirect(url_for("projects.detail", project_id=project_id))
    if len(project.nodes) < 2:
        flash("At least two nodes are required to create peer SSH trust.", "danger")
        return redirect(url_for("projects.detail", project_id=project_id))
    results = bootstrap_peer_keys(project.nodes, password)
    return render_template("projects/ssh_results.html", project=project, results=results, title="SSH key bootstrap", changed=True)


@projects_bp.post("/projects/<int:project_id>/network-apply")
def network_apply(project_id: int):
    record = repository().get_record(project_id)
    if record is None:
        abort(404)
    form = NetworkApplyForm()
    form.node_id.choices = [(node.id, node.hostname) for node in record.nodes]
    password = form.password.data or current_app.config["SSH_BOOTSTRAP_PASSWORD"]
    if not form.validate_on_submit() or not password:
        flash("Select a node, provide credentials, and confirm the network change.", "danger")
        return redirect(url_for("projects.detail", project_id=project_id))
    if record.rhel_major != 10 or record.rhel_minor != "2":
        flash("Automated network configuration is currently limited to RHEL 10.2.", "danger")
        return redirect(url_for("projects.detail", project_id=project_id))
    node_record = next((node for node in record.nodes if node.id == form.node_id.data), None)
    if node_record is None:
        abort(404)
    project = project_or_404(project_id)
    node = next(item for item in project.nodes if item.id == node_record.id)
    result = configure_node_network(node, password)
    if result.ok:
        node_record.bootstrap_ip = host_address(node_record.management_ip)
        record.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        persist_files(record.id, f"Apply network configuration to {node_record.hostname} in {record.name}")
        project = project_or_404(project_id)
    return render_template("projects/ssh_results.html", project=project, results=[result], title="Network configuration", changed=True)


@projects_bp.route("/projects/<int:project_id>/edit", methods=["GET", "POST"])
def edit_project(project_id: int):
    record = repository().get_record(project_id)
    if record is None:
        abort(404)
    form = ProjectForm(obj=record)
    if form.validate_on_submit():
        validate_rhel_release(form.rhel_major.data, form.rhel_minor.data)
        record.name = form.name.data.strip()
        record.customer = form.customer.data.strip()
        record.description = form.description.data.strip() if form.description.data else ""
        record.rhel_major = form.rhel_major.data
        record.rhel_minor = form.rhel_minor.data.strip() if form.rhel_minor.data else ""
        record.platform_type = form.platform_type.data
        record.hypervisor = form.hypervisor.data if form.platform_type.data == "virtual" else ""
        record.node_count = form.node_count.data
        record.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        committed = persist_files(record.id, f"Update {record.name} project")
        flash("Project updated." + (" Git history updated." if committed else ""), "success")
        return redirect(url_for("projects.detail", project_id=record.id))
    return render_template("projects/form.html", form=form, title="Edit project")


@projects_bp.route("/projects/<int:project_id>/nodes/new", methods=["GET", "POST"])
def create_node(project_id: int):
    record = repository().get_record(project_id)
    if record is None:
        abort(404)
    form = NodeForm()
    if request.method == "GET" and record.rhel_major == 10 and record.platform_type == "virtual" and record.hypervisor == "kvm":
        suggested_host = 11 + len(record.nodes)
        if suggested_host <= 254:
            form.management_ip.data = f"192.168.124.{suggested_host}/24"
            form.cluster_ip.data = f"192.168.200.{suggested_host}/24"
        form.management_gateway.data = "192.168.124.1"
        form.primary_interface.data = "enp1s0"
        form.secondary_interface.data = "enp7s0"
    if form.validate_on_submit():
        if add_conflict_errors(form, project_id):
            return render_template("nodes/form.html", form=form, project=record, title="Add node", interface_names=repository().interface_names())
        try:
            repository().add_node(record, **node_form_values(form))
            record.updated_at = datetime.now(timezone.utc)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            form.hostname.errors.append("This hostname already exists in the project.")
        else:
            persist_files(record.id, f"Add node {form.hostname.data.strip()} to {record.name}")
            flash("Node added.", "success")
            return redirect(url_for("projects.detail", project_id=record.id))
    return render_template("nodes/form.html", form=form, project=record, title="Add node", interface_names=repository().interface_names())


@projects_bp.route("/projects/<int:project_id>/nodes/<int:node_id>/clone", methods=["GET", "POST"])
def clone_node(project_id: int, node_id: int):
    record = repository().get_record(project_id)
    if record is None:
        abort(404)
    source = next((item for item in record.nodes if item.id == node_id), None)
    if source is None:
        abort(404)
    form = NodeForm(obj=source)
    if form.validate_on_submit() and not add_conflict_errors(form, project_id):
        clone = repository().add_node(record, **node_form_values(form))
        record.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        persist_files(record.id, f"Clone node {source.hostname} as {clone.hostname} in {record.name}")
        flash("Node cloned.", "success")
        return redirect(url_for("projects.detail", project_id=record.id))
    return render_template("nodes/form.html", form=form, project=record, title=f"Clone node {source.hostname}", interface_names=repository().interface_names())


@projects_bp.route("/projects/<int:project_id>/nodes/<int:node_id>/edit", methods=["GET", "POST"])
def edit_node(project_id: int, node_id: int):
    record = repository().get_record(project_id)
    if record is None:
        abort(404)
    node = next((item for item in record.nodes if item.id == node_id), None)
    if node is None:
        abort(404)
    form = NodeForm(obj=node)
    if form.validate_on_submit():
        if add_conflict_errors(form, project_id, node.id):
            return render_template("nodes/form.html", form=form, project=record, title="Edit node", interface_names=repository().interface_names())
        node.hostname = form.hostname.data.strip()
        node.nodename = form.nodename.data.strip()
        node.fqdn = form.fqdn.data.strip() if form.fqdn.data else ""
        node.site = form.site.data.strip() if form.site.data else ""
        node.management_ip = form.management_ip.data.strip() if form.management_ip.data else ""
        node.management_gateway = form.management_gateway.data.strip() if form.management_gateway.data else ""
        node.cluster_ip = form.cluster_ip.data.strip() if form.cluster_ip.data else ""
        node.cluster_gateway = form.cluster_gateway.data.strip() if form.cluster_gateway.data else ""
        node.primary_interface = form.primary_interface.data.strip() if form.primary_interface.data else ""
        node.secondary_interface = form.secondary_interface.data.strip() if form.secondary_interface.data else ""
        node.bootstrap_ip = form.bootstrap_ip.data.strip() if form.bootstrap_ip.data else ""
        node.ssh_port = form.ssh_port.data
        record.updated_at = datetime.now(timezone.utc)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            form.hostname.errors.append("This hostname already exists in the project.")
        else:
            persist_files(record.id, f"Update node {node.hostname} in {record.name}")
            flash("Node updated.", "success")
            return redirect(url_for("projects.detail", project_id=record.id))
    return render_template("nodes/form.html", form=form, project=record, title="Edit node", interface_names=repository().interface_names())


@projects_bp.get("/projects/<int:project_id>/precheck.sh")
def download_precheck(project_id: int):
    project = project_or_404(project_id)
    content = generate_precheck(project).encode("utf-8")
    return send_file(
        BytesIO(content), mimetype="text/x-shellscript", as_attachment=True, download_name="01-prechecks.sh"
    )


@projects_bp.get("/projects/<int:project_id>/network-check.sh")
def download_network_check(project_id: int):
    project = project_or_404(project_id)
    content = generate_network_check(project).encode("utf-8")
    return send_file(BytesIO(content), mimetype="text/x-shellscript", as_attachment=True, download_name="02-network-check.sh")


@projects_bp.get("/projects/<int:project_id>/hosts-update.sh")
def download_hosts_update(project_id: int):
    project = project_or_404(project_id)
    content = generate_hosts_update(project).encode("utf-8")
    return send_file(BytesIO(content), mimetype="text/x-shellscript", as_attachment=True, download_name="03-hosts-update.sh")


@projects_bp.get("/projects/<int:project_id>/network-connectivity.sh")
def download_network_connectivity(project_id: int):
    project = project_or_404(project_id)
    content = generate_network_connectivity(project).encode("utf-8")
    return send_file(BytesIO(content), mimetype="text/x-shellscript", as_attachment=True, download_name="04-network-connectivity.sh")
