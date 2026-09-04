import shlex

from clusterweaver.core.models import ProjectData


def _q(value: str) -> str:
    return shlex.quote(value)


def generate_network_check(project: ProjectData) -> str:
    """Generate a read-only RHEL 9.8 network inspection script."""
    if project.rhel_major != 9 or project.rhel_minor != "8":
        return "\n".join([
            "#!/bin/bash", "", "set -o pipefail", "",
            f"echo {_q(f'Network verification is not yet supported for RHEL {project.rhel_major}.{project.rhel_minor}.')}",
            "exit 2", "",
        ])

    lines = [
        "#!/bin/bash", "", "set -o pipefail", "",
        'echo "=== ClusterWeaver: RHEL 9.8 network verification ==="',
        'NODE_HOSTNAME="$(hostname -s 2>/dev/null || hostname)"',
        'echo "Detected node: ${NODE_HOSTNAME}"', "",
        'EXPECTED_MGMT_IP=""', 'EXPECTED_CLUSTER_IP=""', 'PRIMARY_IFACE=""', 'SECONDARY_IFACE=""',
        'case "${NODE_HOSTNAME}" in',
    ]
    for node in sorted(project.nodes, key=lambda item: item.hostname.lower()):
        lines.extend([
            f"  {_q(node.hostname)})",
            f"    EXPECTED_MGMT_IP={_q(node.management_ip)}",
            f"    EXPECTED_CLUSTER_IP={_q(node.cluster_ip)}",
            f"    PRIMARY_IFACE={_q(node.primary_interface)}",
            f"    SECONDARY_IFACE={_q(node.secondary_interface)}",
            "    ;;",
        ])
    lines.extend([
        "  *)", '    echo "FAIL: ${NODE_HOSTNAME} is not defined in this ClusterWeaver project."', "    exit 2", "    ;;", "esac", "",
        'check_interface() {', '  local iface="$1"', '  local role="$2"',
        '  if [[ -z "${iface}" ]]; then echo "WARNING: no ${role} interface configured in ClusterWeaver."; return; fi',
        '  echo "--- ${role}: ${iface} ---"',
        '  if ! ip link show dev "${iface}" >/dev/null 2>&1; then echo "FAIL: interface ${iface} does not exist."; return; fi',
        '  ip -brief link show dev "${iface}"',
        '  ip -brief address show dev "${iface}"',
        '  if command -v nmcli >/dev/null 2>&1; then',
        '    nmcli -g GENERAL.STATE,GENERAL.CONNECTION,GENERAL.HWADDR,GENERAL.MTU device show "${iface}" 2>/dev/null || true',
        '  else echo "WARNING: nmcli is not installed."; fi',
        '}', "",
        'check_interface "${PRIMARY_IFACE}" "management"',
        'check_interface "${SECONDARY_IFACE}" "cluster/private"', "",
        'if [[ -n "${EXPECTED_MGMT_IP}" ]] && ip -4 -o address show | grep -Fq " ${EXPECTED_MGMT_IP}/"; then',
        '  echo "PASS: expected management IP ${EXPECTED_MGMT_IP} is configured."',
        'else echo "FAIL: expected management IP ${EXPECTED_MGMT_IP:-<not defined>} was not found."; fi',
        'if [[ -n "${EXPECTED_CLUSTER_IP}" ]] && ip -4 -o address show | grep -Fq " ${EXPECTED_CLUSTER_IP}/"; then',
        '  echo "PASS: expected cluster/private IP ${EXPECTED_CLUSTER_IP} is already configured."',
        'else echo "INFO: cluster/private IP ${EXPECTED_CLUSTER_IP:-<not defined>} is not configured yet."; fi', "",
        'echo "=== Network verification complete (no changes made) ==="', "",
    ])
    return "\n".join(lines)

