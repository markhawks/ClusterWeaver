import copy
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from uuid import uuid4
from xml.etree import ElementTree as ET

import pytest
from sqlalchemy.orm import Session

from clusterweaver.core.services import fencing_create as service
from clusterweaver.core.services.fencing_device import create_devices, matching_resource, UncertainResult
from clusterweaver.persistence import db
from clusterweaver.persistence.models import ClusterOperationRecord, ProjectRecord, StepExecutionRecord, UserRecord
from clusterweaver.web.ssh_credentials import project_key_store
from test_cluster_operations import ready_project, snapshot_text
from test_stonith import stonith_project, profile_data


@pytest.fixture
def payload():
    return dict(cluster_name='example-ha',nodes=['node90lanc','node91lanc'],profiles=[dict(hostname=f'node{i}',nodename=f'node{i}lanc',node_id=i,resource_name=f'STONITH-{i}',controller_endpoint=f'192.0.2.{i}',username='operator',password=f'controller-secret-{i}') for i in (90,91)],options=dict(power_wait=4,monitor=None,failure_timeout=None,disabled=False))


class FakePCS:
    def __init__(self,payload):
        self.payload = payload
        self.root = ET.fromstring('<cib><configuration><nodes/><resources/></configuration></cib>')
        for name in payload['nodes']:
            ET.SubElement(self.root.find('./configuration/nodes'),'node',uname=name)
        self.calls=[]
        self.quorum=True
        self.external_change=False
        self.lose_push=False
    def __call__(self,args):
        self.calls.append(list(args))
        if args[:3]==['pcs','status','--full']:
            return 'Cluster name: '+self.payload['cluster_name']+'\n'
        if args[0]=='crm_mon':
            return '<crm_mon><summary><current_dc present="true" with_quorum="'+str(self.quorum).lower()+'"/></summary><nodes>'+''.join('<node name="'+n+'" online="true"/>' for n in self.payload['nodes'])+'</nodes></crm_mon>'
        if args[:3]==['pcs','cluster','cib']:
            if args[3].endswith('current.xml') and self.external_change:
                ET.SubElement(self.root.find('configuration'),'constraints')
            ET.ElementTree(self.root).write(args[3])
            return ''
        if args[:3]==['pcs','cluster','cib-push']:
            self.root=ET.parse(args[3]).getroot()
            if self.lose_push:
                raise TimeoutError('Transport lost after application')
            return ''
        assert args[:2]==['pcs','-f'] and args[3:5]==['stonith','create']
        tree=ET.parse(args[2])
        primitive=ET.SubElement(tree.getroot().find('./configuration/resources'),'primitive',id=args[5],type=args[6],attrib={'class':'stonith'})
        attributes=ET.SubElement(primitive,'instance_attributes')
        for arg in args[7:]:
            if arg in {'op','meta','--disabled'}:
                break
            key,value=arg.split('=',1)
            ET.SubElement(attributes,'nvpair',name=key,value=value)
        ops=ET.SubElement(primitive,'operations')
        if 'op' in args:
            index=args.index('op')
            ET.SubElement(ops,'op',name='monitor',interval=args[index+2].split('=',1)[1],timeout=args[index+3].split('=',1)[1])
        else:
            ET.SubElement(ops,'op',name='monitor',interval='60s',timeout='20s')
        if 'meta' in args:
            meta=ET.SubElement(primitive,'meta_attributes')
            key,value=args[args.index('meta')+1].split('=',1)
            ET.SubElement(meta,'nvpair',name=key,value=value)
        tree.write(args[2])
        return ''
    @property
    def pushes(self):
        return [c for c in self.calls if c[:3]==['pcs','cluster','cib-push']]


