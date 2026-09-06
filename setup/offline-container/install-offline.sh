#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

bundle_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
environment_dir="/etc/clusterweaver"
environment_file="${environment_dir}/clusterweaver.env"
data_dir="/var/lib/clusterweaver/data"
quadlet_dir="/etc/containers/systemd"
open_firewall=1

if [[ "${1:-}" == "--no-firewall" ]]; then open_firewall=0; shift; fi
if (($#)); then echo "Usage: sudo ./install-offline.sh [--no-firewall]" >&2; exit 2; fi
if [[ ${EUID} -ne 0 ]]; then echo "Run this installer as root." >&2; exit 1; fi
source /etc/os-release
[[ "${VERSION_ID%%.*}" == "10" ]] || { echo "RHEL 10 or a compatible version is required." >&2; exit 1; }
[[ "$(uname -m)" == "x86_64" ]] || { echo "This bundle requires x86_64." >&2; exit 1; }

cd "${bundle_dir}"
sha256sum --check SHA256SUMS
dnf install -y container-tools openssl curl
archive="$(find "${bundle_dir}" -maxdepth 1 -type f -name 'clusterweaver-*.oci.tar' -print -quit)"
[[ -n "${archive}" ]] || { echo "OCI image archive not found." >&2; exit 1; }
podman load --input "${archive}"

install -d -o 10001 -g 10001 -m 0755 "${data_dir}" "${data_dir}/projects"
install -d -o root -g root -m 0755 "${quadlet_dir}"
install -d -o root -g root -m 0750 "${environment_dir}"
if [[ ! -f "${environment_file}" ]]; then
    secret_key="$(openssl rand -hex 32)"
    temporary_environment="$(mktemp)"
    trap 'rm -f "${temporary_environment:-}"' EXIT
    sed "s/GENERATED_BY_INSTALLER/${secret_key}/" clusterweaver.env.example >"${temporary_environment}"
    install -o root -g root -m 0600 "${temporary_environment}" "${environment_file}"
else
    chmod 0600 "${environment_file}"
    echo "Preserved existing ${environment_file}."
fi
install -o root -g root -m 0644 clusterweaver.container "${quadlet_dir}/clusterweaver.container"
systemctl daemon-reload
systemctl enable --now clusterweaver.service

if ((open_firewall)) && systemctl is-active --quiet firewalld; then
    firewall-cmd --permanent --add-port=5000/tcp
    firewall-cmd --reload
fi

"${bundle_dir}/verify.sh"
echo "Installation complete. Initial login for an empty database: admin / changeme"
echo "Change the password immediately from Configuration."

