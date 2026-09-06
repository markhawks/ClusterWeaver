#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "${repository_root}"
version="$(sed -n 's/__version__ = "\([^"]*\)"/\1/p' clusterweaver/version.py)"
image="localhost/clusterweaver:${version}"
output_dir="${1:-${repository_root}/dist}"
bundle_name="clusterweaver-${version}-linux-amd64-offline"
stage="$(mktemp -d)"
trap 'rm -rf "${stage}"' EXIT

if [[ "$(uname -m)" != "x86_64" ]]; then
    echo "Build this bundle on an x86_64 host." >&2
    exit 1
fi
command -v podman >/dev/null || { echo "podman is required." >&2; exit 1; }

mkdir -p "${output_dir}" "${stage}/${bundle_name}"
podman build --arch amd64 --format oci --pull=missing \
    --ignorefile setup/offline-container/containerignore \
    --tag "${image}" --file setup/offline-container/Containerfile .
podman save --format oci-archive --output "${stage}/${bundle_name}/clusterweaver-${version}.oci.tar" "${image}"
podman image inspect "${image}" >"${stage}/${bundle_name}/IMAGE-INSPECT.json"
podman run --rm --entrypoint python "${image}" -m pip freeze >"${stage}/${bundle_name}/PYTHON-PACKAGES.txt"
git rev-parse HEAD >"${stage}/${bundle_name}/SOURCE-COMMIT"

for file in install-offline.sh update-offline.sh uninstall.sh verify.sh clusterweaver.container clusterweaver.env.example README.md; do
    cp "setup/offline-container/${file}" "${stage}/${bundle_name}/${file}"
done
sed -i "s/localhost\/clusterweaver:[0-9][0-9.]*/localhost\/clusterweaver:${version}/" "${stage}/${bundle_name}/clusterweaver.container"
chmod 0755 "${stage}/${bundle_name}"/*.sh
(
    cd "${stage}/${bundle_name}"
    sha256sum clusterweaver-${version}.oci.tar clusterweaver.container clusterweaver.env.example \
        install-offline.sh update-offline.sh uninstall.sh verify.sh README.md \
        IMAGE-INSPECT.json PYTHON-PACKAGES.txt SOURCE-COMMIT >SHA256SUMS
)
tar -C "${stage}" -czf "${output_dir}/${bundle_name}.tar.gz" "${bundle_name}"
(
    cd "${output_dir}"
    sha256sum "${bundle_name}.tar.gz" >"${bundle_name}.tar.gz.sha256"
)
echo "Created ${output_dir}/${bundle_name}.tar.gz"
