# ClusterWeaver

Linux High Availability Cluster Builder & Lifecycle Manager.

Current release: **0.1.0**. Release history is maintained in `CHANGELOG.md` and is also available from the Changelog link in the web interface.

This first MVP manages RHEL 7, 9, and 10 cluster projects and nodes. It stores searchable state in SQLite, writes a human-readable YAML definition, versions project files in a local Git repository, and generates a reviewable pre-check script. RHEL 8 is deliberately unsupported.

## Development prerequisites

- RHEL 10.2 (canonical development/runtime environment)
- Python 3.12+
- Git
- `python3-pip`

On RHEL:

```bash
sudo dnf install git python3-pip
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Set a private session key outside source control:

```bash
export CLUSTERWEAVER_SECRET_KEY='replace-with-a-random-value'
```

The checked-in default is suitable only for local development.

## Database initialization and migration

```bash
source .venv/bin/activate
alembic upgrade head
```

SQLite is created at `data/clusterweaver.db`. This database is ignored by Git and is not the sole copy of project knowledge.

## Start the development server

```bash
source .venv/bin/activate
python run.py
```

Open `http://127.0.0.1:5000`. The development server listens on localhost only and is not a production deployment method.

To make the development server reachable from another machine on the same trusted network:

```bash
export CLUSTERWEAVER_HOST=0.0.0.0
python run.py
```

Then open `http://<vm-ip>:5000`. If `firewalld` is active, TCP port 5000 must also be allowed on the VM's active zone. Do not expose the Flask development server directly to an untrusted or public network.

## systemd service

The installed `clusterweaver-control.service` uses Gunicorn, runs as the unprivileged `clusterweaver` account, starts at boot, and reads its private configuration from `/etc/clusterweaver/clusterweaver.env`.

It can be managed directly with systemd:

```bash
systemctl status clusterweaver-control
systemctl start clusterweaver-control
systemctl stop clusterweaver-control
systemctl restart clusterweaver-control
systemctl reload clusterweaver-control
journalctl -u clusterweaver-control -f
```

Use the convenience script:

```bash
./scripts/clusterweaver-control start
./scripts/clusterweaver-control stop
./scripts/clusterweaver-control restart
./scripts/clusterweaver-control reload
./scripts/clusterweaver-control status
./scripts/clusterweaver-control logs
```

`reload` applies Python/template changes gracefully. Static assets normally require only a browser refresh. After changing dependencies or the unit file, use `restart`.

## Run tests

```bash
source .venv/bin/activate
pytest
```

Tests use isolated temporary databases and project repositories; they do not contact or execute commands on cluster nodes.

## Runtime data

Each project is written to:

```text
data/projects/<project-slug>/project.yaml
```

`data/projects/` is initialized as a separate local Git repository. Meaningful YAML changes create commits; SQLite databases, logs, and secret YAML files are ignored. Generated commands are displayed for review and are never executed by ClusterWeaver.

Configuration can be overridden with:

- `CLUSTERWEAVER_SECRET_KEY`
- `CLUSTERWEAVER_DATABASE_URL`
- `CLUSTERWEAVER_PROJECTS_ROOT`
- `CLUSTERWEAVER_HOST` (defaults to `127.0.0.1`)
- `CLUSTERWEAVER_PORT` (defaults to `5000`)
- `CLUSTERWEAVER_DEBUG` (defaults to disabled)

## Directory layout

```text
clusterweaver/
├── core/          # framework-independent models, validation, generators, serializers, services
├── persistence/   # SQLAlchemy records and repositories
├── web/           # Flask application, routes, forms, templates, static assets
└── cli/           # reserved for the future CLI
cluster_templates/ # isolated RHEL 7, 9, and 10 templates
data/              # SQLite state and Git-versioned project definitions
migrations/        # Alembic schema history
tests/             # unit and web integration tests
```

The MVP intentionally excludes Pacemaker configuration, storage, STONITH, Ansible, SSH execution, and RHEL 8 support.
