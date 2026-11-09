import json
from io import StringIO
from types import SimpleNamespace
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session

from clusterweaver.core.services import fencing_create as service
from clusterweaver.core.services.fencing_device import create_devices, verify_devices
from clusterweaver.persistence import db
from clusterweaver.persistence.models import ClusterOperationRecord, StepExecutionRecord, UserRecord
from test_fencing_create import payload, FakePCS, fencing_ready, _worker_setup
from test_cluster_operations import ready_project
from test_stonith import stonith_project


class ReadOnlyPCS:
    def __init__(self,payload):
        self.payload=payload
        self.pcs=FakePCS(payload)
        create_devices(payload,self.pcs)
        self.calls=[]
        self.quorum=True
        self.blocked=set()
    def __call__(self,args):
        self.calls.append(args)
        if args==['pcs','cluster','cib']:
            return ET.tostring(self.pcs.root,encoding='unicode')
        if args==['pcs','status','--full']:
            return 'Cluster name: '+self.payload['cluster_name']
        assert args==['crm_mon','--one-shot','--as-xml'], 'Verification must only read cluster state'
        runtime=ET.fromstring('<crm_mon><summary/><nodes/><resources/></crm_mon>')
        ET.SubElement(runtime.find('summary'),'current_dc',present='true',with_quorum=str(self.quorum).lower())
        for name in self.payload['nodes']:
            ET.SubElement(runtime.find('nodes'),'node',name=name,online='true')
        for profile in self.payload['profiles']:
            resource=profile['resource_name']
            ET.SubElement(runtime.find('resources'),'resource',id=resource,role='Started',active='true',blocked=str(resource in self.blocked).lower(),managed='true',failed='false')
        return ET.tostring(runtime,encoding='unicode')


def test_verification_reads_actual_operations_and_never_changes_cib_or_returns_passwords(payload):
    pcs=ReadOnlyPCS(payload)
    before=ET.tostring(pcs.pcs.root)
    report=verify_devices(payload,pcs)
    assert report['status']=='pass'
    assert all(r['enabled'] and r['power_wait']==4 for r in report['resources'])
    assert all(r['operations'][0]['interval']=='60s' for r in report['resources'])
    assert all(p['password'] not in json.dumps(report) for p in payload['profiles'])
    assert ET.tostring(pcs.pcs.root)==before
    assert len(pcs.calls)==3


def test_verification_reports_disabled_blocked_and_failcounts_without_cleanup(payload):
    pcs=ReadOnlyPCS(payload)
    primitive=pcs.pcs.root.find('./configuration/resources/primitive')
    meta=ET.SubElement(primitive,'meta_attributes')
    ET.SubElement(meta,'nvpair',name='target-role',value='Stopped')
    node=ET.SubElement(ET.SubElement(pcs.pcs.root,'status'),'node_state',uname='node91lanc')
    attrs=ET.SubElement(ET.SubElement(node,'transient_attributes'),'instance_attributes')
    ET.SubElement(attrs,'nvpair',name='fail-count-STONITH-90#monitor_60000',value='INFINITY')
    pcs.blocked.add('STONITH-90')
    before=ET.tostring(pcs.pcs.root)
    report=verify_devices(payload,pcs)
    assert report['status']=='fail'
    first,second=report['resources']
    assert first['status']=='fail' and second['status']=='pass'
    assert not first['enabled'] and first['failcounts'][0]['value']=='INFINITY'
    assert any('disabled' in error for error in first['errors'])
    assert any('blocked' in error for error in first['errors'])
    assert ET.tostring(pcs.pcs.root)==before


def test_verification_rejects_mapping_and_credentials_conflicts_and_reports_monitor_warning(payload):
    pcs=ReadOnlyPCS(payload)
    primitive=pcs.pcs.root.find('./configuration/resources/primitive')
    primitive.find('./instance_attributes/nvpair[@name="passwd"]').set('value','different-secret')
    report=verify_devices(payload,pcs)
    assert report['status']=='fail' and any('passwd' in error for error in report['resources'][0]['errors'])
    assert 'different-secret' not in json.dumps(report)
    pcs=ReadOnlyPCS(payload)
    primitive=pcs.pcs.root.find('./configuration/resources/primitive')
    primitive.remove(primitive.find('operations'))
    report=verify_devices(payload,pcs)
    assert report['status']=='pass' and report['resources'][0]['warnings']
    pcs.quorum=False
    assert verify_devices(payload,pcs)['status']=='fail'


def _mark_creation_passed(project):
    for node in project.nodes:
        db.session.add(StepExecutionRecord(project_id=project.id,node_id=node.id,step='08b',status='pass',output='created'))
    db.session.commit()


