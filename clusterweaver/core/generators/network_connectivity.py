import shlex

from clusterweaver.core.models import ProjectData
from clusterweaver.core.validators import host_address


def generate_network_connectivity(project: ProjectData) -> str:
    """Generate read-only private cluster network connectivity checks."""
    release = f"{project.rhel_major}.{project.rhel_minor}"
    if release not in {"9.8", "10.2"}:
        return f"#!/bin/bash\n\nset -o pipefail\n\necho {shlex.quote(f'Cluster network connectivity validation is not yet supported for RHEL {release}.')}\nexit 2\n"
    invalid = [node.hostname for node in project.nodes if not node.hostname or not node.nodename or not node.cluster_ip or not node.secondary_interface]
    if invalid or not project.nodes:
        detail = ", ".join(invalid) if invalid else "no nodes configured"
        return f"#!/bin/bash\n\nset -o pipefail\n\necho {shlex.quote(f'Cannot validate cluster connectivity: incomplete node network data ({detail}).')}\nexit 2\n"

    nodes = sorted(project.nodes, key=lambda item: item.hostname.lower())
    lines = [
        "#!/bin/bash", "", "set -o pipefail", "",
        'PASS_COUNT=0', 'FAIL_COUNT=0', 'WARNING_COUNT=0', 'INFO_COUNT=0',
        'pass() { echo "PASS: $*"; ((PASS_COUNT+=1)); }',
        'fail() { echo "FAIL: $*"; ((FAIL_COUNT+=1)); }',
        'warning() { echo "WARNING: $*"; ((WARNING_COUNT+=1)); }',
        'info() { echo "INFO: $*"; ((INFO_COUNT+=1)); }', "",
        'NODE_HOSTNAME="$(hostname -s 2>/dev/null || hostname)"',
        'CLUSTER_IFACE=""', 'LOCAL_CLUSTER_IP=""', 'LOCAL_NODENAME=""', 'PEERS=()',
        f'EXPECTED_RELEASE={shlex.quote(release)}',
        'ACTUAL_RELEASE="$(. /etc/os-release 2>/dev/null; printf %s "${VERSION_ID:-unknown}")"',
        'echo "=== ClusterWeaver: RHEL ${EXPECTED_RELEASE} cluster network connectivity ==="',
        'if [[ "${ACTUAL_RELEASE}" == "${EXPECTED_RELEASE}" ]]; then pass "RHEL ${EXPECTED_RELEASE} detected"; else fail "expected RHEL ${EXPECTED_RELEASE}, detected ${ACTUAL_RELEASE}"; exit 2; fi',
        'echo "Detected node: ${NODE_HOSTNAME}"', "", 'case "${NODE_HOSTNAME}" in',
    ]
    for node in nodes:
        peers = [peer for peer in nodes if peer.hostname.lower() != node.hostname.lower()]
        lines.extend([
            f"  {shlex.quote(node.hostname)})",
            f"    CLUSTER_IFACE={shlex.quote(node.secondary_interface)}",
            f"    LOCAL_CLUSTER_IP={shlex.quote(host_address(node.cluster_ip))}",
            f"    LOCAL_NODENAME={shlex.quote(node.nodename)}",
            "    PEERS=(" + " ".join(shlex.quote(f"{host_address(peer.cluster_ip)}|{peer.nodename}") for peer in peers) + ")",
            "    ;;",
        ])
    lines.extend([
        '  *) fail "${NODE_HOSTNAME} is not defined in this ClusterWeaver project."; exit 2 ;;', 'esac', "",
        'if ip link show dev "${CLUSTER_IFACE}" >/dev/null 2>&1; then pass "cluster interface ${CLUSTER_IFACE} exists"; else fail "cluster interface ${CLUSTER_IFACE} does not exist"; fi',
        'if ip -4 -o address show dev "${CLUSTER_IFACE}" | grep -Fq " ${LOCAL_CLUSTER_IP}/"; then pass "local private IP ${LOCAL_CLUSTER_IP} is configured on ${CLUSTER_IFACE}"; else fail "local private IP ${LOCAL_CLUSTER_IP} is not configured on ${CLUSTER_IFACE}"; fi',
        'resolved_local="$(getent ahostsv4 "${LOCAL_NODENAME}" 2>/dev/null | awk \'NR==1 {print $1}\')"',
        'if [[ "${resolved_local}" == "${LOCAL_CLUSTER_IP}" ]]; then pass "${LOCAL_NODENAME} resolves to ${LOCAL_CLUSTER_IP}"; else fail "${LOCAL_NODENAME} resolves to ${resolved_local:-<nothing>}, expected ${LOCAL_CLUSTER_IP}"; fi', "",
        'if command -v arping >/dev/null 2>&1; then',
        '  if arping -D -c 2 -w 3 -I "${CLUSTER_IFACE}" "${LOCAL_CLUSTER_IP}" >/dev/null 2>&1; then pass "no duplicate response detected for ${LOCAL_CLUSTER_IP}"; else warning "possible duplicate response detected for ${LOCAL_CLUSTER_IP}; investigate before cluster creation"; fi',
        'else warning "arping is not installed; duplicate-IP detection skipped"; fi', "",
        'if [[ ${#PEERS[@]} -eq 0 ]]; then warning "no peer nodes are configured"; fi',
        'for peer in "${PEERS[@]}"; do',
        '  IFS="|" read -r peer_ip peer_name <<< "${peer}"',
        '  echo "--- Peer: ${peer_name} (${peer_ip}) ---"',
        '  resolved_ip="$(getent ahostsv4 "${peer_name}" 2>/dev/null | awk \'NR==1 {print $1}\')"',
        '  if [[ "${resolved_ip}" == "${peer_ip}" ]]; then pass "${peer_name} resolves to ${peer_ip}"; else fail "${peer_name} resolves to ${resolved_ip:-<nothing>}, expected ${peer_ip}"; fi',
        '  route="$(ip -4 route get "${peer_ip}" 2>&1)"',
        '  echo "Route: ${route}"',
        '  if grep -Fq " dev ${CLUSTER_IFACE} " <<< " ${route} "; then pass "route to ${peer_ip} uses ${CLUSTER_IFACE}"; else fail "route to ${peer_ip} does not use ${CLUSTER_IFACE}"; fi',
        '  if ping -c 2 -W 2 "${peer_ip}" >/dev/null 2>&1; then pass "private IP ${peer_ip} is reachable"; else fail "private IP ${peer_ip} is not reachable"; fi',
        '  if ping -c 2 -W 2 "${peer_name}" >/dev/null 2>&1; then pass "nodename ${peer_name} is reachable"; else fail "nodename ${peer_name} is not reachable"; fi',
        '  mtu="$(cat "/sys/class/net/${CLUSTER_IFACE}/mtu" 2>/dev/null || true)"',
        '  if [[ "${mtu}" =~ ^[0-9]+$ ]] && (( mtu > 28 )); then',
        '    payload=$((mtu - 28))',
        '    if ping -c 1 -W 2 -M do -s "${payload}" "${peer_ip}" >/dev/null 2>&1; then pass "MTU ${mtu} path to ${peer_ip} works without fragmentation"; else warning "MTU ${mtu} path test to ${peer_ip} failed"; fi',
        '  else warning "cannot determine MTU for ${CLUSTER_IFACE}"; fi',
        'done', "",
        'echo "=== Result: PASS=${PASS_COUNT} FAIL=${FAIL_COUNT} WARNING=${WARNING_COUNT} INFO=${INFO_COUNT} ==="',
        'if (( FAIL_COUNT > 0 )); then echo "Cluster network validation FAILED."; exit 1; fi',
        'echo "Cluster network validation PASSED."', "",
    ])
    return "\n".join(lines)
