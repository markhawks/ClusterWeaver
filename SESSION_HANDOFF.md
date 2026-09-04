# ClusterWeaver session handoff

Updated: 2026-09-04 (Europe/Rome)

## Repository state

- Working directory: `/var/www/html/ClusterWeaver`
- Git branch: `main`
- Current released version: `0.1.1`
- Application version source: `clusterweaver/version.py`
- Service: `clusterweaver-control`
- Database migration head: `0007_step_results`

## Work completed after release 0.1.1

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
- Changelog is right-aligned in the navigation and displays `v0.1.1`.

## Validation performed

Run before handoff:

```bash
.venv/bin/pytest -q
git diff --check
.venv/bin/alembic current
systemctl is-active clusterweaver-control
```

Expected test result: `40 passed`.

## Important operational notes

- Passwords entered for SSH operations are request-scoped and are not stored in project execution results.
- Older Step 00 actions performed before migration `0007` have no execution records. Those projects must execute Step 00 again before Step 01 becomes available.
- Peer SSH trust is idempotent: existing Ed25519 keys are reused and exact authorized keys are not duplicated.
- The current changes belong to the post-0.1.1 unreleased section; no new release or tag has been created.

## Suggested next session start

1. Read this file and `CHANGELOG.md`.
2. Check `git status --short --branch` and the latest commit.
3. Confirm migration state with `.venv/bin/alembic current`.
4. Confirm the service with `systemctl is-active clusterweaver-control`.
5. Run `.venv/bin/pytest -q` before the next change.

## Likely next work

- Continue the generated workflow after Step 04.
- Decide the next release number for the accumulated unreleased functionality.
- Exercise Step 00 and Steps 01–04 end-to-end on the two-node RHEL 10.2 KVM test cluster.
