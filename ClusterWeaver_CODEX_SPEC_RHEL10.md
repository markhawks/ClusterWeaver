# ClusterWeaver
## Linux High Availability Cluster Builder & Lifecycle Manager

## 1. Project purpose

ClusterWeaver is a local-first web application designed to help build, document, validate, rebuild, and maintain Linux High Availability clusters.

The primary target is Red Hat Enterprise Linux clusters based on Pacemaker/Corosync and related tooling.

Initial supported operating system families:

- RHEL 7
- RHEL 9
- RHEL 10

RHEL 8 is intentionally **not supported in the initial version** because there is no real-world implementation experience to use as the initial baseline. Support can be added later if needed.

The application is not intended to be only a "command generator". It should become a practical lifecycle tool that stores the complete configuration history of every cluster and can regenerate the exact commands/scripts needed for future maintenance.

Typical use cases:

- Create a new HA cluster from scratch.
- Generate copy/paste-ready commands.
- Generate Bash scripts.
- Generate Ansible playbooks when Ansible is available.
- Rebuild a corrupted/reinstalled node.
- Add a new node to an existing cluster.
- Recreate network, storage, Pacemaker, fencing, resource, and constraint configuration.
- Validate that the final configuration is correct.
- Store the cluster history for future disaster recovery or maintenance.
- Reuse a previous project as a template for a new cluster.

---

# 2. Core design principles

ClusterWeaver must be:

- Local-first.
- Simple to deploy.
- Usable even from restricted customer environments.
- Friendly to copy/paste workflows.
- Human-readable even if the web application or database is unavailable.
- Version-controlled.
- Modular.
- Extensible.
- Safe: generated commands must be reviewable before execution.
- Practical for real sysadmin workflows.

The application must **never depend exclusively on a database**.

SQLite is used for indexing, search, metadata, relationships, and application state.

Every project must also exist as human-readable files on disk.

Git is used to version project files.

This creates three layers:

1. SQLite → fast application database and search/index.
2. Files on disk → readable source of truth.
3. Git → history, diff, rollback, audit trail.

---

# 3. Suggested technology stack

## Backend

Preferred stack:

- Python 3
- Flask
- SQLAlchemy
- Jinja2
- SQLite

Optional later evolution:

- PostgreSQL
- MariaDB

Use SQLAlchemy from the beginning so migration away from SQLite remains easy.

## Frontend

Keep the frontend intentionally simple.

Suggested:

- HTML5
- CSS
- Bootstrap
- Vanilla JavaScript
- Jinja2 templates

Avoid a heavy SPA framework for the first releases.

The application should run locally with minimal dependencies and be easy to understand and maintain.

---

# 4. Application concept

The main object in ClusterWeaver is a **Project**.

A project represents one real cluster.

Example:

```text
Customer: Example Customer
Project: DB2 Production Cluster
Created: 2026-09-02
OS: RHEL 9.8
Architecture: Physical
Sites:
  - Firenze
  - Siena
Nodes: 4
Cluster type: Geographic HA Cluster
```

Each project contains all information necessary to reconstruct the cluster.

---

# 5. Main UI

The application should use a web interface.

## Main layout

Preferred desktop layout:

### Left panel — Configuration wizard

Contains forms for all project parameters.

Examples:

- Project information
- Customer
- Cluster name
- RHEL version
- Number of nodes
- Physical or virtual
- Hardware vendor/model
- Site topology
- Networks
- Interfaces
- Bonds
- VLANs
- Storage
- Multipath
- STONITH
- Pacemaker resources
- Resource groups
- Constraints
- Application services
- Validation options

### Center panel — Cluster overview

Display a human-readable visual summary of the cluster.

Initial version can use simple cards/tables.

Possible future version:

- Nodes
- Sites
- Network relationships
- Resource groups
- Storage mappings
- Active/DR roles
- Cluster topology diagram

### Right panel — Generated output

Generated configuration is divided into logical steps.

Example:

```text
01 - Pre-checks
02 - Hostname and /etc/hosts
03 - Packages
04 - Network configuration
05 - Storage and multipath
06 - pcs authentication
07 - Cluster creation
08 - Corosync configuration
09 - STONITH
10 - LVM
11 - Filesystems
12 - Virtual IPs
13 - Application resources
14 - Constraints
15 - Cluster properties
16 - Validation
17 - Failover tests
```

Each step should have:

- Title
- Description
- Generated code
- Copy button
- Download script button
- Mark as executed
- Execution notes
- Validation result
- Regenerate button

The generated text must be easy to copy from a Windows VM into an SSH terminal.

---

# 6. Project workflow

Suggested workflow:

```text
Create Project
     |
     v
Project Metadata
     |
     v
Nodes
     |
     v
Network
     |
     v
Storage
     |
     v
Cluster Core
     |
     v
STONITH
     |
     v
Resources
     |
     v
Constraints
     |
     v
Validation
     |
     v
Save Snapshot
```

