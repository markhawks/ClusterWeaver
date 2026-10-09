from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for
from sqlalchemy import delete

from clusterweaver.core.services.stonith import generate_oem_verification_script, verify_oem_profiles, generate_ipmi_verification_script, verify_ipmi_profiles
from clusterweaver.core.services.dell_ipmi import validate_ipmi_definition
from clusterweaver.core.services.fence_agents import check_cluster_agents, generate_agent_check_script, INSTALL_ALL_COMMAND
from clusterweaver.persistence import db
from clusterweaver.persistence.models import StonithConfigurationRecord, StonithProfileRecord, StepExecutionRecord, utcnow
from clusterweaver.web.ssh_credentials import project_credentials
from clusterweaver.web.forms.stonith import StonithProfilesForm, FenceAgentsCheckForm
from clusterweaver.web.routes.projects import persist_files, project_or_404, repository


stonith_bp = Blueprint("stonith", __name__)


def definitions(configuration):
    if configuration is None:
        return []
    return [dict(hostname=profile.node.hostname, profile_name=profile.profile_name, username=profile.username, controller_endpoint=profile.controller_endpoint, resource_name=profile.resource_name)
            for profile in sorted(configuration.profiles, key=lambda item: item.node.hostname.lower())]


@stonith_bp.route("/projects/<int:project_id>/stonith/profiles", methods=["GET", "POST"])
def profiles(project_id):
    project = project_or_404(project_id)
    record = repository().get_record(project_id)
    configuration = record.stonith_configuration
    form = StonithProfilesForm()
    if request.method == "GET":
        form.mode.data = configuration.mode if configuration else "oem"
        form.endpoint.data = configuration.endpoint if configuration else ""
        saved = {profile.node_id: profile for profile in configuration.profiles} if configuration else {}
        for node in project.nodes:
            profile = saved.get(node.id)
            form.profiles.append_entry(dict(node_id=str(node.id), hostname=node.hostname,
                profile_name=profile.profile_name if profile else "", username=profile.username if profile else "",
                controller_endpoint=profile.controller_endpoint if profile else "", resource_name=profile.resource_name if profile else ""))
    if request.method == "POST" and g.current_user.role not in {"administrator", "clusteradmin"}:
        abort(403)
    if form.validate_on_submit():
        nodes = {str(node.id): node for node in project.nodes}
        posted_ids = [entry.form.node_id.data for entry in form.profiles]
        valid = bool(nodes) and len(posted_ids) == len(nodes) and set(posted_ids) == set(nodes)
        if not valid:
            flash("Provide exactly one DELL profile for every current project node. Reload the form if the inventory changed.", "danger")
        ipmi = form.mode.data == "ipmi"
        seen_profiles = set()
        controllers = set()
        for entry in form.profiles:
            node = nodes.get(entry.form.node_id.data)
            if node is None:
                valid = False
                continue
            if entry.form.hostname.data != node.hostname:
                entry.form.hostname.errors.append(f"Hostname must match the project exactly: {node.hostname} (including uppercase/lowercase).")
                valid = False
            name = (entry.form.resource_name.data or "").strip() if ipmi else (entry.form.profile_name.data or "").strip()
            if ipmi:
                controller = (entry.form.controller_endpoint.data or "").strip()
                try:
                    validate_ipmi_definition(controller, name)
                except ValueError as exc:
                    entry.form.controller_endpoint.errors.append(str(exc))
                    valid = False
                if controller.casefold() in controllers:
                    entry.form.controller_endpoint.errors.append("Use a different iDRAC endpoint for each node.")
                    valid = False
                controllers.add(controller.casefold())
            username = entry.form.username.data.strip()
            if not name or name.casefold() in seen_profiles:
                (entry.form.resource_name if ipmi else entry.form.profile_name).errors.append("Enter a unique DELL profile or STONITH resource name for each node.")
                valid = False
            seen_profiles.add(name.casefold())
            if not username or ":" in username:
                entry.form.username.errors.append("Enter a userid without ':'.")
                valid = False
            if ipmi and any(c in (entry.form.password.data or "") + username for c in "\r\n\x00"):
                entry.form.password.errors.append("Credentials cannot contain newlines or NUL characters.")
                valid = False
            if form.verify.data and not entry.form.password.data:
                entry.form.password.errors.append("Enter the iDRAC password to verify this node." if ipmi else "Enter the OEM password to verify this profile.")
                valid = False
        if valid:
            if configuration is None:
                configuration = StonithConfigurationRecord(project=record, hardware="dell", endpoint=(form.endpoint.data or "").strip())
                db.session.add(configuration)
            endpoint = "" if ipmi else (form.endpoint.data or "").strip()
            changed = configuration.endpoint != endpoint or configuration.mode != form.mode.data
            configuration.mode = form.mode.data
            configuration.endpoint = endpoint
            configuration.hardware = form.hardware.data
            existing = {profile.node_id: profile for profile in configuration.profiles}
            for entry in form.profiles:
                values = entry.form
                node_id = int(values.node_id.data)
                profile = existing.get(node_id)
                name, username = (values.profile_name.data or "").strip() if not ipmi else "", values.username.data.strip()
                controller = (values.controller_endpoint.data or "").strip() if ipmi else ""
                resource = (values.resource_name.data or "").strip() if ipmi else ""
                if profile is None:
                    profile = StonithProfileRecord(configuration=configuration, node_id=node_id, profile_name=name, username=username)
                    db.session.add(profile)
                    changed = True
                changed = changed or profile.profile_name != name or profile.username != username
                changed = changed or profile.controller_endpoint != controller or profile.resource_name != resource
                profile.controller_endpoint, profile.resource_name = controller, resource
                profile.profile_name, profile.username = name, username
            if changed:
                db.session.execute(delete(StepExecutionRecord).where(StepExecutionRecord.project_id == project_id, StepExecutionRecord.step.in_(["08a", "08a-fa"])))
            record.updated_at = utcnow()
            db.session.commit()
            persist_files(project_id, f"Define DELL STONITH profiles for {record.name}")
            if form.verify.data:
                inputs = [dict(hostname=entry.form.hostname.data, profile_name=(entry.form.profile_name.data or "").strip(),
                               controller_endpoint=(entry.form.controller_endpoint.data or "").strip(), resource_name=(entry.form.resource_name.data or "").strip(),
                               username=entry.form.username.data.strip(), password=entry.form.password.data)
                          for entry in form.profiles]
                results = verify_ipmi_profiles(inputs) if ipmi else verify_oem_profiles(configuration.endpoint, inputs, current_app.config.get("OEM_CA_FILE") or None)
                repository().save_step_results(project_id, "08a", results)
                db.session.commit()
                return render_template("projects/ssh_results.html", project=project_or_404(project_id), results=results,
                    title="08a · DELL iDRAC IPMI verification" if ipmi else "08a · DELL OEM profile verification", changed=False,
                    operation_description="Read-only IPMI status from the ClusterWeaver server; no power action or resource creation." if ipmi else "Read-only HTTPS checks from the ClusterWeaver server. No fencing resource was created and no power action was performed.")
            flash("DELL iDRAC profiles saved. Passwords were not stored." if ipmi else "DELL OEM profiles saved. Passwords were not stored.", "success")
            return redirect(url_for("projects.detail", project_id=project_id))
    saved_definitions = definitions(configuration)
    return render_template("projects/stonith_profiles.html", project=project, form=form,
        verification_script=(generate_ipmi_verification_script(saved_definitions) if configuration.mode == "ipmi" else generate_oem_verification_script(configuration.endpoint, saved_definitions)) if configuration else "",
        results=repository().step_results(project_id).get("08a", []),
        agents_form=FenceAgentsCheckForm(prefix="agents"),
        agent_results=repository().step_results(project_id).get("08a-fa", []),
        agent_script=generate_agent_check_script(configuration.mode) if configuration else "",
        install_all_command=INSTALL_ALL_COMMAND)


