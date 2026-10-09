"""Explicit SSH credentials; private keys never belong to portable project data."""
from dataclasses import dataclass, field, replace
from pathlib import Path


@dataclass(frozen=True)
class SSHCredentials:
    private_key: Path | None = None
    known_hosts: Path | None = None
    password: str | None = field(default=None, repr=False)
    enroll_host: bool = False
    expected_host_key: object | None = field(default=None, repr=False)

    def for_reconnect(self, key):
        return replace(self, expected_host_key=key)


def credential_secret(credentials):
    return (credentials.password or "") if isinstance(credentials, SSHCredentials) else (credentials or "")


def redact_output(output, credentials):
    secret = credential_secret(credentials)
    return output.replace(secret, "[redacted]") if secret else output
