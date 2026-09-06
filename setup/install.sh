#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

install_root="/opt/clusterweaver"; app_dir="${install_root}/app"; venv_dir="${install_root}/venv"
data_root="/var/lib/clusterweaver"; data_dir="${data_root}/data"; backup_dir="${data_root}/backups"
legacy_data_dir="/var/www/html/ClusterWeaver/data"
service_user="clusterweaver"; service_group="clusterweaver"
environment_dir="/etc/clusterweaver"; environment_file="${environment_dir}/clusterweaver.env"
unit_file="/etc/systemd/system/clusterweaver-control.service"
open_firewall=1; service_was_active=0; temporary_environment=""; stage_dir=""

cleanup() {
    [[ -z "${temporary_environment}" ]] || rm -f "${temporary_environment}"
    [[ -z "${stage_dir}" ]] || rm -rf "${stage_dir}"
    if ((service_was_active)); then systemctl start clusterweaver-control.service >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT
usage() { echo "Usage: sudo ./setup/install.sh [--no-firewall]"; }
while (($#)); do case "$1" in --no-firewall) open_firewall=0 ;; -h|--help) usage; exit 0 ;; *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;; esac; shift; done
if [[ ${EUID} -ne 0 ]]; then echo "Run this installer as root." >&2; exit 1; fi

source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
[[ -f "${source_dir}/clusterweaver/version.py" ]] || { echo "Invalid ClusterWeaver source tree." >&2; exit 1; }
source /etc/os-release
case "${ID:-}" in rhel|rocky|almalinux|centos) ;; *) echo "Unsupported OS: ${PRETTY_NAME:-unknown}." >&2; exit 1 ;; esac

dnf install -y git python3 python3-pip openssl curl
getent group "${service_group}" >/dev/null || groupadd --system "${service_group}"
id "${service_user}" >/dev/null 2>&1 || useradd --system --gid "${service_group}" --home-dir "${data_root}" --create-home --shell /sbin/nologin "${service_user}"
install -d -o root -g root -m 0755 "${install_root}" "${install_root}/previous"
install -d -o "${service_user}" -g "${service_group}" -m 0755 "${data_root}" "${data_dir}" "${data_dir}/projects"
install -d -o root -g root -m 0700 "${backup_dir}"
install -d -o root -g "${service_group}" -m 0750 "${environment_dir}"

if systemctl is-active --quiet clusterweaver-control.service; then service_was_active=1; systemctl stop clusterweaver-control.service; fi
if [[ ! -f "${data_dir}/clusterweaver.db" && -f "${legacy_data_dir}/clusterweaver.db" ]]; then
    echo "Migrating legacy data from ${legacy_data_dir} to ${data_dir}..."; cp -a "${legacy_data_dir}/." "${data_dir}/"
fi
if [[ -f "${data_dir}/clusterweaver.db" ]]; then
    backup_file="${backup_dir}/clusterweaver-$(date -u +%Y%m%dT%H%M%SZ).db"
    cp --preserve=timestamps "${data_dir}/clusterweaver.db" "${backup_file}"
    chown root:root "${backup_file}"
    chmod 0600 "${backup_file}"
fi

if [[ ! -f "${environment_file}" ]]; then
    temporary_environment="$(mktemp)"
    {
        echo "CLUSTERWEAVER_SECRET_KEY=$(openssl rand -hex 32)"; echo "CLUSTERWEAVER_LOGIN_USERNAME=admin"; echo "CLUSTERWEAVER_LOGIN_PASSWORD=changeme"
        echo "CLUSTERWEAVER_DATABASE_URL=sqlite:////var/lib/clusterweaver/data/clusterweaver.db"; echo "CLUSTERWEAVER_PROJECTS_ROOT=/var/lib/clusterweaver/data/projects"; echo "CLUSTERWEAVER_SSH_BOOTSTRAP_PASSWORD="
    } >"${temporary_environment}"
    install -o root -g "${service_group}" -m 0640 "${temporary_environment}" "${environment_file}"
else
    sed -i 's#sqlite:////var/www/html/ClusterWeaver/data/clusterweaver.db#sqlite:////var/lib/clusterweaver/data/clusterweaver.db#' "${environment_file}"
    sed -i 's#/var/www/html/ClusterWeaver/data/projects#/var/lib/clusterweaver/data/projects#' "${environment_file}"
    grep -q '^CLUSTERWEAVER_DATABASE_URL=' "${environment_file}" || echo 'CLUSTERWEAVER_DATABASE_URL=sqlite:////var/lib/clusterweaver/data/clusterweaver.db' >>"${environment_file}"
    grep -q '^CLUSTERWEAVER_PROJECTS_ROOT=' "${environment_file}" || echo 'CLUSTERWEAVER_PROJECTS_ROOT=/var/lib/clusterweaver/data/projects' >>"${environment_file}"
    chown root:"${service_group}" "${environment_file}"; chmod 0640 "${environment_file}"
fi

stage_dir="$(mktemp -d "${install_root}/.app-stage.XXXXXX")"
for path in clusterweaver cluster_templates migrations setup deploy; do cp -a "${source_dir}/${path}" "${stage_dir}/${path}"; done
for file in alembic.ini run.py config.py requirements.txt LICENSE README.md CHANGELOG.md SECURITY.md CONTRIBUTING.md; do [[ ! -e "${source_dir}/${file}" ]] || cp -a "${source_dir}/${file}" "${stage_dir}/${file}"; done
chown -R root:root "${stage_dir}"; chmod 0755 "${stage_dir}"
if [[ -d "${app_dir}" ]]; then mv "${app_dir}" "${install_root}/previous/app-$(date -u +%Y%m%dT%H%M%SZ)-$$"; fi
mv "${stage_dir}" "${app_dir}"; stage_dir=""

python3 -m venv "${venv_dir}"
"${venv_dir}/bin/python" -m pip install --upgrade pip
"${venv_dir}/bin/python" -m pip install -r "${app_dir}/requirements.txt"
chown -R "${service_user}:${service_group}" "${data_dir}"
chown root:root "${backup_dir}"; chmod 0700 "${backup_dir}"
cd "${app_dir}"; set -a; source "${environment_file}"; set +a
runuser -u "${service_user}" -- env CLUSTERWEAVER_DATABASE_URL="${CLUSTERWEAVER_DATABASE_URL}" CLUSTERWEAVER_PROJECTS_ROOT="${CLUSTERWEAVER_PROJECTS_ROOT}" "${venv_dir}/bin/alembic" upgrade head
find "${data_dir}" -maxdepth 1 -type f -name 'clusterweaver.db*' -exec chmod 0644 {} +
install -o root -g root -m 0644 "${app_dir}/deploy/clusterweaver-control.service" "${unit_file}"
systemctl daemon-reload; systemctl enable --now clusterweaver-control.service; service_was_active=0
if ((open_firewall)) && systemctl is-active --quiet firewalld; then firewall-cmd --permanent --add-port=5000/tcp; firewall-cmd --reload; fi
"${app_dir}/setup/check.sh"
echo "Installation complete: application=${app_dir}, data=${data_dir}"
echo "Initial login for an empty database: admin / changeme (change it immediately)."
