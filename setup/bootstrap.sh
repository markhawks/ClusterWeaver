#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

repository="https://github.com/markhawks/ClusterWeaver.git"
app_dir="/var/www/html/ClusterWeaver"
release_ref="${CLUSTERWEAVER_VERSION:-v0.1.4}"

if [[ ${EUID} -ne 0 ]]; then
    echo "Run this bootstrap as root." >&2
    exit 1
fi
if [[ -e "${app_dir}" ]]; then
    echo "Refusing to overwrite existing path ${app_dir}." >&2
    exit 1
fi

dnf install -y git
install -d -o root -g root -m 0755 "$(dirname "${app_dir}")"
git clone --branch "${release_ref}" --depth 1 "${repository}" "${app_dir}"
exec "${app_dir}/setup/install.sh" "$@"
