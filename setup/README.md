# Automated setup

These scripts install ClusterWeaver on RHEL or a compatible distribution. The supported application path is `/var/www/html/ClusterWeaver` and commands must run as root.

## Complete installation from GitHub

Download `bootstrap.sh` onto an empty server and run:

```bash
curl --fail --location --output bootstrap.sh https://raw.githubusercontent.com/markhawks/ClusterWeaver/v0.1.4/setup/bootstrap.sh
chmod 755 bootstrap.sh
sudo bash bootstrap.sh
```

It installs Git, checks out release `v0.1.4`, and runs the complete installer. Override the release with `CLUSTERWEAVER_VERSION`, for example `CLUSTERWEAVER_VERSION=main sudo bash bootstrap.sh`. The destination must not already exist.

## Installation from an existing checkout

```bash
cd /var/www/html/ClusterWeaver
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

Update to current `main`:

```bash
sudo ./setup/update.sh
```

Update to a release tag:

```bash
sudo ./setup/update.sh v0.1.4
```

The updater refuses a dirty Git working tree, stops the service, backs up the closed SQLite database under `/var/lib/clusterweaver/backups`, performs a fast-forward/tag checkout, installs dependencies, runs migrations, refreshes systemd, restarts the service, and runs the health check. A failure handler attempts to bring the service back online.

## Health check

```bash
sudo ./setup/check.sh
```
