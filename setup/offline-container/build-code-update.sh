#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "${repository_root}"
version="$(sed -n 's/__version__ = "\([^"]*\)"/\1/p' clusterweaver/version.py)"
image="${CLUSTERWEAVER_UPDATE_BASE_IMAGE:-localhost/clusterweaver:${version}}"
output_dir="${repository_root}/dist"
usage() { echo "Usage: $0 [--base-image IMAGE] [--output-dir DIRECTORY]"; }
while (($#)); do
    case "$1" in
        --base-image) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; image="$2"; shift ;;
        --output-dir) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; output_dir="$2"; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done
stage="$(mktemp -d)"
trap 'rm -rf "${stage}"' EXIT

command -v podman >/dev/null || { echo "podman is required." >&2; exit 1; }
podman image exists "${image}" || { echo "Base image ${image} is not available; build the full offline bundle first." >&2; exit 1; }

# A code-only update may carry a newer application version, but is safe only when
# the selected installed base image already satisfies all runtime requirements.
podman run --rm --entrypoint /opt/clusterweaver-venv/bin/pip \
    --volume "${repository_root}/setup/offline-container/requirements-runtime.txt:/tmp/clusterweaver-requirements.txt:ro,Z" \
    "${image}" install --dry-run --no-index --requirement /tmp/clusterweaver-requirements.txt >/dev/null || {
        echo "Runtime dependencies changed; create a full offline bundle instead of a .cwu update." >&2
        exit 1
    }

commit="$(git rev-parse HEAD)"
dirty="false"
git diff --quiet && git diff --cached --quiet || dirty="true"
build_id="${version}-$(date -u +%Y%m%dT%H%M%SZ)-$(printf '%s' "${commit}" | cut -c1-12)"
package_name="clusterweaver-${build_id}.cwu"
package_root="${stage}/package"
app_root="${package_root}/app"
mkdir -p "${app_root}" "${output_dir}"

for path in clusterweaver cluster_templates migrations; do cp -a "${repository_root}/${path}" "${app_root}/${path}"; done
for file in alembic.ini run.py config.py requirements.txt LICENSE README.md CHANGELOG.md SECURITY.md CONTRIBUTING.md; do
    [[ ! -e "${repository_root}/${file}" ]] || cp -a "${repository_root}/${file}" "${app_root}/${file}"
done
find "${app_root}" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
find "${app_root}" -type d -name __pycache__ -empty -delete
find "${app_root}" -type d -exec chmod 0755 {} +
find "${app_root}" -type f -exec chmod 0644 {} +

base_image_id="$(podman image inspect --format '{{.Id}}' "${image}")"
requirements_sha="$(sha256sum setup/offline-container/requirements-runtime.txt | awk '{print $1}')"
cat >"${package_root}/manifest.env" <<EOF
FORMAT=clusterweaver-code-update
FORMAT_VERSION=1
APP_VERSION=${version}
BUILD_ID=${build_id}
BASE_IMAGE=${image}
BASE_IMAGE_ID=${base_image_id}
REQUIREMENTS_SHA256=${requirements_sha}
SOURCE_COMMIT=${commit}
SOURCE_DIRTY=${dirty}
EOF
(
    cd "${package_root}"
    find app -type f -print0 | sort -z | xargs -0 sha256sum >CHECKSUMS.sha256
    sha256sum manifest.env >>CHECKSUMS.sha256
)
tar -C "${package_root}" -czf "${output_dir}/${package_name}" manifest.env CHECKSUMS.sha256 app
(
    cd "${output_dir}"
    sha256sum "${package_name}" >"${package_name}.sha256"
)
cp setup/offline-container/update-code.sh "${output_dir}/clusterweaver-update"
chmod 0755 "${output_dir}/clusterweaver-update"
(
    cd "${output_dir}"
    sha256sum clusterweaver-update >clusterweaver-update.sha256
)
echo "Created ${output_dir}/${package_name}"
echo "Transfer ${package_name}, ${package_name}.sha256, clusterweaver-update, and clusterweaver-update.sha256."
