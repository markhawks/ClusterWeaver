#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

app_dir="/var/www/html/ClusterWeaver"
environment_file="/etc/clusterweaver/clusterweaver.env"
target_ref="${1:-main}"

if [[ ${EUID} -ne 0 ]]; then
    echo "Run this updater as root." >&2
    exit 1
fi
if [[ ! -d "${app_dir}/.git" || ! -f "${environment_file}" ]]; then
    echo "ClusterWeaver is not installed at ${app_dir}." >&2
    exit 1
fi
if [[ -n "$(git -C "${app_dir}" status --porcelain)" ]]; then
    echo "Refusing to update a working tree with local changes." >&2
    exit 1
fi

systemctl stop clusterweaver-control.service
trap 'systemctl start clusterweaver-control.service >/dev/null 2>&1 || true' EXIT

backup_dir="/var/lib/clusterweaver/backups"
install -d -o root -g root -m 0700 "${backup_dir}"
if [[ -f "${app_dir}/data/clusterweaver.db" ]]; then
    cp --preserve=mode,timestamps "${app_dir}/data/clusterweaver.db" "${backup_dir}/clusterweaver-$(date -u +%Y%m%dT%H%M%SZ).db"
fi

git -C "${app_dir}" fetch --tags origin
if git -C "${app_dir}" show-ref --verify --quiet "refs/tags/${target_ref}"; then
    git -C "${app_dir}" checkout --detach "${target_ref}"
else
    git -C "${app_dir}" checkout main
    git -C "${app_dir}" merge --ff-only "origin/${target_ref}"
fi

"${app_dir}/.venv/bin/python" -m pip install -r "${app_dir}/requirements.txt"
cd "${app_dir}"
set -a
source "${environment_file}"
set +a
runuser -u clusterweaver -- env CLUSTERWEAVER_DATABASE_URL="${CLUSTERWEAVER_DATABASE_URL}" "${app_dir}/.venv/bin/alembic" upgrade head
find "${app_dir}/data" -maxdepth 1 -type f -name 'clusterweaver.db*' -exec chmod 0644 {} +
install -o root -g root -m 0644 "${app_dir}/deploy/clusterweaver-control.service" /etc/systemd/system/clusterweaver-control.service
systemctl daemon-reload
systemctl restart clusterweaver-control.service
"${app_dir}/setup/check.sh"
trap - EXIT
