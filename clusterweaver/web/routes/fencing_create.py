from threading import Thread
from uuid import uuid4

from flask import Blueprint, abort, current_app, g, jsonify, render_template, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from clusterweaver.persistence import db
from clusterweaver.persistence.models import ClusterOperationRecord
from clusterweaver.core.services.fencing_create import ACTION, VERIFY_ACTION, creation_profiles, readiness, preview_command, run_creation
from clusterweaver.core.services.cluster_operations import serialize_job
from clusterweaver.web.forms.stonith import FencingCreateForm, FencingVerifyForm
from clusterweaver.web.routes.projects import project_or_404, repository, workflow_step_complete
from clusterweaver.web.routes.cluster_operations import release_stale_jobs
from clusterweaver.web.ssh_credentials import project_key_store, project_credentials
from clusterweaver.web.stonith_secrets import decrypt_password

fencing_create_bp = Blueprint('fencing_create',__name__)


def start_fencing_job(engine,job_id,project,credentials,profiles,options):
    Thread(target=run_creation,args=(engine,job_id,project,credentials,profiles,options),daemon=True,name='fencing-create-'+job_id).start()


def context(project, results):
    reasons = readiness(project,results,project_key_store(project).available())
    verify_reasons = list(reasons)
    if not workflow_step_complete(project,results,'08b'):
        verify_reasons.append('Step 08b must pass on every current node before configuration verification.')
    complete = int(workflow_step_complete(project,results,'08a') and workflow_step_complete(project,results,'08a-fa'))
    complete += sum(workflow_step_complete(project,results,step) for step in ('08b','08c'))
    return dict(fencing_create_ready=not reasons,fencing_create_reasons=reasons,fencing_verify_ready=not verify_reasons,fencing_verify_reasons=verify_reasons,stonith_complete=complete)


@fencing_create_bp.route('/projects/<int:project_id>/stonith/create',methods=['GET','POST'])
def create(project_id):
    project = project_or_404(project_id)
    if request.method == 'POST' and g.current_user.role not in {'administrator','clusteradmin'}:
        abort(403)
    form = FencingCreateForm()
    release_stale_jobs(project_id)
    results = repository().step_results(project_id)
    reasons = readiness(project,results,project_key_store(project).available())
    try:
        profiles = creation_profiles(project)
    except ValueError:
        profiles = []
    options = dict(power_wait=form.power_wait.data if form.power_wait.data is not None else 4,monitor=None,failure_timeout=form.failure_timeout.data,disabled=bool(form.disabled.data))
    if form.configure_monitor.data and form.monitor_interval.data and form.monitor_timeout.data:
        options['monitor'] = dict(interval=form.monitor_interval.data,timeout=form.monitor_timeout.data)
    if request.method == 'POST':
        # Preview is non-mutating and does not require confirmation.
        if form.preview.data:
            form.confirm.validators = []
        valid = form.validate_on_submit()
        if form.configure_monitor.data and options['monitor'] is None:
            form.monitor_interval.errors.append('Enter a monitor interval and timeout.')
            valid = False
        if form.create.data:
            if not valid:
                return jsonify(error='Review the fields and explicitly confirm creation.',fields=form.errors),400
            if reasons:
                return jsonify(error=' '.join(reasons)),409
            uncertain = db.session.scalar(select(ClusterOperationRecord).where(ClusterOperationRecord.project_id==project_id,ClusterOperationRecord.status=='unknown',ClusterOperationRecord.action.notin_(['status',VERIFY_ACTION])).order_by(ClusterOperationRecord.created_at.desc()).limit(1))
            if uncertain and not db.session.scalar(select(ClusterOperationRecord.id).where(ClusterOperationRecord.project_id==project_id,ClusterOperationRecord.action=='status',ClusterOperationRecord.status=='pass',ClusterOperationRecord.created_at>uncertain.created_at)):
                return jsonify(error='Refresh cluster status successfully after the preceding uncertain result before creating fencing devices.'),409
            config = repository().get_record(project_id).stonith_configuration
            stored = {p.node_id:p for p in config.profiles}
            try:
                profiles = [dict(p,password=decrypt_password(stored[p['node_id']].password_encrypted)) for p in profiles]
            except ValueError as exc:
                return jsonify(error=str(exc)),409
            if any(not p['password'] or any(c in p['password'] for c in '\r\n\x00') for p in profiles):
                return jsonify(error='Save every controller password in step 08a before creation.'),409
            job = ClusterOperationRecord(id=str(uuid4()),project_id=project_id,active_project_id=project_id,action=ACTION,target_node='',username=g.current_user.username,status='queued',phase='Queued',results=[])
            db.session.add(job)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                return jsonify(error='A cluster operation is already running. Wait for its result.'),409
            try:
                start_fencing_job(db.engine,job.id,project,project_credentials(project),profiles,options)
            except Exception:
                from clusterweaver.persistence.models import utcnow
                job.status,job.phase,job.active_project_id,job.finished_at = 'fail','Could not start worker; no command was sent',None,utcnow()
                db.session.commit()
                return jsonify(error=job.phase),503
            return jsonify(serialize_job(job)),202
    history = db.session.scalars(select(ClusterOperationRecord).where(ClusterOperationRecord.project_id==project_id,ClusterOperationRecord.action==ACTION).order_by(ClusterOperationRecord.created_at.desc()).limit(10)).all()
    response = current_app.make_response(render_template('projects/fencing_create.html',project=project,form=form,reasons=reasons,profiles=profiles,commands=[preview_command(p,options) for p in profiles],jobs=[serialize_job(job) for job in history]))
    response.headers['Cache-Control']='no-store'
    return response



