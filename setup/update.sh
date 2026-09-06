#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail
repository="https://github.com/markhawks/ClusterWeaver.git"; target_ref="${1:-v0.1.6}"
if [[ ${EUID} -ne 0 ]]; then echo "Run this updater as root." >&2; exit 1; fi
dnf install -y git
checkout_dir="$(mktemp -d)"; trap 'rm -rf "${checkout_dir}"' EXIT
git clone --branch "${target_ref}" --depth 1 "${repository}" "${checkout_dir}/ClusterWeaver"
"${checkout_dir}/ClusterWeaver/setup/install.sh"
