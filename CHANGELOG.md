# Changelog

All notable changes to ClusterWeaver are documented in this file.

The format follows Keep a Changelog principles. ClusterWeaver uses semantic versioning.

## [Unreleased]

### Added

- AGPL-3.0 copyleft license and community contribution/security documentation.
- Editable primary and secondary node interface selectors with reusable custom names.
- Node cloning, cluster nodename, automatic hostname derivation, and duplicate identity/IP detection.
- Official project logo in the repository, README, application header, and browser bookmarks.

### Changed

- Project list rows can be opened directly with a mouse or keyboard.

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
