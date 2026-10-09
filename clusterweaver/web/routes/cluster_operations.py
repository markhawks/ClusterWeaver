from datetime import timezone
from threading import Thread
from uuid import uuid4

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from clusterweaver.persistence import db
from clusterweaver.persistence.models import ClusterOperationRecord, utcnow
from clusterweaver.core.services.cluster_operations import ACTIONS, STALE_AFTER, expected_nodes, generate_operation_script, run_operation, serialize_job
from clusterweaver.core.services.ssh_credentials import SSHCredentials
from clusterweaver.web.forms.cluster_operations import ClusterOperationForm
from clusterweaver.web.ssh_credentials import project_key_store
from clusterweaver.web.routes.projects import project_or_404, repository, workflow_step_complete

cluster_operations_bp = Blueprint('cluster_operations', __name__)


def release_stale_jobs(project_id):
    records = db.session.scalars(select(ClusterOperationRecord).where(ClusterOperationRecord.active_project_id == project_id)).all()
    now = utcnow()
    for job in records:
        created = job.created_at.replace(tzinfo=timezone.utc) if job.created_at.tzinfo is None else job.created_at
        if (now - created).total_seconds() > STALE_AFTER:
            job.status, job.phase, job.active_project_id = 'unknown', 'Worker interrupted or deadline exceeded; refresh status before another action', None
            job.finished_at = now
    if records:
        db.session.commit()


def operation_context(project, workflow_results):
    release_stale_jobs(project.id)
    store = project_key_store(project)
    ready = store.available() and workflow_step_complete(project, workflow_results, '00k')
    history = db.session.scalars(select(ClusterOperationRecord).where(ClusterOperationRecord.project_id == project.id).order_by(ClusterOperationRecord.created_at.desc()).limit(10)).all()
    scripts = {'status': generate_operation_script(project, 'status')}
    try:
        expected_nodes(project)
        for action in ('start', 'stop', 'enable', 'disable'):
            scripts[action] = generate_operation_script(project, action)
        for action in ('standby', 'unstandby'):
            for node in project.nodes:
                scripts[action + ':' + str(node.id)] = generate_operation_script(project, action, node.nodename)
    except ValueError:
        ready = False
    ready = ready and all(node.bootstrap_ip for node in project.nodes)
    return dict(operations_ready=ready, operation_history=[serialize_job(job) for job in history], operation_form=ClusterOperationForm(), operation_actions=ACTIONS, operation_scripts=scripts)


def start_background_job(engine, job_id, project, credentials, action, target):
    Thread(target=run_operation, args=(engine, job_id, project, credentials, action, target), daemon=True,
           name='cluster-operation-' + job_id).start()


@cluster_operations_bp.post('/projects/<int:project_id>/operations')
def start(project_id):
    project = project_or_404(project_id)
    form = ClusterOperationForm()
    if not form.validate_on_submit():
        return jsonify(error='Invalid operation or CSRF token.', fields=form.errors), 400
    action = form.action.data
    if action != 'status' and g.current_user.role not in {'administrator', 'clusteradmin'}:
        abort(403)
    if action != 'status' and not form.confirm.data:
        return jsonify(error='Confirm the operation after reviewing the cluster, nodes and consequence.'), 400
    store = project_key_store(project)
    if not store.available() or not workflow_step_complete(project, repository().step_results(project_id), '00k'):
        return jsonify(error='Install the project SSH key and verify key-only access on every node in step 00 first.'), 409
    try:
        expected_nodes(project)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    if any(not node.bootstrap_ip for node in project.nodes):
        return jsonify(error='Every cluster node needs a configured SSH IP.'), 400
    target = ''
    if action in {'standby', 'unstandby'}:
        try:
            node_id = int(form.node_id.data or '')
        except ValueError:
            return jsonify(error='Select a configured node.'), 400
        node = next((node for node in project.nodes if node.id == node_id), None)
        if node is None:
            return jsonify(error='The selected node does not belong to this project.'), 400
        target = node.nodename
    elif form.node_id.data:
        return jsonify(error='Cluster-wide operations do not accept a node target.'), 400
    release_stale_jobs(project_id)
    # After an uncertain mutation a fresh read-only status job is required.
    uncertain = db.session.scalar(select(ClusterOperationRecord).where(
        ClusterOperationRecord.project_id == project_id, ClusterOperationRecord.action != 'status',
        ClusterOperationRecord.status == 'unknown').order_by(ClusterOperationRecord.created_at.desc()).limit(1))
    if action != 'status' and uncertain is not None:
        refreshed = db.session.scalar(select(ClusterOperationRecord.id).where(
            ClusterOperationRecord.project_id == project_id, ClusterOperationRecord.action == 'status',
            ClusterOperationRecord.status == 'pass', ClusterOperationRecord.created_at > uncertain.created_at).limit(1))
        if refreshed is None:
            return jsonify(error='The preceding result is uncertain. Successfully refresh cluster status before another modifying command.'), 409
    job = ClusterOperationRecord(id=str(uuid4()), project_id=project_id, active_project_id=project_id,
        action=action, target_node=target, username=g.current_user.username, status='queued', phase='Queued', results=[])
    db.session.add(job)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error='An operation is already running for this project. Wait for its result.'), 409
    credentials = SSHCredentials(private_key=store.private, known_hosts=store.known_hosts)
    try:
        start_background_job(db.engine, job.id, project, credentials, action, target)
    except Exception:
        job.status, job.phase, job.active_project_id = 'fail', 'Could not start the background worker; no command was sent', None
        job.finished_at = utcnow()
        db.session.commit()
        return jsonify(error=job.phase), 503
    return jsonify(serialize_job(job)), 202


@cluster_operations_bp.get('/projects/<int:project_id>/operations')
def history(project_id):
    project_or_404(project_id)
    release_stale_jobs(project_id)
    # Background writes use independent sessions; refresh the request identity map.
    db.session.expire_all()
    records = db.session.scalars(select(ClusterOperationRecord).where(ClusterOperationRecord.project_id == project_id).order_by(ClusterOperationRecord.created_at.desc()).limit(10)).all()
    response = jsonify(jobs=[serialize_job(job) for job in records])
    response.headers['Cache-Control'] = 'no-store'
    return response


def protect_running_operation():
    # Avoid changing the plan or running a legacy mutation while a job is active.
    if request.method != 'POST' or request.endpoint in {'cluster_operations.start', 'settings.change_theme', 'settings.change_password', 'auth.logout'}:
        return None
    project_id = (request.view_args or {}).get('project_id')
    if project_id is None:
        return None
    protected = {'projects.edit_project', 'projects.delete_project', 'projects.create_node', 'projects.clone_node', 'projects.edit_node',
        'projects.run_hosts_update', 'projects.run_package_install', 'projects.run_pcsd_auth', 'projects.run_cluster_setup',
        'projects.ssh_key_bootstrap', 'projects.network_apply', 'ssh_access.manage'}
    if request.endpoint not in protected:
        return None
    active = db.session.scalar(select(ClusterOperationRecord.id).where(ClusterOperationRecord.active_project_id == project_id).limit(1))
    if active is not None:
        abort(409, description='A cluster operation is running. Wait for its result before changing configuration, keys or running another modifying workflow.')
    return None
