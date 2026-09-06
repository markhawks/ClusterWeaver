#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

app_dir="/opt/clusterweaver/app"
venv_dir="/opt/clusterweaver/venv"
environment_file="/etc/clusterweaver/clusterweaver.env"

systemctl is-active --quiet clusterweaver-control.service
cd "${app_dir}"
set -a
source "${environment_file}"
set +a
current_revision="$("${venv_dir}/bin/alembic" current 2>/dev/null)"
head_revision="$("${venv_dir}/bin/alembic" heads 2>/dev/null | awk '{print $1}')"
if [[ "${current_revision}" != *"${head_revision}"* ]]; then
    echo "Database migration mismatch: current=${current_revision}, head=${head_revision}" >&2
    exit 1
fi
curl --fail --silent --show-error --max-time 10 http://127.0.0.1:5000/login >/dev/null
echo "ClusterWeaver check passed: service active, database current, login reachable."
