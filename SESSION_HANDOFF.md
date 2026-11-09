# ClusterWeaver session handoff

Updated: 2026-11-09 (Europe/Rome)

## Session closure: 0.1.14 (2026-11-09)

- Checkout: `/root/ClusterWeaver-main`, branch `main`; version/tag: `0.1.14` / `v0.1.14`.
- Release notes: `CHANGELOG.md`, dated `2026-11-09`.
- Published release commit: `cb38c33`; tag: `v0.1.14`; release: <https://github.com/markhawks/ClusterWeaver/releases/tag/v0.1.14>. Verified public, not draft/prerelease, with zero uploaded assets.
- Local service aligned to 0.1.14 at `/opt/clusterweaver/app`: active, database current and login reachable. Final deployment database backup: `/var/lib/clusterweaver/backups/clusterweaver-20261109T170105Z-3785606.db`. No active cluster jobs existed before deployment.
- Offline installation remains deprecated. Do not build or attach offline installation bundles; no binary release assets were uploaded.
- Alembic head remains `0018_stonith_passwords`: no new migration is required by 0.1.14. Preserve the database, project SSH key directories and controller encryption-key directory in protected backups.
- Added explicit network Skip (00c), recorded as skipped per node, preserving existing successful results and unlocking 01 after discovery/trust. No network commands run when skipping.
- Node gateway validation now reports problems while editing and blocks invalid saves, clones and portable imports. It detects self/peer node addresses, existing router-IP collisions, out-of-subnet, network/broadcast and non-unicast values. /31 links remain supported. These checks do not establish actual router reachability or correctness of an otherwise valid address.
- Step 08a visibly offers OEM profiles or individual iDRAC/IPMI. New configurations default to direct IPMI; existing saved modes are preserved. Manual checks display one copyable command per node with controller/user prefilled and a password placeholder, plus the separate full verification script. Agent summaries include per-node Europe/Rome timestamps.
- New profile resource names default to STONITH- plus the last two trailing hostname digits, e.g. STONITH-90 / STONITH-91. Names already saved by the user are preserved. Target mappings use the saved Pacemaker nodename, not the bare hostname.
- Step 08b creates direct-IPMI devices from one coordinator after passing 00k, 08a and 08a-fa checks. Live preflight verifies cluster identity/quorum, healthy membership, agents and surviving-peer access to each controller. Commands use lanplus=1 and power_wait=4 by default, with no explicit method or monitor. Monitor/failure-timeout overrides and disabled creation are optional. Enabled devices become available to Pacemaker immediately.
- 08b stages all missing resources in protected CIB files, injects passwords into XML rather than argv, and applies one diff. Matching existing resources are reused; conflicting resources are never overwritten. Creation is a background job with shared per-project reservations/history. Unknown mutation results require a successful status refresh and are never automatically replayed.
- Step 08c checks live CIB bindings/credentials, enabled/managed/runtime state, actual monitor operations/timeouts, failure counts, global fencing/maintenance state, quorum and peer controller access. It is read-only: no configuration changes, activation, cleanup or power actions. Missing periodic monitors are warnings; failed/disabled/blocked resources and non-zero failure counts fail verification. Conditional policies require manual review.
- The STONITH phase matches the other macro groups, with Steps 08a–08c, a 3-step completion counter and consistent step cards/icons. Cluster Base displays Steps 05–07 and has proper separation from STONITH. UI controls are English.

## Validation and operational state

- Final 0.1.14 validation: 153 tests passed, plus JavaScript and shell syntax checks and Git whitespace checks. Existing WTForms tuple-choice deprecation warnings remain; no test failures. JavaScript verification-page submission was also checked during development.
- Changes have been deployed locally during the session. Latest feature deployment backup before release: `/var/lib/clusterweaver/backups/clusterweaver-20261109T165518Z-3781135.db`.
- 08b/08c implementation tests use simulated pcs/CIB/SSH. The user reported that fencing resources were created through the GUI. The assistant did not execute live creation, power-off or reboot tests during this session.
- No production machine names, controller endpoints, passwords, private keys or runtime database files belong in the application Git release. Project inventories are separately versioned in the local project repository.

## Resume next session

