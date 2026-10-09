import ipaddress
from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for

from clusterweaver.core.services.project_ssh import install_project_key, verify_project_key, revoke_previous_key
from clusterweaver.persistence import db
from clusterweaver.web.ssh_credentials import project_key_store
from clusterweaver.web.forms.ssh_access import ProjectSSHAccessForm
from clusterweaver.web.routes.projects import project_or_404, repository

ssh_access_bp = Blueprint('ssh_access', __name__)


@ssh_access_bp.route('/projects/<int:project_id>/ssh-access', methods=['GET', 'POST'])
def manage(project_id):
    project = project_or_404(project_id)
    store = project_key_store(project)
    form = ProjectSSHAccessForm()
    if request.method == 'GET':
        form.source_ip.data = current_app.config.get('SSH_SOURCE_IP', '')
        for node in project.nodes:
            form.nodes.append_entry(dict(node_id=str(node.id), hostname=node.hostname))
    if request.method == 'POST' and g.current_user.role not in {'administrator', 'clusteradmin'}:
        abort(403)
    if form.validate_on_submit():
        ids = [entry.form.node_id.data for entry in form.nodes]
        expected = {str(node.id): node for node in project.nodes}
        valid = bool(expected) and len(ids) == len(expected) and set(ids) == set(expected)
        valid = valid and all(entry.form.hostname.data == expected[entry.form.node_id.data].hostname for entry in form.nodes)
        if not valid:
            flash('The node inventory changed or hostname case differs. Reload the form before managing SSH keys.', 'danger')
        elif any(not node.bootstrap_ip for node in project.nodes):
            flash('Configure an SSH IP for every node first.', 'danger')
        elif sum(bool(button.data) for button in (form.install, form.verify, form.rotate, form.cleanup)) != 1:
            flash('Select exactly one SSH key operation.', 'danger')
        elif not form.verify.data and not form.confirm.data:
            flash('Confirm the public-key changes before installation, rotation or revocation.', 'danger')
        else:
            try:
                if form.verify.data:
                    results = verify_project_key(store, project.nodes)
                elif form.cleanup.data:
                    if not store.previous.exists():
                        raise ValueError('There is no previous key to revoke.')
                    results = revoke_previous_key(store, project.nodes)
                else:
                    try:
                        source_ip = str(ipaddress.ip_address((form.source_ip.data or '').strip()))
                    except ValueError as exc:
                        raise ValueError('Enter the ClusterWeaver source IP as seen by the cluster nodes (including any NAT).') from exc
                    passwords = {int(entry.form.node_id.data): entry.form.password.data or form.password.data or '' for entry in form.nodes}
                    results = install_project_key(store, project.nodes, passwords, source_ip, rotate=bool(form.rotate.data))
                # Cleanup is distinct: it must not replace evidence of active key verification.
                step = '00kr' if form.cleanup.data else '00k'
                repository().save_step_results(project_id, step, results)
                db.session.commit()
                return render_template('projects/ssh_results.html', project=project, results=results,
                    title='ClusterWeaver project SSH key access', changed=not form.verify.data,
                    operation_description='Project key authentication as root on cluster nodes. Private keys remain on the ClusterWeaver server. Failed key authentication never falls back automatically to a password.')
            except (ValueError, OSError) as exc:
                flash(str(exc), 'danger')
    return render_template('projects/ssh_access.html', project=project, form=form, key_status=store.status(),
        results=repository().step_results(project_id).get('00k', []),
        cleanup_results=repository().step_results(project_id).get('00kr', []))
