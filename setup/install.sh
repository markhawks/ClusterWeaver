#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

app_dir="/var/www/html/ClusterWeaver"
service_user="clusterweaver"
service_group="clusterweaver"
environment_dir="/etc/clusterweaver"
environment_file="${environment_dir}/clusterweaver.env"
unit_file="/etc/systemd/system/clusterweaver-control.service"
open_firewall=1

usage() {
    echo "Usage: sudo ./setup/install.sh [--no-firewall]"
}

while (($#)); do
    case "$1" in
        --no-firewall) open_firewall=0 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

if [[ ${EUID} -ne 0 ]]; then
    echo "Run this installer as root." >&2
    exit 1
fi

source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [[ "${source_dir}" != "${app_dir}" ]]; then
    echo "ClusterWeaver must be checked out at ${app_dir}." >&2
    echo "Use setup/bootstrap.sh for a complete GitHub installation." >&2
    exit 1
fi

if [[ ! -r /etc/os-release ]]; then
    echo "Cannot identify this operating system." >&2
    exit 1
fi
source /etc/os-release
case "${ID:-}" in
    rhel|rocky|almalinux|centos) ;;
    *) echo "Unsupported operating system: ${PRETTY_NAME:-unknown}. Use RHEL or a compatible distribution." >&2; exit 1 ;;
esac

echo "Installing operating-system dependencies..."
dnf install -y git python3 python3-pip openssl curl

if ! getent group "${service_group}" >/dev/null; then
    groupadd --system "${service_group}"
fi
if ! id "${service_user}" >/dev/null 2>&1; then
    useradd --system --gid "${service_group}" --home-dir /var/lib/clusterweaver --create-home --shell /sbin/nologin "${service_user}"
fi

install -d -o "${service_user}" -g "${service_group}" -m 0755 "${app_dir}/data" "${app_dir}/data/projects"
install -d -o root -g "${service_group}" -m 0750 "${environment_dir}"

if [[ ! -f "${environment_file}" ]]; then
    secret_key="$(openssl rand -hex 32)"
    temporary_environment="$(mktemp)"
    trap 'rm -f "${temporary_environment:-}"' EXIT
    {
        echo "CLUSTERWEAVER_SECRET_KEY=${secret_key}"
        echo "CLUSTERWEAVER_LOGIN_USERNAME=admin"
        echo "CLUSTERWEAVER_LOGIN_PASSWORD=changeme"
        echo "CLUSTERWEAVER_DATABASE_URL=sqlite:////var/www/html/ClusterWeaver/data/clusterweaver.db"
        echo "CLUSTERWEAVER_PROJECTS_ROOT=/var/www/html/ClusterWeaver/data/projects"
        echo "CLUSTERWEAVER_SSH_BOOTSTRAP_PASSWORD="
    } >"${temporary_environment}"
    install -o root -g "${service_group}" -m 0640 "${temporary_environment}" "${environment_file}"
    echo "Created ${environment_file}."
else
    chown root:"${service_group}" "${environment_file}"
    chmod 0640 "${environment_file}"
    echo "Preserved existing ${environment_file}."
fi

service_was_active=0
if systemctl is-active --quiet clusterweaver-control.service; then
    service_was_active=1
    systemctl stop clusterweaver-control.service
    trap 'if ((service_was_active)); then systemctl start clusterweaver-control.service; fi; rm -f "${temporary_environment:-}"' EXIT
fi

echo "Creating the Python environment..."
python3 -m venv "${app_dir}/.venv"
"${app_dir}/.venv/bin/python" -m pip install --upgrade pip
"${app_dir}/.venv/bin/python" -m pip install -r "${app_dir}/requirements.txt"

chown -R "${service_user}:${service_group}" "${app_dir}/data"
cd "${app_dir}"
set -a
source "${environment_file}"
set +a
runuser -u "${service_user}" -- env \
    CLUSTERWEAVER_DATABASE_URL="${CLUSTERWEAVER_DATABASE_URL}" \
    CLUSTERWEAVER_PROJECTS_ROOT="${CLUSTERWEAVER_PROJECTS_ROOT}" \
    "${app_dir}/.venv/bin/alembic" upgrade head
find "${app_dir}/data" -maxdepth 1 -type f -name 'clusterweaver.db*' -exec chmod 0644 {} +

install -o root -g root -m 0644 "${app_dir}/deploy/clusterweaver-control.service" "${unit_file}"
systemctl daemon-reload
systemctl enable --now clusterweaver-control.service
service_was_active=0

if ((open_firewall)) && systemctl is-active --quiet firewalld; then
    firewall-cmd --permanent --add-port=5000/tcp
    firewall-cmd --reload
fi

"${app_dir}/setup/check.sh"
echo
echo "Installation complete: http://$(hostname -I | awk '{print $1}'):5000"
echo "Initial login: admin / changeme"
echo "Change the default password immediately from Configuration."
