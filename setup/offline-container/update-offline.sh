#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

bundle_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
data_dir="/var/lib/clusterweaver/data"
backup_dir="/var/lib/clusterweaver/backups"

if [[ ${EUID} -ne 0 ]]; then echo "Run this updater as root." >&2; exit 1; fi
cd "${bundle_dir}"
sha256sum --check SHA256SUMS
archive="$(find "${bundle_dir}" -maxdepth 1 -type f -name 'clusterweaver-*.oci.tar' -print -quit)"
[[ -n "${archive}" ]] || { echo "OCI image archive not found." >&2; exit 1; }

systemctl stop clusterweaver.service
trap 'systemctl start clusterweaver.service >/dev/null 2>&1 || true' EXIT
install -d -o root -g root -m 0700 "${backup_dir}"
if [[ -f "${data_dir}/clusterweaver.db" ]]; then
    cp --preserve=mode,timestamps "${data_dir}/clusterweaver.db" "${backup_dir}/clusterweaver-$(date -u +%Y%m%dT%H%M%SZ).db"
fi
podman load --input "${archive}"
install -o root -g root -m 0644 clusterweaver.container /etc/containers/systemd/clusterweaver.container
systemctl daemon-reload
systemctl start clusterweaver.service
"${bundle_dir}/verify.sh"
trap - EXIT