The user must be able to move back and forth between sections.

No configuration should be lost when changing pages.

---

# 7. Supported RHEL versions

Initial support:

```text
RHEL 7
RHEL 9
RHEL 10
```

RHEL 8:

```text
Not supported initially.
```

Version-specific templates should be isolated from each other.

Suggested structure:

```text
templates/
  rhel7/
  rhel9/
  rhel10/
```

Do not mix commands for different major versions.

The generator should select commands based on the project's OS major version.

---

# 8. Cluster configuration sections

## 8.1 Project metadata

Fields:

- Project UUID
- Project name
- Customer
- Environment
  - DEV
  - TEST
  - PREPROD
  - PROD
  - DR
- Creation date
- Last update
- Description
- Notes
- Tags

---

## 8.2 Operating system

Fields:

- Distribution
- Major version
- Minor version
- Architecture
- Kernel version if known
- Subscription/repository notes

Initial distributions:

```text
Red Hat Enterprise Linux
```

Possible future distributions:

- Rocky Linux
- AlmaLinux
- SUSE Linux Enterprise Server

Do not design the internal model so tightly around RHEL that future extension becomes impossible.

---

## 8.3 Nodes

Each node should contain:

- Hostname
- FQDN
- Management IP
- Cluster private IP
- Service IPs if applicable
- Site
- Role
- Hardware type
- Physical/virtual
- CPU
- RAM
- Notes

Example roles:

- Primary site node
- DR site node
- DB node
- Application node

---

# 9. Network model

ClusterWeaver must describe network topology explicitly.

Objects:

- Physical interfaces
- Bonds
- VLANs
- Bridges if needed
- Management network
- Cluster private network
- Service network
- Storage network if applicable

Interface fields:

- Interface name
- MAC address
- Speed
- Driver
- PCI address
- Switch/fabric
- VLAN
- MTU
- Role

Bond fields:

- Bond name
- Mode
- Members
- Primary interface
- miimon
- fail_over_mac
- MTU

Typical supported modes:

- active-backup
- 802.3ad

Do not assume bonding is always used.

---

# 10. Storage model

Support:

- FC SAN
- iSCSI
- Local disks
- VMware shared disks

Storage objects:

- LUN
- WWID
- Device
- Multipath alias
- Size
- Vendor
- Product
- Filesystem
- Mountpoint
- Volume group
- Logical volume
- Cluster resource name

For FC environments also store:

- WWPN
- WWNN
- HBA
- Fabric
- Target ports if known

---

# 11. Pacemaker / Corosync model

Store:

- Cluster name
- Nodes
- Cluster transport
- Corosync links/rings
- Quorum configuration
- Cluster properties
- Resource defaults
- Operation defaults
- Startup/failure policies

Examples of properties that may be generated:

- stonith-enabled
- no-quorum-policy
- cluster-recheck-interval
- resource-stickiness
- migration-threshold

Exact commands must be version-specific.

---

# 12. STONITH

STONITH is a first-class configuration section.

Possible initial agents:

- fence_vmware_rest
- fence_idrac
- fence_redfish
- fence_ipmilan
- other Pacemaker fence agents

Fields:

- Agent
- Device name
- Host mapping
- IP/hostname
- Username
- Password placeholder/reference
- Port
- SSL options
- pcmk_host_map
- pcmk_host_list
- pcmk_reboot_action
- timeout
- delay
- topology level

IMPORTANT:

Do not store clear-text passwords in Git.

Secrets should be:

- excluded from exported configuration files, or
- stored as placeholders, or
- stored separately in a non-versioned local secrets file.

Example:

```text
${IDRAC_PASSWORD_NODE1}
```

---

# 13. Resources

Support Pacemaker resources such as:

- LVM-activate
- Filesystem
- IPaddr2
- systemd
- SAPInstance
- custom agents

Resources may belong to groups.

Example:

```text
RG-DB2
  LVM_DB2
  FS_DB2
  VIP_DB2
  SERVICE_DB2
```

Store:

- Resource ID
- Agent
- Parameters
- Operations
- Meta attributes
- Group
- Dependencies
- Notes

---

# 14. Constraints

Support:

- Location constraints
- Colocation constraints
- Ordering constraints
- Resource stickiness
- Site preference

This is particularly important for geographic clusters.

Example requirement:

```text
Firenze = preferred production site
Siena = disaster recovery site
```

Resources may normally remain on Firenze and move to Siena only when required.

The project data model must be able to represent this.

---

# 15. Generated outputs

ClusterWeaver should generate multiple forms of output.

## Bash / command mode

Primary mode.

Optimized for copy/paste.

Example:

```bash
echo "=== Configure pcs ==="

dnf install -y pcs pacemaker fence-agents-all

systemctl enable --now pcsd

echo "=== DONE ==="
```

Generated blocks should ideally:

