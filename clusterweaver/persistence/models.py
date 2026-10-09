from datetime import datetime, timezone
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from clusterweaver.persistence.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProjectGroupRecord(Base):
    __tablename__ = "project_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    normalized_name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    color: Mapped[str] = mapped_column(String(7))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    projects: Mapped[list["ProjectRecord"]] = relationship(back_populates="group")


class ProjectRecord(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    cluster_name: Mapped[str] = mapped_column(String(64), default="")
    group_id: Mapped[int | None] = mapped_column(ForeignKey("project_groups.id", ondelete="SET NULL"), nullable=True, index=True)
    customer: Mapped[str] = mapped_column(String(160), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    rhel_major: Mapped[int] = mapped_column(Integer)
    rhel_minor: Mapped[str] = mapped_column(String(20), default="")
    platform_type: Mapped[str] = mapped_column(String(20))
    hypervisor: Mapped[str] = mapped_column(String(20), default="")
    hardware: Mapped[str] = mapped_column(String(20), default="")
    node_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    nodes: Mapped[list["NodeRecord"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="NodeRecord.hostname"
    )
    step_executions: Mapped[list["StepExecutionRecord"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    group: Mapped[ProjectGroupRecord | None] = relationship(back_populates="projects")
    operation_jobs: Mapped[list["ClusterOperationRecord"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    stonith_configuration: Mapped["StonithConfigurationRecord | None"] = relationship(
        back_populates="project", cascade="all, delete-orphan", uselist=False
    )


class NodeRecord(Base):
    __tablename__ = "nodes"
    __table_args__ = (UniqueConstraint("project_id", "hostname", name="uq_node_project_hostname"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    hostname: Mapped[str] = mapped_column(String(253))
    nodename: Mapped[str] = mapped_column(String(253), default="")
    fqdn: Mapped[str] = mapped_column(String(253), default="")
    site: Mapped[str] = mapped_column(String(120), default="")
    management_ip: Mapped[str] = mapped_column(String(45), default="")
    management_gateway: Mapped[str] = mapped_column(String(45), default="")
    cluster_ip: Mapped[str] = mapped_column(String(45), default="")
    cluster_gateway: Mapped[str] = mapped_column(String(45), default="")
    primary_interface: Mapped[str] = mapped_column(String(64), default="")
    secondary_interface: Mapped[str] = mapped_column(String(64), default="")
    bootstrap_ip: Mapped[str] = mapped_column(String(45), default="")
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)
    project: Mapped[ProjectRecord] = relationship(back_populates="nodes")
    step_executions: Mapped[list["StepExecutionRecord"]] = relationship(back_populates="node", cascade="all, delete-orphan")
    stonith_profile: Mapped["StonithProfileRecord | None"] = relationship(
        back_populates="node", cascade="all, delete-orphan", uselist=False
    )


class StonithConfigurationRecord(Base):
    __tablename__ = "stonith_configurations"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), unique=True)
    hardware: Mapped[str] = mapped_column(String(20), default="dell")
    mode: Mapped[str] = mapped_column(String(20), default="oem")
    endpoint: Mapped[str] = mapped_column(String(253))
    project: Mapped[ProjectRecord] = relationship(back_populates="stonith_configuration")
    profiles: Mapped[list["StonithProfileRecord"]] = relationship(
        back_populates="configuration", cascade="all, delete-orphan"
    )


class StonithProfileRecord(Base):
    __tablename__ = "stonith_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    configuration_id: Mapped[int] = mapped_column(ForeignKey("stonith_configurations.id", ondelete="CASCADE"))
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), unique=True)
    controller_endpoint: Mapped[str] = mapped_column(String(253), default="")
    resource_name: Mapped[str] = mapped_column(String(160), default="")
    profile_name: Mapped[str] = mapped_column(String(160))
    username: Mapped[str] = mapped_column(String(128))
    configuration: Mapped[StonithConfigurationRecord] = relationship(back_populates="profiles")
    node: Mapped[NodeRecord] = relationship(back_populates="stonith_profile")


class StepExecutionRecord(Base):
    __tablename__ = "step_executions"
    __table_args__ = (UniqueConstraint("project_id", "node_id", "step", name="uq_step_execution_project_node_step"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), index=True)
    step: Mapped[str] = mapped_column(String(8), index=True)
    status: Mapped[str] = mapped_column(String(16))
    output: Mapped[str] = mapped_column(Text, default="")
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    project: Mapped[ProjectRecord] = relationship(back_populates="step_executions")
    node: Mapped[NodeRecord] = relationship(back_populates="step_executions")


class UserRecord(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="user", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utcnow)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    theme: Mapped[str] = mapped_column(String(16), default="dark")


class ClusterOperationRecord(Base):
    __tablename__ = "cluster_operations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    active_project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    action: Mapped[str] = mapped_column(String(20))
    target_node: Mapped[str] = mapped_column(String(253), default="")
    username: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    phase: Mapped[str] = mapped_column(String(80), default="Queued")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    results: Mapped[list] = mapped_column(JSON, default=list)
    project: Mapped[ProjectRecord] = relationship(back_populates="operation_jobs")
