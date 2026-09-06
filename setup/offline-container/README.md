# ClusterWeaver offline container for RHEL 10

This bundle installs ClusterWeaver on a fresh, Satellite-connected RHEL 10.2 x86_64 server without GitHub, PyPI, or an external container registry.

## Build on the connected staging host

The build host needs x86_64 Podman plus access to Red Hat UBI repositories and PyPI:

```bash
./setup/offline-container/build-offline-bundle.sh
sha256sum -c dist/clusterweaver-0.1.6-linux-amd64-offline.tar.gz.sha256
```

Transfer the `.tar.gz` and its `.sha256` file through the approved offline channel.
The bundle includes image metadata, the exact Python package inventory, source commit, and checksums for every executable installation artifact.
The builder downloads the UBI base when missing and reuses its local verified cache for repeat builds.

## Fresh RHEL 10.2 server installed by Kickstart

Required Kickstart package access through Satellite:

```kickstart
%packages
@^minimal-environment
container-tools
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
sha256sum -c clusterweaver-0.1.6-linux-amd64-offline.tar.gz.sha256
tar -xzf clusterweaver-0.1.6-linux-amd64-offline.tar.gz
cd clusterweaver-0.1.6-linux-amd64-offline
./install-offline.sh
```

Use `./install-offline.sh --no-firewall` when the port is managed centrally. The installer uses only the transferred OCI archive and packages supplied by Satellite. It does not call GitHub, PyPI, or a container registry.

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