- be idempotent where practical
- use clear comments
- print start/end markers
- stop or warn on critical errors
- create logs
- be safe to execute manually

## Bash script mode

Downloadable `.sh`.

## Ansible mode

Optional but supported.

Generate:

- inventory
- variables
- playbooks
- roles where useful

Ansible must **not** be mandatory.

A customer environment may only allow copy/paste.

---

# 16. Validation framework

Validation is a core feature.

Examples:

## OS validation

- Supported RHEL version
- Required packages installed
- SELinux state
- firewalld state
- time synchronization
- hostname resolution

## Network validation

- Interfaces up
- Bond state
- VLAN state
- MTU consistency
- node-to-node ping
- private network communication

## Storage validation

- HBA state
- FC link
- LUN visibility
- multipath paths
- WWID consistency
- filesystem visibility

## Cluster validation

Commands may include:

```text
pcs status
pcs status --full
pcs config
corosync-cfgtool -s
corosync-quorumtool -s
```

Exact commands depend on RHEL/Pacemaker version.

## STONITH validation

- Device exists
- Node mapping is correct
- Manual fencing test
- Cluster recovery after fencing

## Resource validation

- Resource state
- Group state
- Constraint state
- Failover test
- Failback test if applicable

Each validation step should have:

```text
Expected result
Actual result
PASS / FAIL / WARNING
Notes
```

---

# 17. Rebuild functionality

This is a key ClusterWeaver feature.

The user should be able to open an existing project and select:

```text
Maintenance
  Rebuild node
  Add node
  Replace node
  Recreate network
  Recreate storage config
  Recreate STONITH
  Recreate resources
```

Example:

```text
Project:
DB2 Cluster - 2026-09-02

Action:
Rebuild Node 2
```

ClusterWeaver should generate only the relevant steps needed for Node 2.

This avoids manually searching old notes.

---

# 18. Project history

Every saved project should preserve history.

Example:

```text
v1 - Initial cluster creation
v2 - Added STONITH
v3 - Added DB2 resource
v4 - Modified location constraint
v5 - Added third node
```

Every save should optionally create a Git commit.

Suggested commit messages:

```text
Create project
Configure network
Add cluster nodes
Configure STONITH
Add DB2 resource group
Update location constraints
Rebuild node03 configuration
```

---

# 19. Filesystem storage

Suggested root:

```text
/var/lib/clusterweaver/
```

or during development:

```text
./data/
```

Suggested structure:

```text
data/
├── clusterweaver.db
├── projects/
│   ├── customer-a/
│   │   └── db2-prod/
│   │       ├── project.yaml
│   │       ├── nodes.yaml
│   │       ├── network.yaml
│   │       ├── storage.yaml
│   │       ├── cluster.yaml
│   │       ├── resources.yaml
│   │       ├── constraints.yaml
│   │       ├── README.md
│   │       ├── generated/
│   │       │   ├── 01-prechecks.sh
│   │       │   ├── 02-network.sh
│   │       │   ├── 03-storage.sh
│   │       │   ├── 04-cluster.sh
│   │       │   ├── 05-stonith.sh
│   │       │   ├── 06-resources.sh
│   │       │   └── 99-validation.sh
│   │       └── logs/
│   └── customer-b/
└── templates/
```

Prefer YAML for project configuration because it is very readable for sysadmins.

JSON may still be used internally/API-side.

---

# 20. SQLite database

SQLite is used for metadata and fast searches.

Suggested tables:

```text
projects
customers
nodes
interfaces
networks
bonds
vlans
storage_devices
multipath_devices
cluster_settings
stonith_devices
resources
resource_groups
constraints
generated_scripts
validation_checks
project_versions
execution_notes
```

Do not store generated scripts only in SQLite.

Generated scripts must also exist as files.

---

# 21. Git integration

Each project directory may be its own Git repository, or all projects may initially be stored in one repository.

Recommended initial implementation:

```text
data/projects/.git
```

A single local repository is simpler.

Every meaningful save can create a commit.

Features:

- View history
- View diff
- Restore previous version
- Compare configurations
- Show who/when changed a configuration

Future:

- Push to private Git server
- GitLab
- Gitea
- GitHub private repo

Remote Git must remain optional.

---

# 22. Search

The UI should allow searching historical clusters.

Search fields:

- Customer
- Project name
- Cluster name
- Date
- Hostname
- IP
- RHEL version
- Hardware vendor
- Application
- Resource name
- Site
- Tag

Example:

```text
Search:
DB2 2026
```

Possible result:

```text
Customer X
DB2 Production Cluster
Created: 2026-09-02
RHEL 9.8
4 nodes
Firenze / Siena
```

---

# 23. Templates

Existing projects can become templates.

Example templates:

```text
RHEL 9 - 2 Node VMware Cluster
RHEL 9 - 4 Node Dell Geo Cluster
RHEL 9 - PostgreSQL Cluster
RHEL 10 - JBoss Cluster
RHEL 7 - Legacy 2 Node Cluster
```

