#!/usr/bin/env bash
set -o nounset
set -o pipefail

failures=0
warnings=0

pass() { printf 'PASS: %s\n' "$*"; }
info() { printf 'INFO: %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*"; warnings=$((warnings + 1)); }
fail() { printf 'FAIL: %s\n' "$*"; failures=$((failures + 1)); }

echo "=== ClusterWeaver RHEL 10.2 offline installation pre-flight ==="

if [[ ${EUID} -eq 0 ]]; then
    pass "running as root"
else
    fail "run this script as root (sudo ./preflight.sh)"
fi

if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    source /etc/os-release
    if [[ "${ID:-}" == "rhel" && "${VERSION_ID:-}" == "10.2" ]]; then
        pass "RHEL 10.2 detected (${PRETTY_NAME:-RHEL})"
    else
        fail "RHEL 10.2 is required; detected ${PRETTY_NAME:-unknown operating system}"
    fi
else
    fail "/etc/os-release is not readable"
fi

if [[ "$(uname -m)" == "x86_64" ]]; then
    pass "x86_64 architecture detected"
else
    fail "the offline bundle requires x86_64; detected $(uname -m)"
fi

if command -v systemctl >/dev/null 2>&1 && [[ "$(ps -p 1 -o comm= 2>/dev/null)" == "systemd" ]]; then
    pass "systemd is running"
else
    fail "systemd is required"
fi

if command -v subscription-manager >/dev/null 2>&1; then
    if subscription-manager identity >/dev/null 2>&1; then
        pass "Red Hat subscription/Satellite identity is available"
    else
        fail "subscription-manager cannot obtain the system identity"
    fi
else
    fail "subscription-manager is not installed"
fi

if command -v dnf >/dev/null 2>&1; then
    if dnf -q repolist --enabled 2>/dev/null | awk 'NR > 1 && NF { found=1 } END { exit !found }'; then
        pass "at least one enabled DNF repository is available"
    else
        fail "no enabled DNF repository is available"
    fi
    for package in container-tools openssl curl; do
        if rpm -q "${package}" >/dev/null 2>&1; then
            pass "${package} is already installed"
        elif dnf -q list --available "${package}" >/dev/null 2>&1; then
            pass "${package} is available from an enabled repository"
        else
            fail "${package} is neither installed nor available from enabled repositories"
        fi
    done
else
    fail "dnf is not installed"
fi

available_kib="$(df -Pk /var 2>/dev/null | awk 'NR == 2 { print $4 }')"
if [[ "${available_kib}" =~ ^[0-9]+$ ]]; then
    available_mib=$((available_kib / 1024))
    if ((available_kib >= 2097152)); then
        pass "/var has ${available_mib} MiB available (minimum 2048 MiB)"
    else
        fail "/var has only ${available_mib} MiB available; at least 2048 MiB is required"
    fi
else
    fail "unable to determine free space under /var"
fi

if command -v getenforce >/dev/null 2>&1; then
    selinux_state="$(getenforce 2>/dev/null || true)"
    if [[ "${selinux_state}" == "Enforcing" ]]; then
        pass "SELinux is enforcing"
    else
        warn "SELinux state is ${selinux_state:-unknown}; Enforcing is recommended and supported"
    fi
else
    warn "getenforce is unavailable; SELinux state could not be checked"
fi

if command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | awk 'NR > 1 && $4 ~ /:5000$/ { found=1 } END { exit !found }'; then
    if systemctl is-active --quiet clusterweaver.service 2>/dev/null || systemctl is-active --quiet clusterweaver-control.service 2>/dev/null; then
        pass "TCP port 5000 is already owned by an active ClusterWeaver service"
    else
        fail "TCP port 5000 is already in use"
    fi
else
    pass "TCP port 5000 is available"
fi

if command -v podman >/dev/null 2>&1; then
    pass "Podman is already installed ($(podman --version 2>/dev/null))"
else
    info "Podman is not installed yet; container-tools will provide it during installation"
fi

info "the installed portal will require inbound TCP/5000 from the administration LAN"
info "ClusterWeaver will require outbound TCP/22 access to the managed cluster nodes"
echo "=== Result: FAIL=${failures} WARNING=${warnings} ==="

if ((failures)); then
    echo "Pre-flight FAILED. Correct the failed checks before installation." >&2
    exit 1
fi
echo "Pre-flight PASSED. The server is ready for offline installation."
