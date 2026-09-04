from datetime import datetime, timezone
from io import BytesIO

from flask import Blueprint, abort, current_app, flash, redirect, render_template, send_file, url_for
from sqlalchemy.exc import IntegrityError

from clusterweaver.core.generators import generate_network_check, generate_precheck
from clusterweaver.core.services.projects import ProjectFileService
from clusterweaver.core.services.changelog import read_changelog
from clusterweaver.core.services.slugs import make_slug
from clusterweaver.core.validators import validate_rhel_release
from clusterweaver.persistence import db
from clusterweaver.persistence.repositories import ProjectRepository
from clusterweaver.web.forms import NodeForm, ProjectForm


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
    fields = ("hostname", "nodename", "fqdn", "site", "management_ip", "cluster_ip", "primary_interface", "secondary_interface")
    return {field: (getattr(form, field).data or "").strip() for field in fields}


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
    return render_template("projects/detail.html", project=project, script=generate_precheck(project), network_script=generate_network_check(project))


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
        node.cluster_ip = form.cluster_ip.data.strip() if form.cluster_ip.data else ""
        node.primary_interface = form.primary_interface.data.strip() if form.primary_interface.data else ""
        node.secondary_interface = form.secondary_interface.data.strip() if form.secondary_interface.data else ""
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