A template should contain structure and defaults but not customer-specific secrets.

---

# 24. Security

The application may contain infrastructure data.

Minimum requirements:

- Listen on localhost by default.
- No public exposure by default.
- Optional authentication.
- CSRF protection.
- Session protection.
- Never commit passwords or API secrets.
- Sensitive fields masked in the UI.
- Secrets stored outside Git.
- Exported scripts use placeholders for secrets.

Possible later support:

- encrypted secrets store
- HashiCorp Vault
- Ansible Vault

Not needed for MVP.

---

# 25. Suggested repository structure

```text
clusterweaver/
├── app/
│   ├── __init__.py
│   ├── models/
│   ├── routes/
│   ├── services/
│   ├── generators/
│   ├── validators/
│   ├── forms/
│   ├── templates/
│   └── static/
│
├── cluster_templates/
│   ├── rhel7/
│   │   ├── commands/
│   │   └── validation/
│   ├── rhel9/
│   │   ├── commands/
│   │   └── validation/
│   └── rhel10/
│       ├── commands/
│       └── validation/
│
├── data/
│   ├── projects/
│   └── clusterweaver.db
│
├── migrations/
├── tests/
├── docs/
│   ├── architecture.md
│   ├── data-model.md
│   └── generator-design.md
│
├── config.py
├── requirements.txt
├── run.py
├── README.md
└── .gitignore
```

---

# 26. Generator architecture

Do not hardcode large command strings directly inside Flask routes.

Use dedicated generators.

Example:

```text
app/generators/
├── base.py
├── network.py
├── storage.py
├── pacemaker.py
├── stonith.py
├── resources.py
└── validation.py
```

Version-specific command templates:

```text
cluster_templates/rhel9/commands/
```

The generator receives a normalized project model and returns generated steps.

Conceptually:

```python
generate_network(project)
generate_storage(project)
generate_cluster(project)
generate_stonith(project)
generate_resources(project)
generate_validation(project)
```

---

# 27. Validation architecture

Validators should be independent from generators.

Example:

```text
app/validators/
├── project.py
├── network.py
├── storage.py
├── pacemaker.py
├── stonith.py
└── resources.py
```

They should validate both:

1. Input data before generation.
2. Real command output pasted back by the user.

Future possibility:

ClusterWeaver may optionally connect to nodes using SSH and run validation automatically.

This is **not required for the first version**.

---

# 28. Execution model

The initial design should assume that ClusterWeaver cannot always directly access customer servers.

Therefore generated content is the primary interface.

Support:

```text
Copy command
Copy step
Copy full script
Download script
Download all scripts
Generate tar.gz bundle
```

Possible later option:

```text
Execute via SSH
```

but it must remain optional.

---

# 29. MVP — Phase 1

The first usable version should be deliberately small.

Implement:

1. Flask application.
2. SQLite database.
3. Project creation.
4. Customer/project metadata.
5. RHEL version selection:
   - RHEL 7
   - RHEL 9
   - RHEL 10
6. Node management.
7. Network interfaces.
8. Bond configuration.
9. VLAN configuration.
10. Save project as YAML.
11. Generate basic copy/paste Bash commands.
12. Display generated scripts in the web interface.
13. Copy button.
14. Project list.
15. Open/edit existing project.
16. Git commit on save.

Do **not** attempt to implement every Pacemaker feature in the first commit.

---

# 30. Phase 2

Add:

- Storage
- FC
- Multipath
- LVM
- Filesystem resources
- Cluster creation
- pcs configuration
- Corosync
- STONITH
- Resource groups
- Constraints
- Validation commands

---

# 31. Phase 3

Add lifecycle operations:

- Rebuild node
- Add node
- Replace node
- Clone project
- Convert project into template
- Version history
- Git diff
- Restore project version
- Validation results
- Execution notes

---

# 32. Phase 4

Possible future features:

- SSH execution
- Ansible generation
- Automatic inventory
- Import existing cluster using `pcs config`
- Cluster health dashboard
- Pacemaker XML/CIB parser
- Export documentation to Markdown/PDF
- Architecture diagrams
- Multi-user authentication
- PostgreSQL backend
- Git remote synchronization
- API
- Plugin system

---

# 33. Initial UX proposal

Home page:

```text
+----------------------------------------------------------+
| ClusterWeaver                                            |
| Linux High Availability Cluster Builder & Lifecycle Mgr |
+----------------------------------------------------------+

[ New Project ]

Recent Projects

DB2-PROD       Customer A     RHEL 9.8    4 nodes
JBOSS-DEV      Customer B     RHEL 10     2 nodes
LEGACY-DB      Customer C     RHEL 7.9    2 nodes

[ Search ]
```

Project page:

