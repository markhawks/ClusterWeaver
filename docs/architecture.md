# Architecture

ClusterWeaver uses explicit boundaries:

- `clusterweaver.core` contains framework-independent domain values, validation, serialization, generation, and filesystem/Git services.
- `clusterweaver.persistence` maps SQLAlchemy records and converts them to core domain values.
- `clusterweaver.web` is a thin Flask adapter responsible for HTTP, forms, and presentation.
- YAML files are the human-readable cluster definition; SQLite supports application state and search; Git records meaningful project-file changes.

The current pre-check generator reports intended project and node information plus read-only local system commands. It does not configure a cluster.

