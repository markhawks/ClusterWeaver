#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

systemctl is-active --quiet clusterweaver.service
for attempt in {1..30}; do
    if curl --fail --silent --show-error --max-time 3 http://127.0.0.1:5000/login >/dev/null; then
        podman healthcheck run clusterweaver >/dev/null
        echo "ClusterWeaver container check passed."
        exit 0
    fi
    sleep 1
done
echo "ClusterWeaver did not become ready within 30 seconds." >&2
podman logs --tail 50 clusterweaver >&2 || true
exit 1

