# ClusterWeaver session handoff

Updated: 2026-09-09 (Europe/Rome)

## Repository and release state

- Development checkout: `/var/www/html/ClusterWeaver`
- Branch: `main`
- Current release: `0.1.9`
- Release commit: `4b9c70a536583cfeeb45922ab59790078ea63d28`
- Annotated tag: `v0.1.9`
- GitHub release: <https://github.com/markhawks/ClusterWeaver/releases/tag/v0.1.9>
- Database migration head: `0012_project_cluster_name`
- Test baseline: `60 passed`
- Native layout: app `/opt/clusterweaver/app`, venv `/opt/clusterweaver/venv`, configuration `/etc/clusterweaver`, persistent state `/var/lib/clusterweaver`
- Native service: `clusterweaver-control`
- Podman/Quadlet service: `clusterweaver.service`

At handoff, local `main`, `origin/main`, and tag `v0.1.9` all point to release commit `4b9c70a`.

## Work completed in 0.1.9

### Project configuration and presentation

- Added an editable `Cluster Name`, initially derived from the project name and stored independently for Pacemaker.
- Added migration `0012_project_cluster_name`; existing records are populated from their project slug.
- Cluster Name is preserved by YAML serialization and portable `.cwp` import/export.
- Physical projects have a hardware selector with Dell and Cisco; virtual projects retain VMware, KVM, and Proxmox.
- Projects now show `Hypervisor/HW`, visually distinct project/cluster names, and a one-line description preview.
- Configuration and Cluster overview are fully collapsible.
- Workflow phases and individual steps have higher-contrast styling and minimal phase/footprint icons.

### Workflow phases

- Steps 00–04 are grouped under collapsible **Pre-Cluster Configuration**.
- Steps 05–07 are grouped under collapsible **Cluster Base Installation and Configuration**.
- A completed phase is closed by default; the latest available incomplete phase opens automatically; if all phases are complete, all remain closed.
- Each phase reports completed/total steps and visually distinguishes complete from incomplete status.
- Remote execution remains sequentially gated and records the latest per-node result.

### Step 00 and Step 03 corrections

- Step 00 network configuration supports imported RHEL 9.8 projects as well as RHEL 10.2.
- Network application remains idempotent and retains backup, rollback, formed-cluster, management-route, and private-network protections.
- Step 03 always backs up `/etc/hosts` under `/root/clusterweaver-backups/hosts/`.
- Step 03 removes obsolete or empty ClusterWeaver blocks that conflict with the current imported cluster while preserving unrelated populated blocks.

### Step 05 — package installation

- Runs remotely on RHEL 9 and RHEL 10 after every preceding step succeeds.
- MPS projects use `osupdate install pcs pacemaker fence-agents-all pcp-zeroconf -y`.
- Other customers use `dnf install pcs pacemaker fence-agents-all pcp-zeroconf -y`.
- Existing installations are handled idempotently and every required RPM is verified.

### Step 06 — pcsd and node authentication

- Enables and starts `pcsd.service`, then verifies enabled and active state.
- Configures the requested default `hacluster` credential.
- Runs `pcs host auth` against all configured cluster nodenames from every node.

### Step 07 — cluster creation and quorum

- Displays and uses the project’s editable Cluster Name.
- The coordinator runs `pcs cluster setup <cluster-name> --start <all-nodes>`.
- The workflow waits for node membership, enables and controls the cluster, sets `wait_for_all=1`, restarts the cluster, and verifies quorum.
- Existing matching cluster configuration is detected; a conflicting existing cluster name fails safely.
- Execution output is stored per node like the preceding remote steps.

## Release artifacts

The GitHub `v0.1.9` release contains:

- `clusterweaver-0.1.9-linux-amd64-offline.tar.gz` and SHA-256 file for a complete offline Podman installation;
- `clusterweaver-0.1.9-20260909T194033Z-4b9c70a53658.cwu` and SHA-256 file for a code-only update from the 0.1.8 image;
- `clusterweaver-update` and its SHA-256 file.

