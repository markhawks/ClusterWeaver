from pathlib import Path
import os
import tempfile

import yaml

from clusterweaver.core.models import ProjectData


def project_to_dict(project: ProjectData) -> dict:
    return {
        "schema_version": 1,
        "project": {
            "uuid": str(project.uuid),
            "name": project.name,
            "slug": project.slug,
            "customer": project.customer,
            "description": project.description or "",
            "os": {
                "distribution": "rhel",
                "major": project.rhel_major,
                "minor": project.rhel_minor or "",
            },
            "platform_type": project.platform_type,
            "node_count": project.node_count,
            "created_at": project.created_at.isoformat() if project.created_at else None,
            "updated_at": project.updated_at.isoformat() if project.updated_at else None,
        },
        "nodes": [
            {
                "hostname": node.hostname,
                "nodename": node.nodename or "",
                "fqdn": node.fqdn or "",
                "site": node.site or "",
                "management_ip": node.management_ip or "",
                "cluster_ip": node.cluster_ip or "",
                "primary_interface": node.primary_interface or "",
                "secondary_interface": node.secondary_interface or "",
            }
            for node in sorted(project.nodes, key=lambda item: item.hostname.lower())
        ],
    }


def project_to_yaml(project: ProjectData) -> str:
    return yaml.safe_dump(project_to_dict(project), sort_keys=False, allow_unicode=True)


def write_project_yaml(project: ProjectData, projects_root: Path) -> tuple[Path, bool]:
    project_dir = projects_root / project.slug
    project_dir.mkdir(parents=True, exist_ok=True)
    destination = project_dir / "project.yaml"
    content = project_to_yaml(project)
    if destination.exists() and destination.read_text(encoding="utf-8") == content:
        return destination, False
    fd, temporary_name = tempfile.mkstemp(prefix=".project-", dir=project_dir, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temporary_name, destination)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return destination, True
