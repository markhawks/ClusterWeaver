# Changelog

All notable changes to ClusterWeaver are documented in this file.

The format follows Keep a Changelog principles. ClusterWeaver uses semantic versioning.

## [Unreleased]

## [0.1.4] - 2026-09-06

### Added

- Added automated RHEL bootstrap, local installation, safe update, and deployment health-check scripts under `setup/`.
- Added a transferable RHEL 10 x86_64 OCI bundle workflow with UBI 10, Podman Quadlet, persistent SELinux-labelled data, offline install/update verification, checksums, dependency inventory, and Kickstart guidance.

## [0.1.3] - 2026-09-06

### Added

- Added the Configuration page with self-service password changes and administrator-only user management.
- User management now shows and records the date and time of the latest password change.
- Added a per-user light/soft-dark theme selector, with the grey dark theme as default, vertically centred login, and theme-aware transparent logo assets.
- Improved login description contrast by rendering secondary text white with the dark theme.
- Improved dark-theme contrast globally and increased project workflow density so steps use the available page more efficiently.
- Reorganized navigation with Home and Project links; the login page no longer exposes the navigation, Changelog, or application-details dialog.
- Added role-based access control: read-only `user`, cluster-managing `clusteradmin`, and unrestricted `administrator`.
- The ClusterWeaver logo now opens version, author, GitHub and runtime component details; the Changelog link no longer carries the version label.
- Added database-backed login with project branding, protected logout, and initial `admin` / `changeme` bootstrap credentials.

### Changed

- Node hostnames are limited to 30 characters.
- SSH command collection drains stdout and stderr concurrently with bounded output and a hard execution timeout.
- Gunicorn requirement moved to the maintained 26.x release line.

## [0.1.2] - 2026-09-04

### Added

- Persistent per-node workflow execution status displayed in collapsed script panels.
- RHEL 10.2 support and remote-release guard for generated step 03 `/etc/hosts` updates.
- Sequential workflow gating and confirmed remote execution for step 03 on all nodes.
- Unique `/etc/hosts` backup and manifest under `/root/clusterweaver-backups/hosts/` on every step-03 execution.
- Unified step 00 for SSH discovery, peer trust, and per-node RHEL 10.2 network configuration, with three independent latest-execution panels and enforced step-01 gating.
- Idempotent RHEL 10.2 network application with no-op compliance detection, independently applied management/private changes, and `pcs status` protection against private-network changes after cluster formation.
- Hypervisor column in the main project list, with `N/A` for projects without one.
- Stylized Projects heading icon and chronological project numbering, starting at `01` for the oldest project.
- Sortable project number, name, customer, target, creation, and modification columns with column-aware project search.
- Remote Ready status in the project list, enabled when every node has passed all three step-00 operations.
- Red Stop-style workflow action state for failed step-00 operations and remote workflow steps, while preserving retry access.
- Red Remote Ready arrow when at least one node has failed SSH bootstrap discovery.
- Minimal Home and notebook navigation icons, right-aligned Changelog link, and visible current software version.
- RHEL 10.2 support and gated remote execution with per-node results for step 04 cluster connectivity checks.

## [0.1.1] - 2026-09-04

### Added

- AGPL-3.0 copyleft license and community contribution/security documentation.
- Editable primary and secondary node interface selectors with reusable custom names.
- Node cloning, cluster nodename, automatic hostname derivation, and duplicate identity/IP detection.
- Official project logo in the repository, README, application header, and browser bookmarks.
- High-contrast white logo background for application navigation and browser bookmarks.
- User-provided official spherical logo replaces the generated header and favicon treatment.
- Read-only RHEL 9.8 network-interface verification as generated step 02.
- Idempotent, backed-up RHEL 9.8 `/etc/hosts` population as generated step 03.
- Read-only peer resolution, routing, reachability, MTU, and duplicate-IP validation as generated step 04.
- Full-screen in-page viewer for every generated workflow script.
- CIDR-based node addressing with required management gateway and optional cluster/private gateway.
- Guided two-node PostgreSQL, DB2, and Apache HA examples in the new-project form.
- RHEL 10.2 and virtual-platform defaults with persisted VMware, KVM, and Proxmox hypervisor selection.
- Sequential management and cluster/private addressing, gateways, and `enp1s0`/`enp7s0` suggestions for new RHEL 10 KVM nodes.
- Password-based root SSH bootstrap, read-only remote discovery, and confirmed peer Ed25519 key authorization.
- Per-node RHEL 10.2 NetworkManager application with timed rollback and SSH reconnection verification.
- Live network-application progress feedback with duplicate-submit prevention.
- Graphical per-node execution and PASS/FAIL reporting for read-only generated pre-checks.
- RHEL 10.2 step-02 network verification with graphical remote execution.
- Cluster/private interfaces are configured as directly connected networks with mandatory NetworkManager `never-default` routing; any recorded VLAN gateway is informational only.
- Replaced NetworkManager profiles are archived with a manifest under `/root/clusterweaver-backups/network/` before removal from `nmcli`.
- Minimal configuration, cluster, virtual-machine, and physical-server context icons.
- Project-overview warning when a node has no cluster/private IP configured.

### Changed

- Project list rows can be opened directly with a mouse or keyboard.
- Copy buttons now work from remote HTTP development addresses using a compatible clipboard fallback.
- Project details now use a compact horizontal overview and collapsible two-column workflow steps.

### Planned

- Network interface, bond, and VLAN configuration.
- Additional project lifecycle and validation features driven by verified procedures.

## [0.1.0] - 2026-09-04

### Added

- Modular Flask application with a framework-independent core.
- SQLAlchemy persistence with SQLite and an initial Alembic migration.
- Project creation, editing, listing, and detail pages.
- Node creation and editing with IP address validation.
- Explicit support for RHEL 7.0–7.9, 9.0–9.8, and 10.0–10.2.
- Explicit rejection of RHEL 8.
- Human-readable YAML project serialization.
- Separate Git history for project configuration files.
- Generated pre-check script with copy and download actions.
- Local Bootstrap assets and remote browser access support.
- Creation and last-modified timestamps in the interface.
- Breadcrumb navigation and contextual help for the Site field.
- Gunicorn deployment managed by `clusterweaver-control.service`.
- Automated core, web, YAML, generator, version, and Git tests.

### Security

- CSRF protection for web forms.
- Dedicated unprivileged system account for the service.
- Session secret stored outside the source repository.
- systemd filesystem and privilege restrictions.
