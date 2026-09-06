# ClusterWeaver session handoff

Updated: 2026-09-06 (Europe/Rome)

## Repository state

- Working directory: `/var/www/html/ClusterWeaver`
- Git branch: `main`
- Current released version: `0.1.5`
- Application version source: `clusterweaver/version.py`
- Service: `clusterweaver-control`
- Database migration head: `0010_user_theme`

## Work released in 0.1.2

### Workflow execution

- Added persistent per-node latest execution results for generated workflow steps.
- Added database table `step_executions` through migration `0007_step_results`.
- Added Step 00 with three independent operations and execution panels:
  - `00a`: read-only SSH discovery;
  - `00b`: peer root SSH key trust;
  - `00c`: RHEL 10.2 network application.
- Step 01 is enabled only after every node passes all three Step 00 operations.
- Steps 01–04 use sequential server-side and interface gating.
- Failed steps show a red Stop-style retry button; successful/runnable steps are green and blocked steps are grey.
- Execution output temporarily gives way to the script when `Show script` is selected.

### Remote operations

- Steps 01, 02, 03, and 04 can run through SSH from the graphical interface.
- Step 03 supports RHEL 9.8 and 10.2 and creates a unique `/etc/hosts` backup plus manifest under `/root/clusterweaver-backups/hosts/` on every execution.
- Step 04 supports RHEL 9.8 and 10.2, validates the remote release, and stores per-node results.

### Network safety and idempotency

- RHEL 10.2 network application compares the live configuration with the project first.
- If management and private networks are compliant, it returns PASS without changing profiles, interfaces, routes, or scheduling rollback.
- A changed management network is applied using a candidate NetworkManager profile, timed rollback, SSH reconnection verification, and archival of the replaced profile.
- A changed private network is allowed only before cluster formation.
- Private changes run `rpm -q pcs`; when installed, `pcs status` is inspected. A detected cluster blocks the private change.
- If management and private settings both differ after cluster formation, management can be updated but private configuration remains blocked and the operation reports failure.
- Private interfaces retain `ipv4.never-default=yes`; a configured private gateway is informational and is not installed as the system default route.

### Project list and navigation

- Added stable chronological project numbers (`01` is the oldest project).
- Added sortable number, project name, customer, target, creation, and last-modified columns.
- Added column-aware search with a minimal search icon.
- Added Hypervisor column with VMware, KVM, Proxmox, or `N/A`.
- Added Remote Ready status:
  - green arrow when all Step 00 operations pass on every node;
  - red arrow when SSH discovery has at least one failure;
  - grey arrow while setup is incomplete.
- Added minimal Projects, Home, notebook, cluster, VM, server, settings, and search icons.
- Changelog is right-aligned in the navigation; version and component details are displayed by clicking the ClusterWeaver logo.

## Work released in 0.1.3

- Added database-backed login, password management and the `user`, `clusteradmin`, and `administrator` roles. The deployment credentials create only the initial administrator.
- User records track `password_changed_at`; Configuration displays the latest password-change date separately from other account changes.
- Added branded login page, authenticated session, and CSRF-protected logout.
- Limited hostnames to 30 characters and restricted them to safe hostname characters.
- Reworked SSH output collection to drain stdout and stderr while commands run, retain at most 20 KB, and enforce a hard timeout.
- Updated the runtime and requirement from unsupported Gunicorn 23.x to maintained Gunicorn 26.x; its optional control socket is disabled for compatibility with the hardened systemd filesystem.
- The SQLite database remains locally readable by deliberate operator choice for emergency diagnosis.
- Added per-user theme selection with soft dark grey as default, global high-contrast styling, compact project workflows, and a centred login layout.
- Replaced the square-backed logo with an RGBA PNG whose area outside the white circle is transparent; the same asset serves the navbar, login, modal, and favicon.
- The initial empty-database account is `admin` / `changeme`; it must be changed immediately from Configuration.
- Added migrations `0008_users`, `0009_password_changed`, and `0010_user_theme`.

## Validation performed

Run before handoff:

```bash
.venv/bin/pytest -q
git diff --check
.venv/bin/alembic current
systemctl is-active clusterweaver-control
```

Expected test result: `44 passed`.

## Important operational notes

- Passwords entered for SSH operations are request-scoped and are not stored in project execution results.
- Initial application bootstrap credentials may be supplied through the protected environment file and must not reuse node root credentials. They are ignored once an account exists.
- Older Step 00 actions performed before migration `0007` have no execution records. Those projects must execute Step 00 again before Step 01 becomes available.
- Peer SSH trust is idempotent: existing Ed25519 keys are reused and exact authorized keys are not duplicated.
- Release `0.1.3` adds authentication, role-based authorization, account/password management, security fixes, updated Gunicorn support, theme selection, accessible dark styling, responsive navigation, and transparent branding.

## Suggested next session start

1. Read this file and `CHANGELOG.md`.
2. Check `git status --short --branch` and the latest commit.
3. Confirm migration state with `.venv/bin/alembic current`.
4. Confirm the service with `systemctl is-active clusterweaver-control`.
5. Run `.venv/bin/pytest -q` before the next change.

## Likely next work

- Continue the generated workflow after Step 04.
- Define the next generated workflow step after Step 04.
- Exercise Step 00 and Steps 01–04 end-to-end on the two-node RHEL 10.2 KVM test cluster.

## Work released in 0.1.4

- Added `setup/bootstrap.sh` for a complete GitHub-to-system installation at `/var/www/html/ClusterWeaver`.
- Added idempotent `setup/install.sh`, safe `setup/update.sh`, and `setup/check.sh` health verification.
- Setup covers RHEL dependencies, service account, virtualenv, protected environment, Alembic migrations, systemd, optional firewalld opening, closed-database update backups, and initial `admin` / `changeme` access.
- Added `setup/offline-container/` for disconnected RHEL 10.2 x86_64 systems: multi-stage UBI 10 image, OCI archive builder, Podman Quadlet, offline install/update/uninstall/verify scripts, checksums, inventories, and Kickstart instructions.
- Built `dist/clusterweaver-0.1.4-linux-amd64-offline.tar.gz` locally; `dist/` is ignored by Git.
- Local Podman test container `clusterweaver-offline-test` listens on `127.0.0.1:5051`, persists under `/var/lib/clusterweaver-podman-test/data`, and passed health, login, project creation, YAML/Git persistence, Configuration, and migration tests.

## Work released in 0.1.5

- Native production paths are `/opt/clusterweaver/app`, `/opt/clusterweaver/venv`, `/etc/clusterweaver`, and `/var/lib/clusterweaver`.
- The installer accepts any source checkout, migrates the legacy `/var/www/html/ClusterWeaver/data` tree when needed, retains the old data, creates a closed SQLite backup, and preserves the previous deployed app.
- Bootstrap and updater use temporary Git checkouts; the production application is no longer a Git working tree or web-root deployment.
- systemd and all native health/migration tooling use the standard production paths.
