import shlex

from clusterweaver.core.models import ProjectData


def generate_cluster_setup(project: ProjectData, execute_setup: bool = True) -> str:
    """Generate cluster creation on one coordinator and verification on every node."""
    nodes = [node.nodename for node in sorted(project.nodes, key=lambda item: item.nodename.lower()) if node.nodename]
    if not nodes or len(nodes) != len(project.nodes):
        return "#!/bin/bash\n\necho 'FAIL: every node requires a cluster nodename before step 07.' >&2\nexit 2\n"
    cluster_name = project.cluster_name or project.name
    node_args = " ".join(shlex.quote(node) for node in nodes)
    return "\n".join([
        "#!/bin/bash", "", "set -o pipefail", "",
        f"CLUSTER_NAME={shlex.quote(cluster_name)}",
        f"EXPECTED_NODES={len(nodes)}",
        f"NODES=({node_args})",
        f"EXECUTE_SETUP={1 if execute_setup else 0}", "",
        'if [[ ${EUID} -ne 0 ]]; then echo "FAIL: run this script as root." >&2; exit 1; fi',
        'if ! rpm -q pcs pacemaker >/dev/null 2>&1; then echo "FAIL: pcs and pacemaker must be installed." >&2; exit 1; fi',
        'wait_online() { local end=$((SECONDS + 240)); while ((SECONDS < end)); do status="$(pcs status nodes 2>&1)"; online="$(sed -n \'s/.*Online:[[:space:]]*\\[\\(.*\\)\\].*/\\1/p\' <<<"${status}")"; found=0; for node in "${NODES[@]}"; do grep -qw -- "${node}" <<<"${online}" && found=$((found + 1)); done; ((found == EXPECTED_NODES)) && return 0; sleep 5; done; echo "${status}" >&2; return 1; }',
        'current_status="$(pcs status 2>&1 || true)"',
        'if grep -Fq "Cluster name: ${CLUSTER_NAME}" <<<"${current_status}"; then',
        '  echo "PASS: cluster ${CLUSTER_NAME} already exists; creation will not be repeated."',
        'elif ((EXECUTE_SETUP)); then',
        '  if grep -q "Cluster name:" <<<"${current_status}"; then echo "FAIL: a different cluster already exists; refusing to overwrite it." >&2; echo "${current_status}" >&2; exit 1; fi',
        '  pcs cluster setup "${CLUSTER_NAME}" --start "${NODES[@]}" || exit 1',
        'else',
        '  echo "Waiting for coordinator to create cluster ${CLUSTER_NAME}..."',
        'fi',
        'if ! wait_online; then echo "FAIL: not all expected nodes became online after cluster setup." >&2; exit 1; fi',
        'if ((EXECUTE_SETUP)); then',
        '  pcs cluster enable --all || exit 1',
        '  pcs cluster start --all || exit 1',
        '  pcs cluster stop --all || exit 1',
        '  pcs quorum update wait_for_all=1 || exit 1',
        '  pcs quorum config || exit 1',
        '  pcs cluster start --all || exit 1',
        'fi',
        'if ! wait_online; then echo "FAIL: not all expected nodes are online after final start." >&2; exit 1; fi',
        'quorum="$(pcs quorum status 2>&1)" || { echo "${quorum}" >&2; exit 1; }',
        'echo "${quorum}"',
        'grep -Eq "Quorate:[[:space:]]+Yes" <<<"${quorum}" || { echo "FAIL: cluster is not quorate." >&2; exit 1; }',
        'grep -Eq "WaitForAll:[[:space:]]+Enabled" <<<"${quorum}" || { echo "FAIL: WaitForAll is not enabled." >&2; exit 1; }',
        'actual_nodes="$(awk -F: \'/Expected votes:/ {gsub(/[[:space:]]/, "", $2); print $2}\' <<<"${quorum}")"',
        '[[ "${actual_nodes}" == "${EXPECTED_NODES}" ]] || { echo "FAIL: quorum reports ${actual_nodes:-unknown} expected votes, wanted ${EXPECTED_NODES}." >&2; exit 1; }',
        'echo "PASS: cluster ${CLUSTER_NAME} has ${EXPECTED_NODES} online nodes, quorum, and WaitForAll enabled."',
        'echo "=== Result: PASS — cluster base configuration verified ==="', "",
    ])
