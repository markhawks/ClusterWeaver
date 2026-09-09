import shlex

from clusterweaver.core.models import ProjectData


PACKAGES = ("pcs", "pacemaker", "fence-agents-all", "pcp-zeroconf")


def generate_package_install(project: ProjectData) -> str:
    """Generate an idempotent base cluster package installation and verification script."""
    release = f"{project.rhel_major}.{project.rhel_minor}"
    installer = "osupdate" if project.customer.strip().casefold() == "mps" else "dnf"
    packages = " ".join(shlex.quote(package) for package in PACKAGES)
    return "\n".join([
        "#!/bin/bash", "", "set -o pipefail", "",
        f"EXPECTED_RELEASE={shlex.quote(release)}",
        f"INSTALLER={shlex.quote(installer)}",
        f"PACKAGES=({packages})", "",
        'if [[ ${EUID} -ne 0 ]]; then echo "FAIL: run this script as root." >&2; exit 1; fi',
        'ACTUAL_RELEASE="$(. /etc/os-release 2>/dev/null; printf %s "${VERSION_ID:-unknown}")"',
        'if [[ "${ACTUAL_RELEASE%%.*}" != "${EXPECTED_RELEASE%%.*}" ]]; then echo "FAIL: detected RHEL ${ACTUAL_RELEASE}, expected major release ${EXPECTED_RELEASE%%.*}." >&2; exit 1; fi',
        'if ! command -v "${INSTALLER}" >/dev/null 2>&1; then echo "FAIL: required installer ${INSTALLER} was not found." >&2; exit 1; fi',
        'missing=0; for package in "${PACKAGES[@]}"; do rpm -q "${package}" >/dev/null 2>&1 || missing=1; done',
        'if ((missing)); then',
        '  echo "Installing base cluster packages with ${INSTALLER}..."',
        '  "${INSTALLER}" install "${PACKAGES[@]}" -y',
        '  install_status=$?',
        'else',
        '  echo "PASS: all base cluster packages are already installed; no installation required."',
        '  install_status=0',
        'fi',
        'failures=0',
        'for package in "${PACKAGES[@]}"; do',
        '  if rpm -q "${package}"; then echo "PASS: ${package} is installed."; else echo "FAIL: ${package} is not installed." >&2; failures=$((failures + 1)); fi',
        'done',
        'if ((install_status != 0 || failures != 0)); then echo "=== Result: FAIL installer=${install_status} packages=${failures} ===" >&2; exit 1; fi',
        'echo "=== Result: PASS — base cluster packages verified ==="', "",
    ])
