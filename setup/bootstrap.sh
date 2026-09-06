#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail
repository="https://github.com/markhawks/ClusterWeaver.git"; release_ref="${CLUSTERWEAVER_VERSION:-v0.1.5}"
if [[ ${EUID} -ne 0 ]]; then echo "Run this bootstrap as root." >&2; exit 1; fi
dnf install -y git
checkout_dir="$(mktemp -d)"; trap 'rm -rf "${checkout_dir}"' EXIT
git clone --branch "${release_ref}" --depth 1 "${repository}" "${checkout_dir}/ClusterWeaver"
"${checkout_dir}/ClusterWeaver/setup/install.sh" "$@"
