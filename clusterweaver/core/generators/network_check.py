import shlex

from clusterweaver.core.models import ProjectData


def _q(value: str) -> str:
    return shlex.quote(value)


def generate_network_check(project: ProjectData) -> str:
    """Generate a read-only RHEL 9.8/10.2 network inspection script."""
    release = f"{project.rhel_major}.{project.rhel_minor}"
    if release not in {"9.8", "10.2"}:
        return "\n".join([
            "#!/bin/bash", "", "set -o pipefail", "",
            f"echo {_q(f'Network verification is not yet supported for RHEL {release}.')}",
            "exit 2", "",
        ])

    lines = [
        "#!/bin/bash", "", "set -o pipefail", "",
        "FAIL_COUNT=0", "WARNING_COUNT=0",
        'pass() { echo "PASS: $*"; }',
        'fail() { echo "FAIL: $*"; ((FAIL_COUNT+=1)); }',
        'warning() { echo "WARNING: $*"; ((WARNING_COUNT+=1)); }', "",
        f'EXPECTED_RELEASE={_q(release)}',
        f'echo "=== ClusterWeaver: RHEL {release} network verification ==="',
        'NODE_HOSTNAME="$(hostname -s 2>/dev/null || hostname)"',
        'echo "Detected node: ${NODE_HOSTNAME}"', "",
        'EXPECTED_MGMT_IP=""', 'EXPECTED_MGMT_GATEWAY=""',
        'EXPECTED_CLUSTER_IP=""',
        'PRIMARY_IFACE=""', 'SECONDARY_IFACE=""',
        'case "${NODE_HOSTNAME}" in',
    ]
    for node in sorted(project.nodes, key=lambda item: item.hostname.lower()):
        lines.extend([
            f"  {_q(node.hostname)})",
            f"    EXPECTED_MGMT_IP={_q(node.management_ip)}",
            f"    EXPECTED_MGMT_GATEWAY={_q(node.management_gateway)}",
            f"    EXPECTED_CLUSTER_IP={_q(node.cluster_ip)}",
            f"    PRIMARY_IFACE={_q(node.primary_interface)}",
            f"    SECONDARY_IFACE={_q(node.secondary_interface)}",
            "    ;;",
        ])
    lines.extend([
        "  *)", '    echo "FAIL: ${NODE_HOSTNAME} is not defined in this ClusterWeaver project."', "    exit 2", "    ;;", "esac", "",
        'ACTUAL_RELEASE="$(. /etc/os-release 2>/dev/null; printf %s "${VERSION_ID:-unknown}")"',
        'if [[ "${ACTUAL_RELEASE}" == "${EXPECTED_RELEASE}" ]]; then pass "RHEL ${EXPECTED_RELEASE} detected"; else fail "detected release ${ACTUAL_RELEASE}, expected RHEL ${EXPECTED_RELEASE}"; fi',
        'if ! command -v nmcli >/dev/null 2>&1; then fail "nmcli is not installed"; fi', "",
        'check_interface() {', '  local iface="$1"', '  local role="$2"',
        '  if [[ -z "${iface}" ]]; then warning "no ${role} interface configured in ClusterWeaver"; return; fi',
        '  echo "--- ${role}: ${iface} ---"',
        '  if ! ip link show dev "${iface}" >/dev/null 2>&1; then fail "interface ${iface} does not exist"; return; fi',
        '  pass "interface ${iface} exists"',
        '  ip -brief link show dev "${iface}"',
        '  ip -brief address show dev "${iface}"',
        '  state="$(nmcli -g GENERAL.STATE device show "${iface}" 2>/dev/null || true)"',
        '  connection="$(nmcli -g GENERAL.CONNECTION device show "${iface}" 2>/dev/null || true)"',
        '  mac="$(nmcli -g GENERAL.HWADDR device show "${iface}" 2>/dev/null || true)"',
        '  mtu="$(cat "/sys/class/net/${iface}/mtu" 2>/dev/null || true)"',
        '  echo "NetworkManager: state=${state:-unknown} connection=${connection:-none} MAC=${mac:-unknown} MTU=${mtu:-unknown}"',
        '  [[ "${state}" == 100* ]] && pass "${iface} is connected in NetworkManager" || fail "${iface} is not connected in NetworkManager"',
        '  [[ "${mtu}" =~ ^[0-9]+$ ]] && pass "${iface} MTU is ${mtu}" || fail "cannot determine MTU for ${iface}"',
        '}', "",
        'check_interface "${PRIMARY_IFACE}" "management"',
        'check_interface "${SECONDARY_IFACE}" "cluster/private"', "",
        'if [[ -n "${EXPECTED_MGMT_IP}" ]] && ip -4 -o address show dev "${PRIMARY_IFACE}" | grep -Fq " ${EXPECTED_MGMT_IP} "; then pass "management IP ${EXPECTED_MGMT_IP} is configured on ${PRIMARY_IFACE}"; else fail "management IP ${EXPECTED_MGMT_IP:-<not defined>} was not found on ${PRIMARY_IFACE:-<not defined>}"; fi',
        'if [[ -n "${EXPECTED_MGMT_GATEWAY}" ]] && ip -4 route show default | grep -Fq "default via ${EXPECTED_MGMT_GATEWAY} dev ${PRIMARY_IFACE}"; then pass "default route uses ${EXPECTED_MGMT_GATEWAY} on ${PRIMARY_IFACE}"; else fail "expected default route via ${EXPECTED_MGMT_GATEWAY:-<not defined>} on ${PRIMARY_IFACE:-<not defined>} was not found"; fi',
        'if [[ -n "${EXPECTED_MGMT_GATEWAY}" ]] && ping -c 1 -W 2 "${EXPECTED_MGMT_GATEWAY}" >/dev/null 2>&1; then pass "management gateway ${EXPECTED_MGMT_GATEWAY} is reachable"; else warning "management gateway ${EXPECTED_MGMT_GATEWAY:-<not defined>} did not answer ICMP"; fi', "",
        'if [[ -n "${EXPECTED_CLUSTER_IP}" ]] && ip -4 -o address show dev "${SECONDARY_IFACE}" | grep -Fq " ${EXPECTED_CLUSTER_IP} "; then pass "cluster/private IP ${EXPECTED_CLUSTER_IP} is configured on ${SECONDARY_IFACE}"; else fail "cluster/private IP ${EXPECTED_CLUSTER_IP:-<not defined>} was not found on ${SECONDARY_IFACE:-<not defined>}"; fi',
        'if [[ -n "${SECONDARY_IFACE}" ]] && ip -4 route show default | grep -Fq " dev ${SECONDARY_IFACE}"; then fail "cluster/private interface ${SECONDARY_IFACE} owns a default route"; else pass "cluster/private interface does not own a default route"; fi',
        'private_connection="$(nmcli -g GENERAL.CONNECTION device show "${SECONDARY_IFACE}" 2>/dev/null || true)"',
        'if [[ -n "${private_connection}" && "${private_connection}" != "--" ]]; then',
        '  never_default="$(nmcli -g ipv4.never-default connection show "${private_connection}" 2>/dev/null || true)"',
        '  [[ "${never_default}" == "yes" ]] && pass "cluster/private profile is marked never-default" || fail "cluster/private profile is not marked never-default"',
        'fi', "",
        'echo "=== Result: FAIL=${FAIL_COUNT} WARNING=${WARNING_COUNT} ==="',
        'if (( FAIL_COUNT > 0 )); then echo "Network verification FAILED."; exit 1; fi',
        'echo "Network verification PASSED (no changes made)."', "",
    ])
    return "\n".join(lines)
