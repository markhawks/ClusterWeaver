# ClusterWeaver session handoff

Updated: 2026-10-09 (Europe/Rome)

## Session closure: 0.1.12 (2026-10-09)

- Checkout: `/root/ClusterWeaver-main`, branch `main`; version/tag: `0.1.12` / `v0.1.12`.
- Release notes: `CHANGELOG.md`, dated `2026-10-09`.
- Validation: 111 tests passed; JavaScript syntax and Git whitespace checks passed.
- Alembic head: `0017_cluster_operations`; apply migrations before starting updated code.
- Includes hostname diagnostics and step 07 existing-cluster checks; step 08a DELL OEM and direct iDRAC/IPMI definitions, read-only connection/status checks and fence-agent inventory; per-project service-owned SSH keys; background Cluster Operations and Status with identity/quorum checks, per-node progress and audit history.
- Private keys and request-only passwords are excluded from project exports and version control.
- No live fencing or cluster lifecycle operation was performed. Appliance verification still requires real credentials and hardware validation.
- The pre-existing file `1` was a hosts-file copy containing internal addresses; preserved at `/tmp/clusterweaver-session-hosts-backup.txt`, excluded from the release.
- Published release commit: `573060f`; tag: `v0.1.12`.
- GitHub release: <https://github.com/markhawks/ClusterWeaver/releases/tag/v0.1.12>. Commit and tag pushed successfully; no uploaded release assets. GitHub automatically provides source archives.
- All 111 tests passed again before publication; Git whitespace and JavaScript syntax checks passed.
- No application deployment was performed as part of release publication.
- Release packaging: offline installation is deprecated; do not build or upload offline installation archives for 0.1.12.
- Next session: verify installation migrations, bootstrap/verify project SSH keys, then validate read-only status and step 08a against the target equipment before lifecycle operations.

The sections below preserve the historical 0.1.11 handoff and published artifact information.

## Repository and release state (historical 0.1.11)

- Checkout: `/var/www/html/ClusterWeaver`, branch `main`
- Current release: `0.1.11`
- Release commit: `28e5442a9ee8940830126eee0909ce60649028ad`
- Tag: `v0.1.11`
- Release: <https://github.com/markhawks/ClusterWeaver/releases/tag/v0.1.11>
- Alembic head: `0014_user_password_change`
- Test baseline: `66 passed`
- Native service: `clusterweaver-control.service`
- Podman service: `clusterweaver.service`

At handoff, local `main`, `origin/main`, and `v0.1.11` point to `28e5442`. The public release contains all six expected assets.

## Completed in 0.1.11

### Mandatory initial password replacement

- Added `UserRecord.must_change_password` and migration `0014_user_password_change`.
- A bootstrapped administrator signing in with `admin` / `changeme` is forced into Configuration.
- Until replacement, every endpoint except Configuration, password change, logout, and static assets is blocked server-side. Administrative and appearance forms are hidden.
- Existing installations predating the migration are protected when they next authenticate with the configured `changeme` credential.
- A successful password change clears the flag and restores access according to the user's role.

### RHEL 7.9 Step 00c

- Step 00 network operation supports RHEL 7.9, 9.8, and 10.2.
- RHEL 7.9 uses a separate strictly read-only path: it never creates, edits, activates, deletes, copies, or archives network configuration.
- It verifies release, interfaces, management CIDR/default gateway, optional private CIDR, and that the private interface has no default route.
- It reports NetworkManager state and whether interfaces have active NM connections and/or legacy `ifcfg-*` files.
- Matching state returns PASS; differences return FAIL with details and no changes.
- A RHEL 7.9 PASS records the execution result but does not update bootstrap IP or project YAML.
- RHEL 9.8/10.2 retain idempotency, candidate profile, reconnect, backup, rollback, private never-default, and formed-cluster protections.

### Step 00 script views

- Operations `00a`, `00b`, and `00c` now offer Show/Hide script, Full screen, and Copy like subsequent steps.
- Opening a script temporarily hides its Latest Execution panel.
- `00a` shows the exact discovery payload; `00b` and `00c` show sanitized execution/orchestration plans.
- Passwords and private keys are never rendered.

## Release assets

- `clusterweaver-0.1.11-20260916T160211Z-28e5442a9ee8.cwu`
- `clusterweaver-0.1.11-20260916T160211Z-28e5442a9ee8.cwu.sha256`
- `clusterweaver-update`
- `clusterweaver-update.sha256`
- `clusterweaver-0.1.11-linux-amd64-offline.tar.gz`
- `clusterweaver-0.1.11-linux-amd64-offline.tar.gz.sha256`

The `.cwu` targets the existing `localhost/clusterweaver:0.1.10` base image. The full bundle contains `localhost/clusterweaver:0.1.11`. All checksums passed locally.

## Validation

```bash
.venv/bin/pytest -q
# 66 passed

.venv/bin/alembic heads
# 0014_user_password_change (head)

bash -n setup/*.sh setup/offline-container/*.sh
git diff --check
```

## Native remote update

```bash
sudo /opt/clusterweaver/app/setup/update.sh v0.1.11
```