def test_creation_stages_all_devices_once_without_password_in_argv_and_is_idempotent(payload):
    pcs=FakePCS(payload)
    report=create_devices(payload,pcs)
    assert report['status']=='pass' and len(pcs.pushes)==1
    assert [r['resource'] for r in report['resources']]==['STONITH-90','STONITH-91']
    assert all(r['outcome']=='created' for r in report['resources'])
    assert 'diff-against=' in pcs.pushes[0][-1]
    assert not any(p['password'] in str(pcs.calls) for p in payload['profiles'])
    assert all(matching_resource(pcs.root,p,payload['options']) for p in payload['profiles'])
    assert all(r['operations'][0]['interval']=='60s' for r in report['resources'])
    report=create_devices(payload,pcs)
    assert all(r['outcome']=='already configured' for r in report['resources'])
    assert len(pcs.pushes)==1
    assert not Path(pcs.pushes[0][3]).exists()


def test_conflict_blocks_every_creation_without_updating_existing_secrets(payload):
    pcs=FakePCS(payload)
    create_devices(payload,pcs)
    pcs.calls=[]
    pair=pcs.root.find('./configuration/resources/primitive/instance_attributes/nvpair[@name="passwd"]')
    pair.set('value','different-existing-secret')
    with pytest.raises(ValueError,match='conflicts.*passwd') as error:
        create_devices(payload,pcs)
    assert 'different-existing-secret' not in str(error.value)
    assert not pcs.pushes and not any(c[1:2]==['-f'] for c in pcs.calls)


def test_creation_checks_quorum_and_configuration_races_and_never_retries_a_push(payload):
    pcs=FakePCS(payload)
    pcs.quorum=False
    with pytest.raises(ValueError,match='quorum'):
        create_devices(payload,pcs)
    assert not pcs.pushes
    pcs=FakePCS(payload)
    pcs.external_change=True
    with pytest.raises(ValueError,match='changed during preparation'):
        create_devices(payload,pcs)
    assert not pcs.pushes
    pcs=FakePCS(payload)
    pcs.lose_push=True
    with pytest.raises(UncertainResult):
        create_devices(payload,pcs)
    assert len(pcs.pushes)==1


def test_optional_operations_and_failure_timeout_are_explicit(payload):
    payload['options'].update(monitor=dict(interval=90,timeout=60),failure_timeout=300,disabled=True)
    pcs=FakePCS(payload)
    report=create_devices(payload,pcs)
    assert report['status']=='pass'
    calls=[c for c in pcs.calls if c[1:2]==['-f']]
    assert all('--disabled' in c and 'interval=90s' in c and 'failure-timeout=300s' in c for c in calls)
    assert all(r['operations'][0]['timeout']=='60s' for r in report['resources'])


def test_default_names_use_last_two_digits_and_preserve_saved_names(client,stonith_project):
    assert service.default_resource_name('machine2090')=='STONITH-90'
    assert service.default_resource_name('machine2091')=='STONITH-91'
    assert service.default_resource_name('node7')=='STONITH-07'
    assert service.default_resource_name('node')=='STONITH-node'
    path=f'/projects/{stonith_project.id}/stonith/profiles'
    assert b'value="STONITH-01"' in client.get(path).data
    data=profile_data(stonith_project)
    data.update(mode='ipmi',endpoint='')
    for index in (0,1):
        data[f'profiles-{index}-resource_name']=f'CUSTOM-{index}'
        data[f'profiles-{index}-controller_endpoint']=f'192.0.2.{index+1}'
    assert client.post(path,data=data).status_code==302
    page=client.get(path)
    assert b'value="CUSTOM-0"' in page.data and b'value="CUSTOM-1"' in page.data


@pytest.fixture
def fencing_ready(client,app,ready_project):
    project=ready_project
    data=profile_data(db.session.get(ProjectRecord,project.id))
    data.update(mode='ipmi',endpoint='')
    for index in (0,1):
        data[f'profiles-{index}-resource_name']=f'STONITH-9{index}'
        data[f'profiles-{index}-controller_endpoint']=f'192.0.2.{index+1}'
    assert client.post(f'/projects/{project.id}/stonith/profiles',data=data).status_code==302
    for step in ('08a','08a-fa'):
        for node in project.nodes:
            db.session.add(StepExecutionRecord(project_id=project.id,node_id=node.id,step=step,status='pass',output='test'))
    db.session.commit()
    from clusterweaver.persistence.repositories.projects import ProjectRepository
    return ProjectRepository(db.session).get(project.id)


