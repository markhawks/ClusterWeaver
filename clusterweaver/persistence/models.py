from datetime import datetime, timezone
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from clusterweaver.persistence.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProjectRecord(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    customer: Mapped[str] = mapped_column(String(160), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    rhel_major: Mapped[int] = mapped_column(Integer)
    rhel_minor: Mapped[str] = mapped_column(String(20), default="")
    platform_type: Mapped[str] = mapped_column(String(20))
    node_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    nodes: Mapped[list["NodeRecord"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="NodeRecord.hostname"
    )


class NodeRecord(Base):
    __tablename__ = "nodes"
    __table_args__ = (UniqueConstraint("project_id", "hostname", name="uq_node_project_hostname"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    hostname: Mapped[str] = mapped_column(String(253))
    fqdn: Mapped[str] = mapped_column(String(253), default="")
    site: Mapped[str] = mapped_column(String(120), default="")
    management_ip: Mapped[str] = mapped_column(String(45), default="")
    cluster_ip: Mapped[str] = mapped_column(String(45), default="")
    project: Mapped[ProjectRecord] = relationship(back_populates="nodes")

