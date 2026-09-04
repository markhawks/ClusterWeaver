# Changelog

All notable changes to ClusterWeaver are documented in this file.

The format follows Keep a Changelog principles. ClusterWeaver uses semantic versioning.

## [Unreleased]

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
