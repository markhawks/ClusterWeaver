#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

purge=0
if [[ "${1:-}" == "--purge-data" ]]; then purge=1; shift; fi
if (($#)); then echo "Usage: sudo ./uninstall.sh [--purge-data]" >&2; exit 2; fi
if [[ ${EUID} -ne 0 ]]; then echo "Run this command as root." >&2; exit 1; fi

systemctl disable --now clusterweaver.service 2>/dev/null || true
rm -f /etc/containers/systemd/clusterweaver.container
systemctl daemon-reload
podman rm --force clusterweaver 2>/dev/null || true
if ((purge)); then
    archive="/var/lib/clusterweaver/purged-$(date -u +%Y%m%dT%H%M%SZ)"
    install -d -o root -g root -m 0700 "${archive}"
    [[ ! -e /var/lib/clusterweaver/data ]] || mv /var/lib/clusterweaver/data "${archive}/data"
    [[ ! -e /etc/clusterweaver ]] || mv /etc/clusterweaver "${archive}/configuration"
    echo "Data moved to ${archive}; remove it manually after verification."
else
    echo "Application removed; data and configuration were preserved."
fi