- Run 08c from the GUI on the selected cluster and review resource bindings, runtime/monitor state, failure counts and peer controller access. Investigate timeout causes; do not automatically clear failure history.
- Step 08d (real fencing/power tests) is NOT implemented. Design it separately with explicit node selection/confirmation, one node at a time, quorum/workload checks and verification of full rejoin before the next test.
- Creating devices for OEM/Cisco/ILOM/VMware is NOT implemented; 08b/08c currently support direct iDRAC/IPMI only. OEM remains available for 08a definitions/verification.
- The SSH-key migration remains unresolved. Step 00b creates distinct Ed25519 keys commented clusterweaver-bootstrap on individual nodes for peer trust. The server root RSA identity is different. The service currently uses working per-project keys. Do not remove these or copy node private keys without resolving the user's intended identity and verifying replacement access on every node. Existing keys were preserved.

The following sections preserve the historical release/session records.

## Session closure: 0.1.13 (2026-10-30)

- Checkout: `/root/ClusterWeaver-main`, branch `main`; version/tag: `0.1.13` / `v0.1.13`.
- Release notes: `CHANGELOG.md`, dated `2026-10-30`.
- Published release commit: `e571893`; tag: `v0.1.13`; release: <https://github.com/markhawks/ClusterWeaver/releases/tag/v0.1.13>. Release is public (not draft/prerelease), with zero uploaded assets.
- Local installation aligned to 0.1.13 at `/opt/clusterweaver/app`; `clusterweaver-control.service` active, database current and login reachable. Deployment backup: `/var/lib/clusterweaver/backups/clusterweaver-20261030T171249Z-64778.db`.
- The pre-existing empty npm manifests were preserved outside the Python release at `/var/tmp/clusterweaver-session-20261030-untracked/`.
- Offline installation remains deprecated. Do not build or upload offline installation bundles; this release has no uploaded binary assets.
- Step 08a saves controller passwords encrypted in SQLite, reuses them for verification, and exposes a CSRF-protected show/hide control only to administrators and clusteradmins. Blank fields retain saved credentials for unchanged controller/mode/userid. Passwords and ciphertext remain excluded from YAML/Git, scripts and portable project exports.
- Validation: 117 tests passed; Git whitespace, JavaScript syntax and shell syntax checks passed. WTForms emits existing tuple-choice deprecation warnings.
- Alembic head: `0018_stonith_passwords`. Back up the service-owned encryption key directory (`PROJECTS_ROOT.parent/stonith_secrets`, override `CLUSTERWEAVER_STONITH_SECRETS_ROOT`) securely with SQLite; the database alone cannot recover saved passwords. Credentials entered in older releases must be re-entered once.
- Direct iDRAC/IPMI status runs via project SSH on each cluster node against its associated iDRAC. The agent is required on the nodes, not the web server. OEM HTTPS checks still run on ClusterWeaver.
- Show/Copy verification script controls are beside profile Save/Verify. The manual IPMI script runs on a cluster node and prompts for passwords; it checks the saved definitions, not unsaved form changes.
- Native updates repair staged virtual-environment launcher paths. Local HTTP checks bypass proxies and retry while the service starts. Existing deployment fixes are in `setup/update-local.sh`, `setup/relocate-venv.py` and `setup/check.sh`.
- Real validation: key-only SSH and read-only iDRAC status passed on both tested nodes; both controllers reported ON. Results were persisted as PASS in steps 00k and 08a. No power actions or cluster lifecycle changes were performed.

### SSH decision deferred — resume here next session

- The user wants to reuse the key called `clusterweaver-bootstrap` and remove the extra project key added during diagnosis. This migration has NOT been implemented, and no key has been removed.
- Inspection established that step 00b generates a different Ed25519 key with comment `clusterweaver-bootstrap` on each node for node-to-node trust. These are not a single server-side identity.
- The local root RSA key is a separate identity and already reaches the tested nodes. Root access uses the configured SSH IP with the trusted hostname as `HostKeyAlias`; strict host-key checking remains enabled.
- The web service runs as `clusterweaver`. The currently working implementation uses a service-owned project key; its public key was added via the existing strictly verified root SSH access, restricted to the source IP each node observes. The root private key was not copied into the service, and existing authorized keys were preserved.
- Pending user clarification: reuse the already-authorized local server RSA key for service access, or literally transfer a node-generated bootstrap identity. Do not claim these are the same key. Do not remove the working project key until the chosen replacement has been verified on every node.
- Next session: resolve this key choice, make step 00 bootstrap repeatable for subsequent clusters, then resume read-only tests on other clusters. Actual fencing/power tests remain outside completed validation.

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