```text
+----------------+---------------------+----------------------+
| CONFIGURATION  | CLUSTER OVERVIEW    | GENERATED COMMANDS   |
|                |                     |                      |
| General        | Node01              | 01 Prechecks         |
| Nodes          | Node02              | [COPY] [DOWNLOAD]    |
| Network        |                     |                      |
| Storage        | bond0               | 02 Network           |
| Cluster        | bond1.927           | [COPY] [DOWNLOAD]    |
| STONITH        |                     |                      |
| Resources      | Storage             | 03 Cluster           |
| Constraints    |                     | [COPY] [DOWNLOAD]    |
| Validation     |                     |                      |
+----------------+---------------------+----------------------+
```

---

# 34. Important implementation rule

The user's real-world notes and real cluster procedures are the authoritative source for command templates.

Do not invent "generic best practices" and silently put them into generated production scripts.

When implementing a new cluster function:

1. Start from a real tested procedure.
2. Convert it to a template.
3. Parameterize variables.
4. Add validation.
5. Test against the real environment.
6. Only then mark it as supported.

ClusterWeaver should grow gradually while real clusters are being built.

This is intentional.

---

# 35. Current project philosophy

ClusterWeaver is developed incrementally.

Every time a real cluster is configured, the related procedure should be converted into reusable ClusterWeaver logic.

The application therefore becomes both:

- an automation tool
- and a living operational knowledge base

The final goal is to make cluster creation and recovery repeatable without depending on handwritten notes.

---

# 36. Initial Codex task

Start by creating the project skeleton and the first MVP.

Required first iteration:

1. Create Flask project structure.
2. Configure SQLAlchemy with SQLite.
3. Create `Project` and `Node` database models.
4. Create home page with project list.
5. Create "New Project" page.
6. Project fields:
   - project name
   - customer
   - description
   - RHEL major version
   - RHEL minor version
   - physical/virtual
   - node count
7. Support only:
   - RHEL 7
   - RHEL 9
   - RHEL 10
8. Explicitly reject/disable RHEL 8.
9. After project creation, allow adding/editing nodes.
10. Each node initially contains:
    - hostname
    - FQDN
    - site
    - management IP
    - cluster/private IP
11. Save an additional human-readable YAML representation under:

```text
data/projects/<project-slug>/project.yaml
```

12. Initialize a Git repository under:

```text
data/projects/
```

13. When a project is saved:
    - update YAML
    - create a Git commit if content changed
14. Create a first placeholder "Generated Commands" panel.
15. Add a simple generated pre-check script containing project/node information.
16. Add Copy-to-Clipboard support using JavaScript.
17. Use Bootstrap for the UI.
18. Keep code modular and easy to extend.

Do not implement storage, Pacemaker, STONITH, or Ansible yet.

The first objective is to establish a clean architecture that we can extend incrementally while building real clusters.

---

# 37. Naming

Project name:

```text
ClusterWeaver
```

Tagline:

```text
Linux High Availability Cluster Builder & Lifecycle Manager
```

Suggested repository name:

```text
clusterweaver
```

Suggested Python package:

```text
clusterweaver
```

---

# 38. Non-goals for the first release

Do not:

- support RHEL 8
- auto-execute commands on production nodes
- store passwords in Git
- require Ansible
- require PostgreSQL
- build a complex SPA
- implement all Pacemaker resource agents
- attempt automatic discovery of every cluster configuration
- hide generated commands from the user

Transparency is important: the sysadmin must always be able to see exactly what ClusterWeaver intends to execute.

---

# 39. Development priority

Priority order:

```text
Correctness
Readability
Recoverability
Maintainability
Safety
Automation
UI polish
```

The system is intended for production infrastructure work.

Generated commands must therefore remain understandable and reviewable by a Linux administrator.


---

# 40. Development Platform Decision — RHEL 10.2

ClusterWeaver development is now standardized on a dedicated **Red Hat Enterprise Linux 10.2** development VM.

Fedora 44 may be used as the developer workstation, browser, terminal, or editor host, but the canonical development/runtime environment for ClusterWeaver is RHEL 10.2.

Suggested development VM baseline:

```text
Hostname: clusterweaver-dev
OS:       Red Hat Enterprise Linux 10.2
CPU:      2 vCPU minimum
RAM:      4 GB minimum
Disk:     30 GB minimum
```

Do not assume that ClusterWeaver running on RHEL 10.2 means that it only manages RHEL 10 clusters.

Initial cluster target versions remain:

```text
RHEL 7  - supported target
RHEL 8  - NOT supported
RHEL 9  - supported target
RHEL 10 - supported target
```

The application runtime and the generated cluster configuration templates are separate concepts.

---

# 41. Python / Flask Architecture Decision

Use Python as the primary application language.

Use Flask for the initial web interface.

However, **ClusterWeaver Core must not depend on Flask**.

This is a mandatory architectural rule.

The intended architecture is:

