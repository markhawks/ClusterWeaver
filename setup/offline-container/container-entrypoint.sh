#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

alembic upgrade head
find /var/lib/clusterweaver/data -maxdepth 1 -type f -name 'clusterweaver.db*' -exec chmod 0644 {} +
exec gunicorn --no-control-socket --workers 2 --timeout 150 --graceful-timeout 30 \
    --bind 0.0.0.0:5000 --access-logfile - --error-logfile - run:app

