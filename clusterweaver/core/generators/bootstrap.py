import shlex

from clusterweaver.core.models import ProjectData
from clusterweaver.core.services.ssh_bootstrap import DISCOVERY_COMMAND


def generate_ssh_discovery() -> str:
    """Return the exact read-only payload executed on every node."""
    return "#!/bin/bash\n\n" + DISCOVERY_COMMAND.rstrip() + "\n"


def generate_peer_trust(project: ProjectData) -> str:
    """Describe the password-free remote payloads used to create peer trust."""
    nodes = " ".join(shlex.quote(node.hostname) for node in project.nodes)
    return f"""#!/bin/bash

# ClusterWeaver Step 00b remote execution plan
# Target nodes: {nodes or '<configure nodes first>'}
# Passwords and private keys are never embedded in this view.
set -o errexit
set -o nounset
set -o pipefail

# Executed independently on every node:
install -d -m 700 /root/.ssh
test -f /root/.ssh/id_ed25519 || \\
  ssh-keygen -q -t ed25519 -N '' -C clusterweaver-bootstrap -f /root/.ssh/id_ed25519
cat /root/.ssh/id_ed25519.pub

# ClusterWeaver collects each public key through the SSH session, then on every
# target performs the equivalent operation below once for every peer key:
PEER_PUBLIC_KEY='<public key collected from another configured node>'
touch /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
grep -qxF "${{PEER_PUBLIC_KEY}}" /root/.ssh/authorized_keys || \\
  printf '%s\n' "${{PEER_PUBLIC_KEY}}" >> /root/.ssh/authorized_keys
"""


def generate_network_configuration_plan(project: ProjectData) -> str:
    """Return a credential-free representation of Step 00c orchestration."""
    release = f"{project.rhel_major}.{project.rhel_minor}"
    read_only = release == "7.9"
    lines = [
        "#!/bin/bash", "",
        "# ClusterWeaver Step 00c remote execution plan",
        f"# Expected platform: RHEL {release}",
        "# This view contains no SSH credentials.",
        "# ClusterWeaver executes the checks separately on the selected node.", "",
        "set -o pipefail",
        f"EXPECTED_RELEASE={shlex.quote(release)}",
        "ACTUAL_RELEASE=$(. /etc/os-release 2>/dev/null; printf '%s' \"${VERSION_ID:-unknown}\")",
        "[[ \"${ACTUAL_RELEASE}\" = \"${EXPECTED_RELEASE}\" ]] || { echo \"FAIL: expected RHEL ${EXPECTED_RELEASE}, detected ${ACTUAL_RELEASE}\"; exit 1; }", "",
    ]
    if read_only:
        lines.extend([
            "# RHEL 7.9 safety policy: inspection only. No modifying command is executed.",
            "if command -v nmcli >/dev/null 2>&1; then",
            "  systemctl is-active NetworkManager 2>/dev/null || true",
            "  nmcli -t -f RUNNING general 2>/dev/null || true",
            "fi", "",
        ])
    else:
        lines.extend([
            "# RHEL 9.8/10.2: if the current configuration already matches, execution stops",
            "# successfully without changes. Otherwise ClusterWeaver checks duplicate IPs,",
            "# creates NetworkManager candidate profiles, arms a 90-second systemd rollback,",
            "# activates management, reconnects to the desired IP, cancels rollback only after",
            "# successful SSH verification, archives the old profile, then configures private",
            "# networking with ipv4.never-default=yes. Private changes are blocked after a",
            "# formed pcs cluster is detected.", "",
        ])
    for node in project.nodes:
        lines.extend([
            f"# --- {node.hostname} ---",
            f"PRIMARY_INTERFACE={shlex.quote(node.primary_interface or '<not configured>')}",
            f"MANAGEMENT_CIDR={shlex.quote(node.management_ip or '<not configured>')}",
            f"MANAGEMENT_GATEWAY={shlex.quote(node.management_gateway or '<not configured>')}",
            f"SECONDARY_INTERFACE={shlex.quote(node.secondary_interface or '<not configured>')}",
            f"PRIVATE_CIDR={shlex.quote(node.cluster_ip or '<not configured>')}",
            "ip link show dev \"${PRIMARY_INTERFACE}\"",
            "ip -4 -o address show dev \"${PRIMARY_INTERFACE}\" scope global",
            "ip -4 route show default dev \"${PRIMARY_INTERFACE}\"",
        ])
        if node.secondary_interface:
            lines.extend([
                "ip link show dev \"${SECONDARY_INTERFACE}\"",
                "ip -4 -o address show dev \"${SECONDARY_INTERFACE}\" scope global",
                "ip -4 route show default dev \"${SECONDARY_INTERFACE}\"",
            ])
        lines.append("")
    lines.append("# End of sanitized orchestration view.")
    return "\n".join(lines) + "\n"
