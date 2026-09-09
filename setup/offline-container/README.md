# ClusterWeaver offline container for RHEL 10

This bundle installs ClusterWeaver on a fresh, Satellite-connected RHEL 10.2 x86_64 server without GitHub, PyPI, or an external container registry.

## Build on the connected staging host

The build host needs x86_64 Podman plus access to Red Hat UBI repositories and PyPI:

```bash
./setup/offline-container/build-offline-bundle.sh
sha256sum -c dist/clusterweaver-0.1.9-linux-amd64-offline.tar.gz.sha256
```

Transfer the `.tar.gz` and its `.sha256` file through the approved offline channel.
The bundle includes image metadata, the exact Python package inventory, source commit, and checksums for every executable installation artifact.
The builder downloads the UBI base when missing and reuses its local verified cache for repeat builds.

## Fresh RHEL 10.2 server installed by Kickstart

Required Kickstart package access through Satellite:

```kickstart
%packages
@^minimal-environment
podman
openssl
curl
tar
gzip
%end

firewall --enabled --port=5000:tcp
services --enabled=firewalld
```

After first boot, copy the bundle to `/root`, then run:

```bash
cd /root
sha256sum -c clusterweaver-0.1.9-linux-amd64-offline.tar.gz.sha256
tar -xzf clusterweaver-0.1.9-linux-amd64-offline.tar.gz
cd clusterweaver-0.1.9-linux-amd64-offline
./preflight.sh
./install-offline.sh
```

`preflight.sh` does not install packages or change system configuration. It checks root access, exact RHEL release, architecture, systemd, Satellite/subscription identity, enabled repositories, package availability, free space, SELinux, Podman and its `crun`, `netavark`, and `aardvark-dns` components, and TCP port 5000. A missing Satellite identity is a warning when repositories remain usable. It exits unsuccessfully when a mandatory prerequisite is missing; warnings do not block installation. DNF may refresh repository metadata while checking package availability.

Use `./install-offline.sh --no-firewall` when the port is managed centrally. The installer uses only the transferred OCI archive and packages supplied by Satellite. It does not call GitHub, PyPI, or a container registry.

To make exported projects available for server-side import, copy `.cwp` files into `/var/lib/clusterweaver/data/Project-Import`. This path is part of the persistent container data mount. It can also contain a private Git working tree maintained by an administrator outside ClusterWeaver; repository credentials are never read or managed by the application.

Persistent state is stored in `/var/lib/clusterweaver/data`; configuration and secrets are in `/etc/clusterweaver/clusterweaver.env`. The Quadlet is installed as `/etc/containers/systemd/clusterweaver.container` and managed with:

```bash
systemctl status clusterweaver.service
journalctl -u clusterweaver.service -f
podman healthcheck run clusterweaver
```

The container needs outbound TCP/22 access to managed nodes and inbound TCP/5000 from the administration LAN. SELinux remains enforcing; the Quadlet applies a private `:Z` label to the persistent data volume.

Initial credentials for an empty database are `admin` / `changeme`. Change the password immediately.

## Update and removal

Extract a newer bundle and run `./update-offline.sh`. It stops the service and backs up SQLite before loading and starting the new image. `./uninstall.sh` preserves data and configuration. `./uninstall.sh --purge-data` moves them into a timestamped recovery directory rather than deleting them.

### Small code-only updates

Use a `.cwu` package when Python dependencies and the base container image have not changed:

```bash
./setup/offline-container/build-code-update.sh --base-image localhost/clusterweaver:0.1.7
```

The builder validates the current runtime requirements against the selected base image and refuses a code-only update when a full image is required. It writes a small `.cwu` archive, its checksum, `clusterweaver-update`, and the updater checksum under `dist/`.

On a server that predates this updater, install the small helper once:

```bash
sha256sum -c clusterweaver-update.sha256
install -o root -g root -m 0755 clusterweaver-update /usr/local/sbin/clusterweaver-update
```

For this and all subsequent code-only updates, transfer the `.cwu` file and its adjacent `.sha256`, then run:

```bash
clusterweaver-update ./clusterweaver-<build>.cwu
```

The updater validates external and internal checksums plus the exact base-image ID. It backs up SQLite and the Quadlet, stages code under `/opt/clusterweaver/live`, mounts it read-only over the application embedded in the container, and performs a health check. A failure restores the previous code, database, and Quadlet automatically. Previous code is retained in `/opt/clusterweaver/releases`. Dependencies, the UBI base, entrypoint, healthcheck, or other image-level changes still require a full offline bundle.

For the official `0.1.8` → `0.1.9` update, obtain the `.cwu`, its `.sha256`, `clusterweaver-update`, and `clusterweaver-update.sha256` from the GitHub `v0.1.9` release on a connected workstation. Transfer those four unchanged files through the approved channel, install the helper once as shown above, and run `clusterweaver-update` with the `.cwu` path. No Git access is required on the ClusterWeaver server.