Both the full bundle and `.cwu` package were checksum-verified locally. The full OCI image is `localhost/clusterweaver:0.1.9`.

## Validation performed

```bash
.venv/bin/pytest -q
# 60 passed

env CLUSTERWEAVER_DATABASE_URL=sqlite:////tmp/clusterweaver-release-019.db \
    CLUSTERWEAVER_PROJECTS_ROOT=/tmp/clusterweaver-release-019-projects \
    .venv/bin/alembic upgrade head
# upgraded successfully through 0012_project_cluster_name

bash -n setup/*.sh setup/offline-container/*.sh
git diff --check
```

The offline bundle and code-only update were built after the release commit so their metadata identifies `4b9c70a`.

## Updating a native remote installation

If the remote Git checkout is already present:

```bash
cd /root/ClusterWeaver
git status --short --branch
git fetch --tags origin
git switch main
git pull --ff-only origin main
git checkout v0.1.9
git describe --tags --exact-match
./setup/update-local.sh
```

Expected tag output: `v0.1.9`. A detached HEAD after checking out a release tag is expected. To track `main` instead, omit `git checkout v0.1.9`.

Validate the native deployment with:

```bash
systemctl is-active clusterweaver-control
curl --fail --silent http://127.0.0.1:5000/login | grep -oE 'Version[[:space:]]+[0-9.]+'
```

Expected results are `active` and `Version 0.1.9`. `setup/update-local.sh` backs up SQLite, applies migrations, verifies service health, and automatically restores the previous deployment if verification fails.

## Updating a Podman installation

For the official code-only update from 0.1.8, verify the four downloaded release files and run:

```bash
sha256sum -c clusterweaver-update.sha256
sha256sum -c clusterweaver-0.1.9-20260909T194033Z-4b9c70a53658.cwu.sha256
install -o root -g root -m 0755 clusterweaver-update /usr/local/sbin/clusterweaver-update
clusterweaver-update ./clusterweaver-0.1.9-20260909T194033Z-4b9c70a53658.cwu
```

Then verify:

```bash
systemctl is-active clusterweaver.service
podman healthcheck run clusterweaver
grep '^__version__' /opt/clusterweaver/live/clusterweaver/version.py
```

Use the complete offline bundle instead whenever Python dependencies, entrypoint, health check, or base image change.

## Operational notes

- Initial empty-database credentials are `admin` / `changeme`; change the password immediately.
- SSH passwords are request-scoped and are not persisted in execution results or project data.
- Peer SSH trust reuses an existing Ed25519 key and does not duplicate an already-authorized exact key.
- Imported `.cwp` projects receive a new UUID and no execution history; Step 00 must be run again.
- `.cwp` archives exclude passwords, private keys, secrets, logs, and remote execution results.
- Server-side imports are read from `/var/lib/clusterweaver/data/Project-Import`.
- The main GitHub README is English; `README_IT.md` is the complete Italian version.
- Private cluster gateways are accepted as configuration metadata but never become the system default route.
- A private network change is blocked after an existing Pacemaker cluster is detected; management changes remain supported with safety rollback.

## Suggested next-session start

1. Read this file and `CHANGELOG.md`.
2. Run `git status --short --branch` and `git log -3 --oneline --decorate`.
3. Run `.venv/bin/pytest -q`; the expected baseline is 60 passing tests.
4. Confirm the target deployment reports version 0.1.9 and migration `0012_project_cluster_name`.
5. Test Step 07 end-to-end on the intended RHEL 9 or RHEL 10 multi-node lab cluster, confirming cluster naming, online membership, `WaitForAll`, and quorum output.
6. Continue with the next cluster workflow function after the base cluster has been validated, likely STONITH selection/configuration based on Hypervisor/HW.