def test_api_requires_all_checks_confirmation_role_and_reserves_one_job(client,app,fencing_ready,monkeypatch):
    project=fencing_ready
    url=f'/projects/{project.id}/stonith/create'
    captured=[]
    monkeypatch.setattr('clusterweaver.web.routes.fencing_create.start_fencing_job',lambda *args:captured.append(args))
    assert b'Create Fencing Devices' in client.get(f'/projects/{project.id}').data
    page=client.get(url)
    assert b'STONITH-90' in page.data and b'power_wait=4' in page.data
    assert b'not-a-real-secret' not in page.data
    assert client.post(url,data={'create':'y','power_wait':'4'}).status_code==400
    response=client.post(url,data={'create':'y','confirm':'y','power_wait':'4'})
    assert response.status_code==202 and len(captured)==1
    assert all(p['password']=='not-a-real-secret' for p in captured[0][4])
    assert client.post(url,data={'create':'y','confirm':'y','power_wait':'4'}).status_code==409
    assert client.post(f'/projects/{project.id}/stonith/profiles',data=profile_data(db.session.get(ProjectRecord,project.id))).status_code==409
    assert client.post(f'/projects/{project.id}/edit').status_code==409
    jobs=client.get(f'/projects/{project.id}/operations').json['jobs']
    assert jobs[0]['action']=='fencing_create' and 'not-a-real-secret' not in str(jobs)


def _worker_setup(project,monkeypatch):
    from clusterweaver.core.services.cluster_operations import parse_snapshot
    snap=parse_snapshot(snapshot_text(project),project)
    monkeypatch.setattr(service,'snapshot_node',lambda *args: copy.deepcopy(snap))
    monkeypatch.setattr(service,'check_cluster_agents',lambda nodes,*args:[SimpleNamespace(ok=True) for n in nodes])
    monkeypatch.setattr(service,'verify_ipmi_profiles_on_nodes',lambda *args:[SimpleNamespace(ok=True)])
    profiles=[dict(p,password='not-a-real-secret') for p in service.creation_profiles(project)]
    options=dict(power_wait=4,monitor=None,failure_timeout=None,disabled=False)
    job=ClusterOperationRecord(id=str(uuid4()),project_id=project.id,active_project_id=project.id,action=service.ACTION,target_node='',username='tester',status='queued',phase='Queued',results=[])
    db.session.add(job)
    db.session.commit()
    return job.id,profiles,options,snap


def test_worker_preflights_once_runs_one_coordinator_and_persists_redacted_results(app,fencing_ready,monkeypatch):
    from io import StringIO
    project=fencing_ready
    job_id,profiles,options,snap=_worker_setup(project,monkeypatch)
    stream=StringIO()
    stream.channel=SimpleNamespace(shutdown_write=lambda:None)
    commands=[]
    def execute(command,timeout):
        commands.append(command)
        assert 'not-a-real-secret' not in command
        return stream,SimpleNamespace(channel='channel'),None
    monkeypatch.setattr(service,'_connect',lambda *args:(SimpleNamespace(exec_command=execute,close=lambda:None),'fingerprint'))
    def collect(*args,**kwargs):
        payload=json.loads(stream.getvalue())
        assert all(p['password']=='not-a-real-secret' for p in payload['profiles'])
        return 0,json.dumps(dict(status='pass',message='Verified not-a-real-secret',resources=[dict(resource=p['resource_name'],outcome='created',operations=[]) for p in profiles]))
    monkeypatch.setattr(service,'_collect_channel',collect)
    service.run_creation(db.engine,job_id,project,SimpleNamespace(),profiles,options)
    with Session(db.engine) as session:
        job=session.get(ClusterOperationRecord,job_id)
        assert job.status=='pass' and job.active_project_id is None
        assert 'not-a-real-secret' not in str(job.results)
        records=session.query(StepExecutionRecord).filter_by(project_id=project.id,step='08b').all()
        assert len(records)==2 and all(r.status=='pass' for r in records)
    assert len(commands)==1


