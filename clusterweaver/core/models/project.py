from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(slots=True)
class NodeData:
    hostname: str
    fqdn: str = ""
    site: str = ""
    management_ip: str = ""
    cluster_ip: str = ""
    id: int | None = None


@dataclass(slots=True)
class ProjectData:
    uuid: UUID
    name: str
    customer: str
    description: str
    rhel_major: int
    rhel_minor: str
    platform_type: str
    node_count: int
    slug: str
    nodes: list[NodeData] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    id: int | None = None

