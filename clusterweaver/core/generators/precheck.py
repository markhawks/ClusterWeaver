import shlex

from clusterweaver.core.models import ProjectData


def generate_precheck(project: ProjectData) -> str:
    lines = [
        "#!/bin/bash",
        "",
        "set -o pipefail",
        "",
        f"echo {shlex.quote(f'=== ClusterWeaver: Pre-checks for {project.name} ===')}",
        f"echo {shlex.quote(f'Customer: {project.customer}')}",
        f"echo {shlex.quote(f'Target OS: RHEL {project.rhel_major}.{project.rhel_minor}' if project.rhel_minor else f'Target OS: RHEL {project.rhel_major}')}",
        f"echo {shlex.quote(f'Platform: {project.platform_type}')}",
        "",
        'echo "=== Local system information ==="',
        "hostnamectl 2>/dev/null || hostname",
        "cat /etc/redhat-release",
        "uname -r",
        "",
        'echo "=== Expected cluster nodes ==="',
    ]
    for node in sorted(project.nodes, key=lambda item: item.hostname.lower()):
        description = f"{node.hostname} | nodename={node.nodename or '-'} | fqdn={node.fqdn or '-'} | site={node.site or '-'} | management={node.management_ip or '-'} | cluster={node.cluster_ip or '-'} | interfaces={node.primary_interface or '-'},{node.secondary_interface or '-'}"
        lines.append(f"echo {shlex.quote(description)}")
    if not project.nodes:
        lines.append('echo "No nodes configured yet."')
    lines.extend(["", 'echo "=== Pre-check complete ==="', ""])
    return "\n".join(lines)
