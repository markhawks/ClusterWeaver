#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

service="clusterweaver.service"
quadlet="/etc/containers/systemd/clusterweaver.container"
install_root="/opt/clusterweaver"
live_dir="${install_root}/live"
releases_dir="${install_root}/releases"
data_dir="/var/lib/clusterweaver/data"
backup_dir="/var/lib/clusterweaver/backups"
database_file="${data_dir}/clusterweaver.db"
stage=""
old_live=""
database_backup=""
quadlet_backup=""
rollback_ready=0
service_was_active=0
operation_id=""

usage() { echo "Usage: clusterweaver-update <clusterweaver-update.cwu>"; }
[[ ${EUID} -eq 0 ]] || { echo "Run this updater as root." >&2; exit 1; }
[[ $# -eq 1 ]] || { usage >&2; exit 2; }
archive="$(readlink -f "$1")"
checksum_file="${archive}.sha256"
[[ -f "${archive}" && -f "${checksum_file}" ]] || { echo "The .cwu archive and adjacent .sha256 file are required." >&2; exit 1; }
[[ -f "${quadlet}" ]] || { echo "ClusterWeaver Quadlet not found at ${quadlet}." >&2; exit 1; }

expected_checksum="$(awk 'NR == 1 {print $1}' "${checksum_file}")"
[[ "${expected_checksum}" =~ ^[0-9a-f]{64}$ ]] || { echo "Invalid update checksum file." >&2; exit 1; }
actual_checksum="$(sha256sum "${archive}" | awk '{print $1}')"
[[ "${actual_checksum}" == "${expected_checksum}" ]] || { echo "Code update checksum verification failed." >&2; exit 1; }
archive_size="$(stat -c %s "${archive}")"
((archive_size > 0 && archive_size <= 33554432)) || { echo "Code update archive is empty or exceeds 32 MiB." >&2; exit 1; }

install -d -o root -g root -m 0755 "${install_root}" "${releases_dir}"
install -d -o root -g root -m 0700 "${backup_dir}"
stage="$(mktemp -d "${install_root}/.code-update.XXXXXX")"

finish() {
    result=$?
    trap - EXIT
    if ((result != 0 && rollback_ready)); then
        echo "Code update failed; restoring the previous code, database, and Quadlet." >&2
        systemctl stop "${service}" >/dev/null 2>&1 || true
        [[ ! -d "${live_dir}" ]] || mv "${live_dir}" "${releases_dir}/failed-${operation_id}"
        if [[ -n "${old_live}" && -d "${old_live}" ]]; then mv "${old_live}" "${live_dir}"; fi
        install -o root -g root -m 0644 "${quadlet_backup}" "${quadlet}"
        if [[ -n "${database_backup}" && -f "${database_backup}" ]]; then
            for suffix in "" "-wal" "-shm"; do
                [[ ! -e "${database_file}${suffix}" ]] || mv "${database_file}${suffix}" "${backup_dir}/failed-${operation_id}.db${suffix}"
            done
            cp --preserve=timestamps "${database_backup}" "${database_file}"
            chown 10001:10001 "${database_file}"
            chmod 0644 "${database_file}"
        fi
        systemctl daemon-reload
        if ((service_was_active)); then systemctl start "${service}" || true; fi
    fi
    [[ -z "${stage}" || ! -d "${stage}" ]] || rm -rf "${stage}"
    exit "${result}"
}
trap finish EXIT

while IFS= read -r member; do
    case "/${member}/" in
        *"/../"*|*"/./"*|"//"*) echo "Unsafe path in code update archive: ${member}" >&2; exit 1 ;;
    esac
    case "${member}" in manifest.env|CHECKSUMS.sha256|app|app/*) ;; *) echo "Unsupported file in code update archive: ${member}" >&2; exit 1 ;; esac
done < <(tar -tzf "${archive}")
tar -xzf "${archive}" --no-same-owner --no-same-permissions -C "${stage}"
if find "${stage}" -type l -o -type b -o -type c -o -type p -o -type s | grep -q .; then
    echo "The code update contains unsupported filesystem objects." >&2
    exit 1
fi
(
    cd "${stage}"
    sha256sum --check CHECKSUMS.sha256
)

manifest_value() {
    key="$1"
    value="$(sed -n "s/^${key}=//p" "${stage}/manifest.env")"
    [[ -n "${value}" && "$(grep -c "^${key}=" "${stage}/manifest.env")" -eq 1 ]] || { echo "Missing or duplicate ${key} in update manifest." >&2; exit 1; }
    printf '%s' "${value}"
}
[[ "$(manifest_value FORMAT)" == "clusterweaver-code-update" && "$(manifest_value FORMAT_VERSION)" == "1" ]] || { echo "Unsupported code update format." >&2; exit 1; }
build_id="$(manifest_value BUILD_ID)"
[[ "${build_id}" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "Invalid build identifier." >&2; exit 1; }
operation_id="${build_id}-$(date -u +%Y%m%dT%H%M%SZ)-$$"
app_version="$(manifest_value APP_VERSION)"
[[ "${app_version}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Invalid application version in update manifest." >&2; exit 1; }
base_image="$(manifest_value BASE_IMAGE)"
base_image_id="$(manifest_value BASE_IMAGE_ID)"
[[ "${base_image}" =~ ^localhost/clusterweaver:[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Invalid base image in update manifest." >&2; exit 1; }
installed_image_id="$(podman image inspect --format '{{.Id}}' "${base_image}" 2>/dev/null || true)"
[[ -n "${installed_image_id}" && "${installed_image_id}" == "${base_image_id}" ]] || {
    echo "This .cwu requires base image ${base_image} (${base_image_id}); install the matching full bundle." >&2
    exit 1
}
[[ -f "${stage}/app/run.py" && -f "${stage}/app/alembic.ini" && -d "${stage}/app/clusterweaver" && -d "${stage}/app/migrations" ]] || { echo "Incomplete application payload." >&2; exit 1; }

if systemctl is-active --quiet "${service}"; then service_was_active=1; fi
systemctl stop "${service}"
quadlet_backup="${backup_dir}/clusterweaver-${operation_id}.container"
cp --preserve=mode,timestamps "${quadlet}" "${quadlet_backup}"
if [[ -f "${database_file}" ]]; then
    database_backup="${backup_dir}/clusterweaver-${operation_id}.db"
    cp --preserve=timestamps "${database_file}" "${database_backup}"
    chown root:root "${database_backup}"
    chmod 0600 "${database_backup}"
fi
rollback_ready=1

if [[ -d "${live_dir}" ]]; then
    old_live="${releases_dir}/code-$(date -u +%Y%m%dT%H%M%SZ)-$$"
    mv "${live_dir}" "${old_live}"
fi
mv "${stage}/app" "${live_dir}"
chown -R root:root "${live_dir}"
find "${live_dir}" -type d -exec chmod 0755 {} +
find "${live_dir}" -type f -exec chmod 0644 {} +

if ! grep -q '^Volume=/opt/clusterweaver/live:/opt/clusterweaver/app:ro,Z$' "${quadlet}"; then
    sed -i '\#^Volume=/var/lib/clusterweaver/data:/var/lib/clusterweaver/data:Z$#a Volume=/opt/clusterweaver/live:/opt/clusterweaver/app:ro,Z' "${quadlet}"
fi
grep -q '^Volume=/opt/clusterweaver/live:/opt/clusterweaver/app:ro,Z$' "${quadlet}" || { echo "Unable to activate the code mount in ${quadlet}." >&2; exit 1; }
systemctl daemon-reload
systemctl start "${service}"

ready=0
for _attempt in {1..30}; do
    if curl --fail --silent --max-time 3 http://127.0.0.1:5000/login >/dev/null 2>&1 && podman healthcheck run clusterweaver >/dev/null 2>&1; then
        ready=1
        break
    fi
    sleep 1
done
((ready)) || { podman logs --tail 50 clusterweaver >&2 || true; echo "ClusterWeaver did not become healthy after the code update." >&2; exit 1; }

rollback_ready=0
echo "ClusterWeaver code update ${build_id} installed successfully."
echo "Database backup: ${database_backup:-not required (empty database)}"
