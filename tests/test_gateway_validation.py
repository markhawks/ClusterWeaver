from uuid import uuid4

import pytest

from clusterweaver.core.models import ProjectData, NodeData
from clusterweaver.core.services.project_transfer import build_project_archive, read_project_archive, ProjectTransferError
from clusterweaver.core.validators.project import validate_gateway
from clusterweaver.persistence import db
from clusterweaver.persistence.models import NodeRecord


@pytest.mark.parametrize('gateway', ['192.0.2.10', '192.0.2.0', '192.0.2.255', '192.0.3.1', '0.0.0.0', '127.0.0.1', '224.0.0.1', '240.0.0.1', '::1'])
def test_gateway_rejects_impossible_addresses(gateway):
    with pytest.raises(ValueError):
        validate_gateway('192.0.2.10/24', gateway)


@pytest.mark.parametrize('address,gateway', [('192.0.2.10/24', '192.0.2.1'), ('192.0.2.10/24', '192.0.2.254'), ('192.0.2.0/31', '192.0.2.1'), ('192.0.2.1/31', '192.0.2.0')])
def test_gateway_accepts_valid_hosts_including_point_to_point(address, gateway):
    validate_gateway(address, gateway)


def test_configuration_rejects_self_peer_and_reverse_gateway_collisions(client, app):
    response = client.post('/projects/new', data=dict(name='Gateway validation', customer='Example', rhel_major='9', rhel_minor='8', platform_type='virtual', hypervisor='kvm', node_count='2'))
    url = response.headers['Location']
    node_url = url + '/nodes/new'
    base = dict(hostname='node01', nodename='node01lanc', management_ip='192.0.2.10/24', management_gateway='192.0.2.1', primary_interface='bond0', cluster_ip='198.51.100.10/24', cluster_gateway='198.51.100.1', secondary_interface='bond1')
    page = client.get(node_url)
    assert b'gateway-node-inventory' in page.data
    for field, value in [('management_gateway', '192.0.2.10'), ('management_gateway', '192.0.2.0'), ('management_gateway', '192.0.2.255'), ('cluster_gateway', '198.51.100.10')]:
        response = client.post(node_url, data={**base, field: value})
        assert response.status_code == 200
    assert client.post(node_url, data=base).status_code == 302
    other = {**base, 'hostname': 'node02', 'nodename': 'node02lanc', 'management_ip': '192.0.2.11/24', 'cluster_ip': '198.51.100.11/24'}
    response = client.post(node_url, data={**other, 'management_gateway': '192.0.2.10'})
    assert b'equals a node IP address (node01)' in response.data
    response = client.post(node_url, data={**other, 'management_ip': '192.0.2.1/24', 'management_gateway': '192.0.2.254'})
    assert b'already configured as a gateway' in response.data
    assert client.post(node_url, data=other).status_code == 302
    with app.app_context():
        first = db.session.query(NodeRecord).filter_by(hostname='node01').one()
        node_id = first.id
    assert b'equals a node IP address (node02)' in client.post(url + f'/nodes/{node_id}/edit', data={**base, 'management_gateway': '192.0.2.11'}).data
    assert client.post(url + f'/nodes/{node_id}/edit', data=base).status_code == 302
    with app.app_context():
        assert db.session.get(NodeRecord, node_id).management_gateway == '192.0.2.1'
        assert db.session.query(NodeRecord).count() == 2


def test_import_rejects_gateway_equal_to_a_later_nodes_address():
    project = ProjectData(uuid=uuid4(), name='Example', customer='Example', description='', rhel_major=9, rhel_minor='8', platform_type='physical', hardware='dell', node_count=2, slug='example', nodes=[
        NodeData(hostname='node01', nodename='node01lanc', management_ip='192.0.2.10/24', management_gateway='192.0.2.11', primary_interface='bond0'),
        NodeData(hostname='node02', nodename='node02lanc', management_ip='192.0.2.11/24', management_gateway='192.0.2.1', primary_interface='bond0'),
    ])
    with pytest.raises(ProjectTransferError, match='equals a node IP address'):
        read_project_archive(build_project_archive(project, {}))
    project.nodes[0].management_gateway = '192.0.2.1'
    assert len(read_project_archive(build_project_archive(project, {}))['nodes']) == 2
