import shlex

from clusterweaver.core.models import ProjectData


def generate_pcsd_auth(project: ProjectData) -> str:
    """Generate pcsd activation, hacluster password setup, and full peer authorization."""
    names = [node.nodename for node in sorted(project.nodes, key=lambda item: item.nodename.lower()) if node.nodename]
    if not names or len(names) != len(project.nodes):
        return "#!/bin/bash\n\necho 'FAIL: every node requires a cluster nodename before step 06.' >&2\nexit 2\n"
    quoted_names = " ".join(shlex.quote(name) for name in names)
    return "\n".join([
        "#!/bin/bash", "", "set -o pipefail", "",
        "HACLUSTER_PASSWORD='ricciolone'",
        f"CLUSTER_NODES=({quoted_names})", "",
        'if [[ ${EUID} -ne 0 ]]; then echo "FAIL: run this script as root." >&2; exit 1; fi',
        'if ! rpm -q pcs >/dev/null 2>&1; then echo "FAIL: pcs is not installed; complete step 05 first." >&2; exit 1; fi',
        'if ! systemctl enable --now pcsd.service; then echo "FAIL: unable to enable and start pcsd.service." >&2; exit 1; fi',
        'if ! systemctl is-enabled --quiet pcsd.service; then echo "FAIL: pcsd.service is not enabled at boot." >&2; systemctl status pcsd.service --no-pager -l || true; exit 1; fi',
        'if ! systemctl is-active --quiet pcsd.service; then echo "FAIL: pcsd.service is not active." >&2; systemctl status pcsd.service --no-pager -l || true; exit 1; fi',
        'systemctl status pcsd.service --no-pager -l',
        'echo "PASS: pcsd.service is enabled and active."',
        'if ! printf "%s\\n" "${HACLUSTER_PASSWORD}" | passwd --stdin hacluster; then echo "FAIL: unable to set the hacluster password." >&2; exit 1; fi',
        'echo "PASS: hacluster password configured."',
        'if ! pcs host auth "${CLUSTER_NODES[@]}" -u hacluster -p "${HACLUSTER_PASSWORD}"; then echo "FAIL: pcs host authentication failed." >&2; exit 1; fi',
        'echo "PASS: pcs host authentication completed for ${CLUSTER_NODES[*]}."',
        'echo "=== Result: PASS — pcsd and host authentication configured ==="', "",
    ])
