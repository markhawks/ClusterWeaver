from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, union_all
from sqlalchemy.orm import selectinload

from clusterweaver.core.models import NodeData, ProjectData
from clusterweaver.core.validators import host_address
from clusterweaver.persistence.models import NodeRecord, ProjectRecord, StepExecutionRecord, utcnow


def to_domain(record: ProjectRecord) -> ProjectData:
    return ProjectData(
        id=record.id,
        uuid=UUID(record.uuid),
        name=record.name,
        slug=record.slug,
        customer=record.customer,
        description=record.description,
        rhel_major=record.rhel_major,
        rhel_minor=record.rhel_minor,
        platform_type=record.platform_type,
        hypervisor=record.hypervisor,
        node_count=record.node_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
        nodes=[
            NodeData(
                id=node.id,
                hostname=node.hostname,
                nodename=node.nodename,
                fqdn=node.fqdn,
                site=node.site,
                management_ip=node.management_ip,
                management_gateway=node.management_gateway,
                cluster_ip=node.cluster_ip,
                cluster_gateway=node.cluster_gateway,
                primary_interface=node.primary_interface,
                secondary_interface=node.secondary_interface,
                bootstrap_ip=node.bootstrap_ip,
                ssh_port=node.ssh_port,
            )
            for node in record.nodes
        ],
    )


class ProjectRepository:
    def __init__(self, session) -> None:
        self.session = session

    def list(self) -> list[ProjectData]:
        statement = select(ProjectRecord).options(selectinload(ProjectRecord.nodes)).order_by(ProjectRecord.updated_at.desc())
        return [to_domain(record) for record in self.session.scalars(statement).all()]

    def get(self, project_id: int) -> ProjectData | None:
        statement = select(ProjectRecord).where(ProjectRecord.id == project_id).options(selectinload(ProjectRecord.nodes))
        record = self.session.scalar(statement)
        return to_domain(record) if record else None

    def get_record(self, project_id: int) -> ProjectRecord | None:
        return self.session.get(ProjectRecord, project_id)

    def slug_exists(self, slug: str, excluding_id: int | None = None) -> bool:
        statement = select(ProjectRecord.id).where(ProjectRecord.slug == slug)
        if excluding_id is not None:
            statement = statement.where(ProjectRecord.id != excluding_id)
        return self.session.scalar(statement) is not None

    def interface_names(self) -> list[str]:
        statement = union_all(
            select(NodeRecord.primary_interface.label("name")),
            select(NodeRecord.secondary_interface.label("name")),
        )
        saved = {value.strip() for value in self.session.scalars(statement) if value and value.strip()}
        return sorted({"enp1s0", "enp7s0", "ens160", "ens224", *saved})

    def node_conflicts(self, project_id: int, values: dict[str, str], excluding_id: int | None = None) -> dict[str, str]:
        statement = select(NodeRecord).where(NodeRecord.project_id == project_id)
        if excluding_id is not None:
            statement = statement.where(NodeRecord.id != excluding_id)
        nodes = self.session.scalars(statement).all()
        conflicts: dict[str, str] = {}
        for field in ("hostname", "fqdn", "nodename"):
            candidate = values.get(field, "").strip().lower()
            if candidate and any(getattr(node, field).strip().lower() == candidate for node in nodes):
                conflicts[field] = f"This {field} is already used by another node in the project."
        used_ips = {host_address(address.strip()) for node in nodes for address in (node.management_ip, node.cluster_ip) if address.strip()}
        for field in ("management_ip", "cluster_ip"):
            candidate = values.get(field, "").strip()
            if candidate and host_address(candidate) in used_ips:
                conflicts[field] = "This IP address is already used by another node in the project."
        management_ip = values.get("management_ip", "").strip()
        cluster_ip = values.get("cluster_ip", "").strip()
        if management_ip and cluster_ip and host_address(management_ip) == host_address(cluster_ip):
            conflicts["cluster_ip"] = "Management and cluster IP addresses must be different."
        return conflicts

    def step_results(self, project_id: int) -> dict[str, list[StepExecutionRecord]]:
        statement = (
            select(StepExecutionRecord)
            .where(StepExecutionRecord.project_id == project_id)
            .options(selectinload(StepExecutionRecord.node))
            .order_by(StepExecutionRecord.step, StepExecutionRecord.node_id)
        )
        records = self.session.scalars(statement).all()
        grouped: dict[str, list[StepExecutionRecord]] = {}
        for record in records:
            grouped.setdefault(record.step, []).append(record)
        return grouped

    def save_step_results(self, project_id: int, step: str, results) -> None:
        project = self.get_record(project_id)
        if project is None:
            return
        nodes_by_hostname = {node.hostname: node for node in project.nodes}
        for result in results:
            node = nodes_by_hostname.get(result.hostname)
            if node is None:
                continue
            statement = select(StepExecutionRecord).where(
                StepExecutionRecord.project_id == project_id,
                StepExecutionRecord.node_id == node.id,
                StepExecutionRecord.step == step,
            )
            record = self.session.scalar(statement)
            if record is None:
                record = StepExecutionRecord(project_id=project_id, node_id=node.id, step=step, status="fail", output="")
                self.session.add(record)
            record.status = "pass" if result.ok else "fail"
            record.output = result.output[-20000:]
            record.executed_at = utcnow()

    def add_project(self, **values) -> ProjectRecord:
        record = ProjectRecord(**values)
        self.session.add(record)
        self.session.flush()
        return record

    def add_node(self, project: ProjectRecord, **values) -> NodeRecord:
        node = NodeRecord(project=project, **values)
        self.session.add(node)
        self.session.flush()
        return node
