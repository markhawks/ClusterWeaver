#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

install_root="/opt/clusterweaver"
app_dir="${install_root}/app"
venv_dir="${install_root}/venv"
previous_dir="${install_root}/previous"
data_dir="/var/lib/clusterweaver/data"
backup_dir="/var/lib/clusterweaver/backups"
database_file="${data_dir}/clusterweaver.db"
environment_file="/etc/clusterweaver/clusterweaver.env"
unit_file="/etc/systemd/system/clusterweaver-control.service"
service="clusterweaver-control.service"
service_user="clusterweaver"
service_group="clusterweaver"

stage_app=""
stage_venv=""
old_app=""
old_venv=""
database_backup=""
rollback_ready=0
service_was_active=0

if [[ ${EUID} -ne 0 ]]; then
    echo "Run this updater as root." >&2
    exit 1
fi

source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
[[ -f "${source_dir}/clusterweaver/version.py" ]] || { echo "Invalid ClusterWeaver source tree." >&2; exit 1; }
[[ -d "${app_dir}" && -x "${venv_dir}/bin/python" ]] || { echo "Native installation not found; run ./setup/install.sh first." >&2; exit 1; }
[[ -f "${environment_file}" ]] || { echo "Missing ${environment_file}." >&2; exit 1; }
[[ -f "${database_file}" ]] || { echo "Missing ${database_file}." >&2; exit 1; }

timestamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
install -d -o root -g root -m 0755 "${previous_dir}"
install -d -o root -g root -m 0700 "${backup_dir}"
stage_app="$(mktemp -d "${install_root}/.app-update.XXXXXX")"

finish() {
    result=$?
    trap - EXIT
    if ((result != 0 && rollback_ready)); then
        echo "Update failed; restoring the previous application and database." >&2
        systemctl stop "${service}" >/dev/null 2>&1 || true
        if [[ -n "${old_app}" && -d "${old_app}" ]]; then
            [[ ! -d "${app_dir}" ]] || mv "${app_dir}" "${previous_dir}/failed-app-${timestamp}"
            mv "${old_app}" "${app_dir}"
        fi
        if [[ -n "${old_venv}" && -d "${old_venv}" ]]; then
            [[ ! -d "${venv_dir}" ]] || mv "${venv_dir}" "${previous_dir}/failed-venv-${timestamp}"
            mv "${old_venv}" "${venv_dir}"
        fi
        for suffix in "" "-wal" "-shm"; do
            if [[ -e "${database_file}${suffix}" ]]; then
                mv "${database_file}${suffix}" "${backup_dir}/failed-clusterweaver-${timestamp}.db${suffix}"
            fi
        done
        cp --preserve=timestamps "${database_backup}" "${database_file}"
        chown "${service_user}:${service_group}" "${database_file}"
        chmod 0644 "${database_file}"
        if [[ -f "${app_dir}/deploy/clusterweaver-control.service" ]]; then
            install -o root -g root -m 0644 "${app_dir}/deploy/clusterweaver-control.service" "${unit_file}"
        fi
        systemctl daemon-reload
        if ((service_was_active)); then systemctl start "${service}" || true; fi
    fi
    [[ -z "${stage_app}" || ! -d "${stage_app}" ]] || rm -rf "${stage_app}"
    [[ -z "${stage_venv}" || ! -d "${stage_venv}" ]] || rm -rf "${stage_venv}"
    exit "${result}"
}
trap finish EXIT

for path in clusterweaver cluster_templates migrations setup deploy; do
    cp -a "${source_dir}/${path}" "${stage_app}/${path}"
done
for file in alembic.ini run.py config.py requirements.txt LICENSE README.md CHANGELOG.md SECURITY.md CONTRIBUTING.md; do
    [[ ! -e "${source_dir}/${file}" ]] || cp -a "${source_dir}/${file}" "${stage_app}/${file}"
done
chown -R root:root "${stage_app}"
chmod 0755 "${stage_app}"

requirements_changed=0
if ! cmp -s "${source_dir}/requirements.txt" "${app_dir}/requirements.txt"; then
    requirements_changed=1
    stage_venv="$(mktemp -d "${install_root}/.venv-update.XXXXXX")"
    rmdir "${stage_venv}"
    python3 -m venv "${stage_venv}"
    "${stage_venv}/bin/python" -m pip install --upgrade pip
    "${stage_venv}/bin/python" -m pip install -r "${source_dir}/requirements.txt"
fi

if systemctl is-active --quiet "${service}"; then
    service_was_active=1
    systemctl stop "${service}"
fi

database_backup="${backup_dir}/clusterweaver-${timestamp}.db"
cp --preserve=timestamps "${database_file}" "${database_backup}"
chown root:root "${database_backup}"
chmod 0600 "${database_backup}"
rollback_ready=1

old_app="${previous_dir}/app-${timestamp}"
mv "${app_dir}" "${old_app}"
mv "${stage_app}" "${app_dir}"
stage_app=""

if ((requirements_changed)); then
    old_venv="${previous_dir}/venv-${timestamp}"
    mv "${venv_dir}" "${old_venv}"
    mv "${stage_venv}" "${venv_dir}"
    stage_venv=""
fi

cd "${app_dir}"
set -a
# shellcheck disable=SC1090
source "${environment_file}"
set +a
runuser -u "${service_user}" -- env \
    CLUSTERWEAVER_DATABASE_URL="${CLUSTERWEAVER_DATABASE_URL}" \
    CLUSTERWEAVER_PROJECTS_ROOT="${CLUSTERWEAVER_PROJECTS_ROOT}" \
    "${venv_dir}/bin/alembic" upgrade head

find "${data_dir}" -maxdepth 1 -type f -name 'clusterweaver.db*' -exec chmod 0644 {} +
install -o root -g root -m 0644 "${app_dir}/deploy/clusterweaver-control.service" "${unit_file}"
systemctl daemon-reload
systemctl start "${service}"
"${app_dir}/setup/check.sh"

rollback_ready=0
echo "Local update complete: source=${source_dir}, application=${app_dir}"
echo "Database backup: ${database_backup}"
if ((requirements_changed)); then
    echo "Python dependencies changed; a new virtual environment was installed."
else
    echo "Python dependencies unchanged; the existing virtual environment was reused."
fi