@stonith_bp.post("/projects/<int:project_id>/stonith/check-agents")
def check_agents(project_id):
    project = project_or_404(project_id)
    if g.current_user.role not in {"administrator", "clusteradmin"}:
        abort(403)
    configuration = repository().get_record(project_id).stonith_configuration
    form = FenceAgentsCheckForm(prefix="agents")
    password = project_credentials(project, form.password.data or "")
    if not form.validate_on_submit() or not password:
        flash("Enter the root SSH password to check agents on cluster nodes.", "danger")
        return redirect(url_for("stonith.profiles", project_id=project_id))
    if configuration is None:
        flash("Save the STONITH profiles before checking node agents.", "danger")
        return redirect(url_for("stonith.profiles", project_id=project_id))
    if not project.nodes or any(not node.bootstrap_ip for node in project.nodes):
        flash("Configure an SSH bootstrap IP for every cluster node before checking agents.", "danger")
        return redirect(url_for("stonith.profiles", project_id=project_id))
    results = check_cluster_agents(project.nodes, password, configuration.mode)
    repository().save_step_results(project_id, "08a-fa", results)
    db.session.commit()
    return render_template("projects/ssh_results.html", project=project_or_404(project_id), results=results,
        title="08a · Cluster-node fence-agent verification", changed=False,
        operation_description="Read-only SSH checks on each cluster node: installed packages and fence_* executables; IPMI mode also reads fence_ipmilan metadata. Missing agents produce an installation command; no package is installed automatically.")
