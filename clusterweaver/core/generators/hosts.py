import shlex

from clusterweaver.core.models import ProjectData
from clusterweaver.core.validators import host_address


def generate_hosts_update(project: ProjectData) -> str:
    """Generate an idempotent /etc/hosts update for verified cluster nodenames."""
    release = f"{project.rhel_major}.{project.rhel_minor}"
    if release not in {"9.8", "10.2"}:
        return "\n".join([
            "#!/bin/bash", "", "set -o pipefail", "",
            shlex.join(["echo", f"/etc/hosts generation is not yet supported for RHEL {project.rhel_major}.{project.rhel_minor}."]),
            "exit 2", "",
        ])
    invalid = [node.hostname for node in project.nodes if not node.cluster_ip or not node.nodename]
    if invalid or not project.nodes:
        names = ", ".join(invalid) if invalid else "no nodes configured"
        return "\n".join([
            "#!/bin/bash", "", "set -o pipefail", "",
            shlex.join(["echo", f"Cannot generate /etc/hosts: missing private IP or nodename ({names})."]),
            "exit 2", "",
        ])

    nodes = sorted(project.nodes, key=lambda item: item.nodename.lower())
    ips = ",".join(host_address(node.cluster_ip) for node in nodes)
    names = ",".join(node.nodename for node in nodes)
    marker = f"ClusterWeaver {project.uuid}"
    lines = [
        "#!/bin/bash", "", "set -o pipefail", "",
        'HOSTS_FILE="/etc/hosts"', 'BACKUP_ROOT="/root/clusterweaver-backups/hosts"', f"MARKER={shlex.quote(marker)}", f"EXPECTED_RELEASE={shlex.quote(release)}", "",
        'if [[ ${EUID} -ne 0 ]]; then echo "FAIL: run this script as root." >&2; exit 1; fi',
        'if [[ ! -f "${HOSTS_FILE}" ]]; then echo "FAIL: ${HOSTS_FILE} does not exist." >&2; exit 1; fi',
        'if ! install -d -m 700 "${BACKUP_ROOT}"; then echo "FAIL: cannot create backup root ${BACKUP_ROOT}." >&2; exit 1; fi',
        'if ! BACKUP_DIR="$(mktemp -d "${BACKUP_ROOT}/$(date -u +%Y%m%dT%H%M%SZ)-$(hostname -s)-XXXXXX")"; then echo "FAIL: cannot create a unique backup directory." >&2; exit 1; fi',
        'chmod 700 "${BACKUP_DIR}"',
        'if ! cp -a "${HOSTS_FILE}" "${BACKUP_DIR}/hosts"; then echo "FAIL: cannot back up ${HOSTS_FILE}; no changes made." >&2; exit 1; fi',
        'if ! printf "hostname=%s\\nsource_file=%s\\nbackup_time_utc=%s\\nproject_marker=%s\\n" "$(hostname -s)" "${HOSTS_FILE}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${MARKER}" > "${BACKUP_DIR}/manifest.txt"; then echo "FAIL: cannot write backup manifest; no changes made." >&2; exit 1; fi',
        'chmod 600 "${BACKUP_DIR}/manifest.txt"',
        'echo "Backup created: ${BACKUP_DIR}/hosts"', "",
        'ACTUAL_RELEASE="$(. /etc/os-release 2>/dev/null; printf %s "${VERSION_ID:-unknown}")"',
        'if [[ "${ACTUAL_RELEASE}" != "${EXPECTED_RELEASE}" ]]; then echo "FAIL: detected release ${ACTUAL_RELEASE}, expected RHEL ${EXPECTED_RELEASE}." >&2; exit 1; fi',
        'echo "PASS: RHEL ${EXPECTED_RELEASE} detected."',
        'TEMP_FILE="$(mktemp /etc/hosts.clusterweaver.XXXXXX)"',
        'trap \'rm -f "${TEMP_FILE}"\' EXIT',
        f"MANAGED_IPS={shlex.quote(ips)}", f"MANAGED_NAMES={shlex.quote(names)}", "",
        "awk -v marker=\"${MARKER}\" -v ips=\"${MANAGED_IPS}\" -v names=\"${MANAGED_NAMES}\" '",
        'BEGIN { split(ips, ip_list, ","); for (i in ip_list) managed_ip[ip_list[i]]=1; split(names, name_list, ","); for (i in name_list) managed_name[name_list[i]]=1; in_block=0 }',
        '$0 == "# BEGIN " marker { in_block=1; next }',
        '$0 == "# END " marker { in_block=0; next }',
        'in_block { next }',
        '{ conflict=managed_ip[$1]; for (i=2; i<=NF; i++) if (managed_name[$i]) conflict=1; if (!conflict) print }',
        "' \"${HOSTS_FILE}\" > \"${TEMP_FILE}\"", "",
        '[[ -s "${TEMP_FILE}" ]] && [[ "$(tail -c 1 "${TEMP_FILE}" | wc -l)" -eq 0 ]] && echo >> "${TEMP_FILE}"',
        'echo "# BEGIN ${MARKER}" >> "${TEMP_FILE}"',
    ]
    lines.extend(shlex.join(["echo", f"{host_address(node.cluster_ip)} {node.nodename}"]) + ' >> "${TEMP_FILE}"' for node in nodes)
    lines.extend([
        'echo "# END ${MARKER}" >> "${TEMP_FILE}"',
        'chmod --reference="${HOSTS_FILE}" "${TEMP_FILE}"',
        'chown --reference="${HOSTS_FILE}" "${TEMP_FILE}"',
        'install -m "$(stat -c %a "${HOSTS_FILE}")" -o "$(stat -c %u "${HOSTS_FILE}")" -g "$(stat -c %g "${HOSTS_FILE}")" "${TEMP_FILE}" "${HOSTS_FILE}"',
        'echo "PASS: ${HOSTS_FILE} updated with ClusterWeaver node mappings."',
        'getent hosts ${MANAGED_NAMES//,/ } || true',
        'echo "=== /etc/hosts update complete ==="', "",
    ])
    return "\n".join(lines)