```text
                    +-------------------+
                    | ClusterWeaver Core |
                    +---------+---------+
                              |
          +-------------------+-------------------+
          |                   |                   |
     Generators           Validators            Parsers
          |                   |                   |
          +-------------------+-------------------+
                              |
                     Normalized Project Model
                              |
                  +-----------+-----------+
                  |                       |
              Flask Web UI             Future CLI
```

Flask is an interface to the core, not the core itself.

Do not place cluster-generation logic, Pacemaker logic, validation logic, Git logic, or YAML serialization logic directly inside Flask routes.

Routes should remain thin.

Bad:

```python
@app.route("/generate")
def generate():
    # hundreds of lines of cluster logic
    ...
```

Preferred:

```python
@app.route("/generate")
def generate():
    result = generator_service.generate(project)
    return render_template("generated.html", result=result)
```

This separation is required so that a future CLI can reuse the same engine:

```text
clusterweaver project list
clusterweaver project show DB2-PROD
clusterweaver generate DB2-PROD
clusterweaver validate DB2-PROD
clusterweaver rebuild DB2-PROD node02
```

A CLI is not required in the first implementation, but the architecture must not prevent it.

---

# 42. Web Stack Decision

Initial web stack:

```text
Python 3
Flask
Jinja2
Bootstrap
Vanilla JavaScript
SQLAlchemy
Alembic
SQLite
PyYAML
Git
```

Keep frontend dependencies minimal.

Do not introduce React, Vue, Angular, Node.js, Redis, Celery, or a separate frontend build pipeline unless a future requirement clearly justifies them.

The project favors boring, stable, understandable technology over unnecessary complexity.

---

# 43. Python Environment

Do not install ClusterWeaver Python dependencies globally into the RHEL system Python environment.

Use a Python virtual environment.

Recommended development layout:

```text
/opt/clusterweaver/
├── .venv/
├── clusterweaver/
├── data/
├── docs/
├── tests/
└── ...
```

Development should normally be performed by a non-root user with appropriate permissions on the project directory.

The application must not require root privileges merely to start the web UI.

System-level actions should remain clearly separated from application development.

---

# 44. Dependency Management

Dependencies must be explicitly recorded and reproducible.

For the initial implementation, use a conventional Python dependency file.

At minimum track:

```text
Flask
SQLAlchemy
Alembic
PyYAML
```

Add other dependencies only when they provide a concrete benefit.

Avoid unnecessary libraries.

Pin or constrain dependency versions in a maintainable way so that a future environment can reproduce a known-good installation.

Do not depend on random globally installed Python modules.

---

# 45. Database Evolution

Use SQLite initially.

Use SQLAlchemy for persistence.

Use Alembic for schema migrations from the beginning.

The database must be treated as an application index/state store, not as the only copy of cluster knowledge.

Human-readable YAML project files remain mandatory.

Generated scripts remain normal files on disk.

Therefore:

```text
SQLite     -> application/search/index
YAML       -> human-readable cluster definition
Generated  -> human-readable executable/reference scripts
Git        -> history and change tracking
```

A database failure must not make historical cluster configuration unreadable.

The architecture should allow a future migration to PostgreSQL without rewriting ClusterWeaver Core.

---

# 46. Project Configuration Format

Prefer YAML for human-readable project configuration.

A project should eventually be reconstructable from its YAML files even if the SQLite database is unavailable.

Example:

```yaml
project:
  name: DB2-PROD
  customer: Example Customer
  os:
    distribution: rhel
    major: 9
    minor: 8

nodes:
  - hostname: node01
    site: firenze
    management_ip: 10.0.0.11
    cluster_ip: 192.168.10.11

  - hostname: node02
    site: firenze
    management_ip: 10.0.0.12
    cluster_ip: 192.168.10.12
```

Do not store secrets in these Git-tracked YAML files.

---

# 47. Local Git Strategy

Git is part of the design, not merely a developer tool.

The source repository versions ClusterWeaver itself.

Separately, project configuration/history should be versionable.

For the initial implementation, a local Git repository under:

```text
data/projects/
```

is acceptable.

Do not automatically commit database binary files.

Git should primarily version:

```text
YAML
Markdown
generated scripts
non-secret configuration
```

Example project-history commits:

```text
Create DB2-PROD project
Add node01 and node02
Configure private network
Add bond1
Configure STONITH
Add DB2 resource group
Change Firenze location preference
Rebuild node02 configuration
```

All Git operations must be encapsulated behind a service/module so Git implementation details do not leak into Flask routes.

---

# 48. Secrets Policy

Never store real customer passwords, tokens, iDRAC credentials, VMware credentials, or other secrets in Git.

Generated scripts should use placeholders such as:

```text
${IDRAC_PASSWORD_NODE01}
${VMWARE_PASSWORD}
```

For the MVP, placeholders are sufficient.

A dedicated secret-management system may be implemented later.

