# Contributing to ClusterWeaver

Thank you for helping improve ClusterWeaver.

## Before contributing

- Open an issue before starting a large change.
- Base production generators on a real, verified cluster procedure.
- Never include customer names, infrastructure data, credentials, tokens, or secrets.
- Keep RHEL 7, RHEL 9, and RHEL 10 command logic isolated.
- Do not add RHEL 8 templates until support is explicitly designed and verified.

## Development workflow

1. Fork the repository and create a focused branch.
2. Create a Python virtual environment and install `requirements.txt`.
3. Implement the change without coupling core logic to Flask.
4. Add or update automated tests.
5. Run `pytest -q` and `alembic check`.
6. Update `CHANGELOG.md` under `Unreleased`.
7. Open a pull request describing the operational procedure and validation used.

By submitting a contribution, you agree that it is licensed under Apache License 2.0.