Alternative from a checkout:

```bash
cd /root/ClusterWeaver
git fetch --tags origin
git checkout v0.1.11
sudo ./setup/install.sh
```

Validate with:

```bash
systemctl is-active clusterweaver-control.service
curl --fail --silent http://127.0.0.1:5000/login | grep -oE 'Version[[:space:]]+[0-9.]+'
```

Expected: `active` and `Version 0.1.11`. Data is preserved, SQLite is backed up, and migration `0014` is applied automatically.

## Podman update from 0.1.10

Download the four code-update files from the v0.1.11 release, then:

```bash
sha256sum -c clusterweaver-update.sha256
sha256sum -c clusterweaver-0.1.11-20260916T160211Z-28e5442a9ee8.cwu.sha256
install -o root -g root -m 0755 clusterweaver-update /usr/local/sbin/clusterweaver-update
clusterweaver-update ./clusterweaver-0.1.11-20260916T160211Z-28e5442a9ee8.cwu
```

Validate with:

```bash
systemctl is-active clusterweaver.service
podman healthcheck run clusterweaver
grep '^__version__' /opt/clusterweaver/live/clusterweaver/version.py
```

## Security review: remaining priorities

Only forced replacement of `admin/changeme` was fixed in 0.1.11. Remaining findings:

1. **Critical:** Step 06 embeds shared `hacluster` password `ricciolone` in generated/downloadable/exported scripts and passes it to `pcs -p`. Replace it with a per-project or per-run secret that is never rendered/exported.
2. **Critical:** Paramiko uses `AutoAddPolicy`; implement first-use fingerprint confirmation and persistent host-key pinning before sending root credentials.
3. **High:** production exposes HTTP TCP/5000. Add an HTTPS reverse proxy, bind 5000 to localhost, enable secure cookies, and restrict firewall access.
4. **High:** add login rate limiting and temporary lockout.
5. **Medium:** make role authorization deny-by-default for unknown database role values.
6. **Medium:** add session expiration/revocation plus CSP, HSTS, frame, and content-type headers.
7. **Accepted design risk:** SQLite mode `0644` exposes password hashes and cluster inventory to local users.
8. **Supply chain:** artifacts have adjacent SHA-256 files but no signed provenance; Python dependencies use ranges rather than a hash-locked file.

## Operational notes

- Empty-database credentials remain `admin` / `changeme`, but 0.1.11 blocks normal use until replacement.
- SSH passwords are request-scoped unless the optional protected environment variable is configured; they are not persisted in projects or execution results.
- Peer trust creates/reuses unencrypted root Ed25519 keys and full peer trust; revocation/restriction is not implemented.
- Imported `.cwp` projects receive a new UUID and reset execution history; Step 00 must be repeated.
- Server-side imports live under `/var/lib/clusterweaver/data/Project-Import`.
- Private cluster gateways never become the default route.
- Private network changes are blocked after a formed Pacemaker cluster is detected.
- Main README is English; `README_IT.md` is the complete Italian version.

## Suggested next-session start

1. Read this file and the top of `CHANGELOG.md`.
2. Run `git status --short --branch`, `git log -3 --oneline --decorate`, and `.venv/bin/pytest -q`.
3. Confirm the remote target reports 0.1.11 and migration `0014_user_password_change`.
4. Test forced password replacement and direct-URL blocking.
5. Test Step 00c on RHEL 7.9 under both NetworkManager and legacy network-scripts, verifying no remote state changes.
6. Test Show/Copy/Full-screen for all three Step 00 operations.
7. Prefer removing the hard-coded `hacluster` password next, then implement SSH host-key pinning and HTTPS.

- Step 08a now also supports direct DELL iDRAC/IPMI with credential-free per-node definitions. `fence_ipmilan` must be installed on the application server/container. Status only; no live IPMI check or deployment performed.

- Step 08a now has a separate root-SSH node-agent check: inventories fence RPMs/executables, validates IPMI metadata, stores results as `08a-fa`, and proposes manual `dnf install fence-agents-all`. No remote installation or live node check was performed. No new migration is required for this check.

- Added service-owned UUID-scoped SSH keys in `data/ssh_keys` (0700/0600), Step 00 → ClusterWeaver SSH key UI, per-node password provisioning, host-key pinning, key-only verification, pending/active/previous rotation, and previous-key revocation. All remote workflows accept keys; explicitly entered passwords request temporary password access. No fallback after key failure. Network IP changes require the original host key. No additional DB migration. No keys provisioned on actual cluster nodes or application deployment performed during this change.

- Cluster Operations and Status UI follows STONITH, linked by Gestisci cluster. New migration0017 persists background jobs and one active reservation per project. Jobs use explicit project SSH keys, require 00k proof, verify exact Corosync/live identity, run local pcs on each SSH IP for cluster-wide actions, and one coordinator for node standby. No automatic retries/force; timeouts are UNKNOWN with refresh required. Daemon threads are interrupted on worker restart; stale jobs expire as UNKNOWN after600s. No live cluster operation or deployment was performed.