Do not implement Vault or another complex secret manager in the first iteration.

---

# 49. UI Philosophy

The web interface is optimized for a sysadmin working through restricted customer access.

A common real-world workflow is:

```text
Linux workstation
      |
      v
Windows VM
      |
      v
Customer VPN
      |
      v
SSH / terminal
      |
      v
RHEL cluster nodes
```

Direct automation may therefore be impossible.

Copy/paste is a first-class execution method, not a temporary workaround.

Generated commands must:

- be clearly visible
- be selectable
- have a Copy button
- be divided into logical steps
- avoid unnecessary line wrapping
- be understandable before execution
- include useful comments
- clearly identify the target node where relevant

Future SSH/Ansible execution is optional and must not replace manual copy/paste support.

---

# 50. Generated Script Philosophy

Generated scripts must be suitable both for direct execution and for use as operational documentation.

Prefer small logical scripts over one giant script.

Example:

```text
01-prechecks.sh
02-packages.sh
03-network.sh
04-storage.sh
05-cluster-bootstrap.sh
06-stonith.sh
07-resources.sh
08-constraints.sh
99-validation.sh
```

Where a step differs per node, make the target explicit.

For example:

```text
03-network-node01.sh
03-network-node02.sh
```

Generated scripts should ideally include:

```bash
#!/bin/bash

set -o pipefail

echo "=== ClusterWeaver: Network configuration ==="
echo "=== Target: node01 ==="
```

Do not blindly add `set -e` to every generated production script. Error handling must be designed per operation because some diagnostic or idempotency checks may legitimately return non-zero.

---

# 51. Version-Specific Cluster Logic

RHEL major versions must remain isolated.

Suggested structure:

```text
cluster_templates/
├── rhel7/
│   ├── commands/
│   └── validation/
├── rhel9/
│   ├── commands/
│   └── validation/
└── rhel10/
    ├── commands/
    └── validation/
```

There must be no `rhel8` directory in the initial implementation.

If the user selects or imports RHEL 8, the application must clearly report:

```text
RHEL 8 is not currently supported by ClusterWeaver.
```

Do not silently reuse RHEL 9 commands for RHEL 8.

Similarly, do not assume commands are identical between RHEL 7, RHEL 9, and RHEL 10.

---

# 52. Real-World Procedure Rule

ClusterWeaver will be developed while real clusters are being implemented.

A real, verified procedure is the preferred source for a production generator.

Workflow:

```text
Real cluster work
      |
      v
Verified manual procedure
      |
      v
Parameterize
      |
      v
ClusterWeaver template/generator
      |
      v
Validation
      |
      v
Reusable supported workflow
```

Do not attempt to invent every possible Pacemaker configuration in advance.

Do not mark a workflow as supported merely because a command appears syntactically plausible.

Favor tested procedures and incremental implementation.

---

# 53. Maintainability Requirements

ClusterWeaver is intended to remain maintainable for many years.

Code should prioritize:

```text
Correctness
Readability
Recoverability
Maintainability
Safety
Testability
Automation
UI polish
```

Requirements:

- Python modules should have clear responsibilities.
- Avoid circular dependencies.
- Keep Flask routes thin.
- Core logic must be testable without running a web server.
- Database access should be isolated from business logic where practical.
- Generated output must be deterministic when given the same project configuration.
- Avoid hidden magic.
- Prefer explicit configuration.
- Add type hints where useful.
- Add docstrings to non-obvious public functions/classes.
- Add tests for generator behavior.
- Never make destructive cluster operations implicit.

---

# 54. Testing Strategy

Start testing from the first MVP.

At minimum create tests for:

```text
Project creation
Node creation
RHEL version validation
RHEL 8 rejection
YAML serialization
YAML round-trip where applicable
slug/path generation
generator output
Git-change detection
```

As real cluster generators are added, use known input fixtures and expected command output.

Example:

```text
tests/
├── fixtures/
│   ├── rhel7/
│   ├── rhel9/
│   └── rhel10/
├── test_projects.py
├── test_yaml.py
├── test_generators.py
└── test_version_support.py
```

Tests must not require access to real production cluster nodes.

Integration tests requiring actual RHEL/Pacemaker nodes can be added separately later.

---

# 55. Development vs Production Runtime

During development, running the Flask development server is acceptable.

Do not treat the Flask development server as the final production deployment model.

Later, when ClusterWeaver needs a persistent deployment, choose an appropriate WSGI deployment method and optionally place it behind Apache or another reverse proxy.

This production deployment work is not part of the first MVP.

---

# 56. Updated Repository Layout

Use the following architecture as the starting point:

