# Automated setup

These scripts install ClusterWeaver on RHEL or a compatible distribution using `/opt/clusterweaver` for application code, `/etc/clusterweaver` for configuration, and `/var/lib/clusterweaver` for state and backups. Commands must run as root.

## Complete installation from GitHub

Download `bootstrap.sh` onto an empty server and run:

```bash
curl --fail --location --output bootstrap.sh https://raw.githubusercontent.com/markhawks/ClusterWeaver/v0.1.5/setup/bootstrap.sh
chmod 755 bootstrap.sh
sudo bash bootstrap.sh
```

It installs Git into the staging environment, checks out release `v0.1.5` in a temporary directory, deploys the application under `/opt`, and removes the temporary checkout. Override the release with `CLUSTERWEAVER_VERSION`.

## Installation from an existing checkout

```bash
cd /path/to/ClusterWeaver
sudo ./setup/install.sh
```

Use `--no-firewall` to leave firewalld unchanged. By default, port `5000/tcp` is opened only when firewalld is already running.

The installer:

1. validates the operating system and installation path;
2. installs OS and Python prerequisites;
3. creates the unprivileged `clusterweaver` service account;
4. generates a private Flask session key and protected environment file;
5. creates the virtual environment and installs pinned-compatible dependencies;
6. creates or upgrades the SQLite database;
7. installs and starts the hardened Gunicorn systemd unit;
8. configures the firewall when requested;
9. verifies service, migration, and HTTP login health.

The initial login for an empty database is `admin` / `changeme`. Change it immediately in **Configuration**. Existing environment files, databases, projects, users, and passwords are preserved.

## Updates

Update to the default release:

```bash
sudo /opt/clusterweaver/app/setup/update.sh
```

Update to a release tag:

```bash
sudo /opt/clusterweaver/app/setup/update.sh v0.1.5
```

The updater downloads the selected release into a temporary checkout, invokes the idempotent installer, backs up the closed SQLite database under `/var/lib/clusterweaver/backups`, preserves the previous application tree under `/opt/clusterweaver/previous`, runs migrations, refreshes systemd, restarts the service, and runs the health check.

## Health check

```bash
sudo /opt/clusterweaver/app/setup/check.sh
```
