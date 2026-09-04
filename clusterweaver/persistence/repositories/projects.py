from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, union_all
from sqlalchemy.orm import selectinload

from clusterweaver.core.models import NodeData, ProjectData
from clusterweaver.persistence.models import NodeRecord, ProjectRecord


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
        node_count=record.node_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
        nodes=[
            NodeData(
                id=node.id,
                hostname=node.hostname,
                fqdn=node.fqdn,
                site=node.site,
                management_ip=node.management_ip,
                cluster_ip=node.cluster_ip,
                primary_interface=node.primary_interface,
                secondary_interface=node.secondary_interface,
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
        return sorted({"ens160", "ens224", *saved})

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