```text
clusterweaver/
├── clusterweaver/
│   ├── __init__.py
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── models/
│   │   ├── generators/
│   │   ├── validators/
│   │   ├── parsers/
│   │   ├── serializers/
│   │   └── services/
│   │
│   ├── web/
│   │   ├── __init__.py
│   │   ├── routes/
│   │   ├── forms/
│   │   ├── templates/
│   │   └── static/
│   │
│   ├── persistence/
│   │   ├── database.py
│   │   ├── repositories/
│   │   └── migrations/
│   │
│   └── cli/
│       └── __init__.py
│
├── cluster_templates/
│   ├── rhel7/
│   │   ├── commands/
│   │   └── validation/
│   ├── rhel9/
│   │   ├── commands/
│   │   └── validation/
│   └── rhel10/
│       ├── commands/
│       └── validation/
│
├── data/
│   ├── projects/
│   └── clusterweaver.db
│
├── docs/
├── tests/
├── migrations/
├── .gitignore
├── README.md
├── requirements.txt
└── run.py
```

The exact number of Python files may evolve, but preserve the architectural boundaries.

---

# 57. First Development Session on RHEL 10.2

Codex should begin with environment inspection before changing the system.

First inspect:

```bash
cat /etc/redhat-release
python3 --version
git --version
```

If required packages are missing, report the exact packages needed before assuming installation.

Do not make broad system configuration changes.

The expected project location is:

```text
/opt/clusterweaver
```

If the repository is instead provided in another working directory, use the existing repository and do not move it without instruction.

Use:

```text
.venv
```

inside the repository for Python dependencies.

The `.venv` directory must be ignored by Git.

Also ignore:

```text
__pycache__/
*.pyc
data/clusterweaver.db
secret files
runtime logs
```

Do not ignore the human-readable project YAML files or generated non-secret scripts that form part of project history.

---

# 58. Updated First Codex Implementation Task

Implement only the architectural foundation and first usable MVP.

## Step A — Inspect

Inspect the existing repository and environment.

Do not overwrite useful existing work.

## Step B — Skeleton

Create the modular package layout described above.

## Step C — Application bootstrap

Implement a Flask application factory.

Avoid a monolithic `app.py`.

## Step D — Persistence

Configure:

```text
SQLAlchemy
SQLite
Alembic
```

Create initial migrations.

## Step E — Core models

Implement initial domain concepts for:

```text
Project
Node
```

Keep domain/business concepts separate from Flask request objects.

## Step F — Supported OS validation

Supported:

```text
RHEL 7
RHEL 9
RHEL 10
```

Unsupported:

```text
RHEL 8
```

The validation should live in core logic and be testable without Flask.

## Step G — Project UI

Implement:

```text
Home / project list
New project
Project detail
Edit project
Add node
Edit node
```

Project fields:

```text
Project name
Customer
Description
RHEL major
RHEL minor
Physical / Virtual
Node count
```

Node fields:

```text
Hostname
FQDN
Site
Management IP
Cluster/private IP
```

## Step H — YAML

Every project must have a human-readable representation under:

```text
data/projects/<project-slug>/project.yaml
```

YAML generation must be implemented outside Flask routes.

## Step I — Git service

Implement a small Git service abstraction.

Initialize/use a local repository for:

```text
data/projects/
```

When meaningful YAML/project content changes, create a commit.

Do not commit if there is no change.

Do not commit secrets or SQLite database files.

## Step J — First generator

Create a very small generator that produces a pre-check script from the project/node information.

The generator must live under core generators and must not depend on Flask.

Display the generated script in the project web page.

Provide:

```text
Copy
Download
```

for the generated output.

## Step K — Tests

Implement automated tests for the initial behavior, especially:

```text
supported RHEL versions
RHEL 8 rejection
project model
node model
YAML generation
generator output
```

## Step L — Documentation

Update README with:

```text
development prerequisites
virtualenv creation
dependency installation
database initialization/migration
development server startup
test execution
directory layout
```

---

# 59. Codex Guardrails

For the first implementation, Codex must NOT:

- implement Pacemaker commands beyond placeholder/pre-check generation
- implement STONITH
- implement storage
- implement multipath
- implement Ansible
- implement SSH execution
- introduce Docker/Podman as a requirement
- introduce PostgreSQL
- introduce React/Vue/Angular
- introduce Node.js tooling
- introduce RHEL 8 support
- store secrets in Git
- execute generated cluster commands
- perform destructive system changes
- tightly couple core logic to Flask

If an architectural decision is unclear, prefer the simpler implementation that preserves future extensibility.

---

# 60. Immediate Goal

The immediate goal is not to automate an entire cluster.

The immediate goal is to obtain a clean working application on RHEL 10.2 where the user can:

```text
Open ClusterWeaver
        |
        v
Create project
        |
        v
Select RHEL 7 / 9 / 10
        |
        v
Add nodes
        |
        v
Save
        |
        +--> SQLite index
        |
        +--> project.yaml
        |
        +--> Git history
        |
        v
Generate pre-check script
        |
        v
View / Copy / Download
```

Once this works cleanly, real cluster procedures will be introduced incrementally.