def start_verification_job(engine,job_id,project,credentials,profiles):
    Thread(target=run_creation,args=(engine,job_id,project,credentials,profiles,{},True),daemon=True,name='fencing-verify-'+job_id).start()


@fencing_create_bp.route('/projects/<int:project_id>/stonith/verify',methods=['GET','POST'])
def verify(project_id):
    project = project_or_404(project_id)
    if request.method=='POST' and g.current_user.role not in {'administrator','clusteradmin'}:
        abort(403)
    form = FencingVerifyForm()
    release_stale_jobs(project_id)
    results = repository().step_results(project_id)
    reasons = context(project,results)['fencing_verify_reasons']
    try:
        profiles = creation_profiles(project)
    except ValueError:
        profiles = []
    if request.method=='POST':
        if not form.validate_on_submit():
            return jsonify(error='Invalid CSRF token.',fields=form.errors),400
        if reasons:
            return jsonify(error=' '.join(reasons)),409
        config = repository().get_record(project_id).stonith_configuration
        stored = {p.node_id:p for p in config.profiles}
        try:
            profiles = [dict(p,password=decrypt_password(stored[p['node_id']].password_encrypted)) for p in profiles]
        except ValueError as exc:
            return jsonify(error=str(exc)),409
        if any(not p['password'] for p in profiles):
            return jsonify(error='Save every controller password in step 08a before verification.'),409
        job = ClusterOperationRecord(id=str(uuid4()),project_id=project_id,active_project_id=project_id,action=VERIFY_ACTION,target_node='',username=g.current_user.username,status='queued',phase='Queued',results=[])
        db.session.add(job)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify(error='A cluster operation is already running. Wait for its result.'),409
        try:
            start_verification_job(db.engine,job.id,project,project_credentials(project),profiles)
        except Exception:
            from clusterweaver.persistence.models import utcnow
            job.status,job.phase,job.active_project_id,job.finished_at = 'fail','Could not start verification; no command was sent',None,utcnow()
            db.session.commit()
            return jsonify(error=job.phase),503
        return jsonify(serialize_job(job)),202
    jobs = db.session.scalars(select(ClusterOperationRecord).where(ClusterOperationRecord.project_id==project_id,ClusterOperationRecord.action==VERIFY_ACTION).order_by(ClusterOperationRecord.created_at.desc()).limit(10)).all()
    response = current_app.make_response(render_template('projects/fencing_verify.html',project=project,form=form,reasons=reasons,profiles=profiles,jobs=[serialize_job(job) for job in jobs]))
    response.headers['Cache-Control']='no-store'
    return response