def test_worker_blocks_unreachable_peer_and_marks_lost_creation_transport_unknown(app,fencing_ready,monkeypatch):
    from io import StringIO
    project=fencing_ready
    job_id,profiles,options,_=_worker_setup(project,monkeypatch)
    monkeypatch.setattr(service,'verify_ipmi_profiles_on_nodes',lambda *args:[SimpleNamespace(ok=False)])
    monkeypatch.setattr(service,'_connect',lambda *args: (_ for _ in ()).throw(AssertionError('No creation command allowed')))
    service.run_creation(db.engine,job_id,project,None,profiles,options)
    with Session(db.engine) as session:
        job=session.get(ClusterOperationRecord,job_id)
        assert job.status=='fail' and 'at least one other' in job.results[0]['output']
    job_id,profiles,options,_=_worker_setup(project,monkeypatch)
    stream=StringIO();stream.channel=SimpleNamespace(shutdown_write=lambda:None)
    calls=[]
    def execute(*args,**kwargs):
        calls.append(1)
        return stream,SimpleNamespace(channel='channel'),None
    monkeypatch.setattr(service,'_connect',lambda *args:(SimpleNamespace(exec_command=execute,close=lambda:None),'fingerprint'))
    monkeypatch.setattr(service,'_collect_channel',lambda *args,**kwargs: (_ for _ in ()).throw(TimeoutError('Connection lost')))
    service.run_creation(db.engine,job_id,project,None,profiles,options)
    with Session(db.engine) as session:
        job=session.get(ClusterOperationRecord,job_id)
        assert job.status=='unknown' and job.active_project_id is None
    assert len(calls)==1


def test_api_blocks_missing_agent_proof_and_invalid_csrf_and_readers(client,app,fencing_ready,monkeypatch):
    from werkzeug.security import generate_password_hash
    project=fencing_ready
    url=f'/projects/{project.id}/stonith/create'
    proof=db.session.query(StepExecutionRecord).filter_by(project_id=project.id,step='08a-fa').first()
    proof.status='fail';db.session.commit()
    assert client.post(url,data={'create':'y','confirm':'y','power_wait':'4'}).status_code==409
    assert b'cluster-node fence-agent verification' in client.get(url).data
    proof.status='pass';db.session.commit()
    app.config['WTF_CSRF_ENABLED']=True
    assert client.post(url,data={'create':'y','confirm':'y','power_wait':'4'}).status_code==400
    app.config['WTF_CSRF_ENABLED']=False
    user=UserRecord(username='fencing-reader',password_hash=generate_password_hash('example-password'),role='user')
    db.session.add(user);db.session.commit()
    app.config['LOGIN_DISABLED']=False
    with client.session_transaction() as session:
        session['authenticated'],session['user_id']=True,user.id
    assert client.get(url).status_code==200
    assert client.post(url,data={'create':'y','confirm':'y','power_wait':'4'}).status_code==403


def test_editing_fencing_definitions_invalidates_previous_creation_results(client,app,fencing_ready):
    project=fencing_ready
    for node in project.nodes:
        db.session.add(StepExecutionRecord(project_id=project.id,node_id=node.id,step='08b',status='pass',output='old result'))
    db.session.commit()
    data=profile_data(db.session.get(ProjectRecord,project.id))
    data.update(mode='ipmi',endpoint='')
    for index in (0,1):
        data[f'profiles-{index}-resource_name']=f'NEW-NAME-{index}'
        data[f'profiles-{index}-controller_endpoint']=f'192.0.2.{index+1}'
    assert client.post(f'/projects/{project.id}/stonith/profiles',data=data).status_code==302
    assert not db.session.query(StepExecutionRecord).filter_by(project_id=project.id,step='08b').all()