def test_verify_api_gating_graphics_reservation_and_no_secrets(client,app,fencing_ready,monkeypatch):
    project=fencing_ready
    url=f'/projects/{project.id}/stonith/verify'
    assert client.post(url,data={'verify':'y'}).status_code==409
    _mark_creation_passed(project)
    detail=client.get(f'/projects/{project.id}')
    assert 'Steps 08a–08c'.encode() in detail.data and b'2/3 complete' in detail.data
    assert b'workflow-run-08c' in detail.data
    page=client.get(url)
    assert b'Verify Fencing Configuration' in page.data and b'not-a-real-secret' not in page.data
    captured=[]
    monkeypatch.setattr('clusterweaver.web.routes.fencing_create.start_verification_job',lambda *args:captured.append(args))
    response=client.post(url,data={'verify':'y'})
    assert response.status_code==202 and response.json['action']=='fencing_verify'
    assert len(captured)==1 and all(p['password']=='not-a-real-secret' for p in captured[0][4])
    assert client.post(url,data={'verify':'y'}).status_code==409
    assert client.post(f'/projects/{project.id}/stonith/create',data={'create':'y','confirm':'y','power_wait':'4'}).status_code==409
    assert client.post(f'/projects/{project.id}/edit').status_code==409


def test_readonly_worker_dispatches_verify_and_records_individual_results(app,fencing_ready,monkeypatch):
    project=fencing_ready
    _mark_creation_passed(project)
    job_id,profiles,options,snapshot=_worker_setup(project,monkeypatch)
    snapshot['failures']=[{'operation':'monitor'}]
    job=db.session.get(ClusterOperationRecord,job_id);job.action=service.VERIFY_ACTION;db.session.commit()
    stream=StringIO();stream.channel=SimpleNamespace(shutdown_write=lambda:None)
    calls=[]
    def execute(*args,**kwargs):
        calls.append(args[0])
        return stream,SimpleNamespace(channel='channel'),None
    monkeypatch.setattr(service,'_connect',lambda *args:(SimpleNamespace(exec_command=execute,close=lambda:None),'fingerprint'))
    def collect(*args,**kwargs):
        assert json.loads(stream.getvalue())['verify_only'] is True
        return 0,json.dumps(dict(status='fail',message='Checked not-a-real-secret',resources=[dict(resource=p['resource_name'],status='fail' if index==0 else 'pass',errors=['monitor failure'] if index==0 else [],warnings=[]) for index,p in enumerate(profiles)]))
    monkeypatch.setattr(service,'_collect_channel',collect)
    service.run_creation(db.engine,job_id,project,SimpleNamespace(),profiles,{},True)
    with Session(db.engine) as session:
        job=session.get(ClusterOperationRecord,job_id)
        assert job.status=='fail' and job.active_project_id is None
        assert 'not-a-real-secret' not in str(job.results)
        records=session.query(StepExecutionRecord).filter_by(project_id=project.id,step='08c').order_by(StepExecutionRecord.node_id).all()
        assert [r.status for r in records]==['fail','pass']
        assert all(r.status=='pass' for r in session.query(StepExecutionRecord).filter_by(project_id=project.id,step='08b'))
    assert len(calls)==1


def test_verify_csrf_roles_and_unknown_readonly_result_does_not_block_creation(client,app,fencing_ready,monkeypatch):
    from werkzeug.security import generate_password_hash
    project=fencing_ready
    _mark_creation_passed(project)
    url=f'/projects/{project.id}/stonith/verify'
    app.config['WTF_CSRF_ENABLED']=True
    assert client.post(url,data={'verify':'y'}).status_code==400
    app.config['WTF_CSRF_ENABLED']=False
    job=ClusterOperationRecord(id='readonly-unknown',project_id=project.id,active_project_id=None,action=service.VERIFY_ACTION,target_node='',username='test',status='unknown',phase='Interrupted verification',results=[])
    db.session.add(job);db.session.commit()
    monkeypatch.setattr('clusterweaver.web.routes.fencing_create.start_fencing_job',lambda *args:None)
    assert client.post(f'/projects/{project.id}/stonith/create',data={'create':'y','confirm':'y','power_wait':'4'}).status_code==202
    user=UserRecord(username='verify-reader',password_hash=generate_password_hash('example-password'),role='user')
    db.session.add(user);db.session.commit()
    app.config['LOGIN_DISABLED']=False
    with client.session_transaction() as session:
        session['authenticated'],session['user_id']=True,user.id
    assert client.get(url).status_code==200
    assert client.post(url,data={'verify':'y'}).status_code==403
