from __future__ import annotations

import base64
import hashlib
import shlex
import time
import os
import stat
import fcntl
import tempfile
from dataclasses import dataclass

import paramiko

from clusterweaver.core.services.ssh_credentials import SSHCredentials, redact_output


DISCOVERY_COMMAND = """set -o pipefail
echo '--- identity ---'
hostnamectl 2>/dev/null || hostname
echo '--- release ---'
cat /etc/redhat-release
echo '--- interfaces ---'
ip -brief link
ip -brief -4 address
echo '--- routes ---'
ip -4 route
echo '--- networkmanager ---'
nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device status 2>/dev/null || true
"""


@dataclass(slots=True)
class SSHResult:
    hostname: str
    endpoint: str
    ok: bool
    output: str
    fingerprint: str = ""


def _fingerprint(key: paramiko.PKey) -> str:
    digest = hashlib.sha256(key.asbytes()).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


class ProjectHostKeyPolicy(paramiko.MissingHostKeyPolicy):
    def __init__(self, credentials):
        self.credentials = credentials

    def missing_host_key(self, client, hostname, key):
        credentials = self.credentials
        existing = client.get_host_keys().lookup(hostname)
        if existing:
            raise ValueError("SSH host key changed for " + hostname + "; verify the node fingerprint before updating known_hosts.")
        if credentials.expected_host_key is not None:
            if key != credentials.expected_host_key:
                raise ValueError("SSH host key at the new IP does not match the original node; network rollback remains armed.")
        elif not credentials.enroll_host:
            raise ValueError("SSH host identity is not enrolled for " + hostname + "; install the project public key using the current root password first.")
        path = credentials.known_hosts
        if path is None:
            raise ValueError("Project known_hosts file is not configured.")
        fd = os.open(str(path) + '.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            keys = paramiko.HostKeys()
            if path.exists() or path.is_symlink():
                _check_credential_file(path)
                keys.load(str(path))
            known = keys.lookup(hostname)
            if known and not keys.check(hostname, key):
                raise ValueError("Conflicting SSH host key detected while enrolling " + hostname + ".")
            keys.add(hostname, key.get_name(), key)
            tmp_fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix='.known-hosts-')
            os.close(tmp_fd)
            try:
                keys.save(tmp_name)
                os.replace(tmp_name, path)
            finally:
                if os.path.exists(tmp_name):
                    os.unlink(tmp_name)
            client.get_host_keys().add(hostname, key.get_name(), key)
        finally:
            os.close(fd)


def _check_credential_file(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise ValueError("SSH credentials must be service-owned regular files with mode 0600.")


def _connect(node, password) -> tuple[paramiko.SSHClient, str]:
    if not node.bootstrap_ip:
        raise ValueError("SSH bootstrap IP is not configured.")
    client = paramiko.SSHClient()
    credentials = password if isinstance(password, SSHCredentials) else None
    try:
        pkey = None
        if credentials:
            if credentials.private_key is not None:
                _check_credential_file(credentials.private_key)
                pkey = paramiko.RSAKey.from_private_key_file(str(credentials.private_key))
            if credentials.known_hosts and (credentials.known_hosts.exists() or credentials.known_hosts.is_symlink()):
                _check_credential_file(credentials.known_hosts)
                client.load_host_keys(str(credentials.known_hosts))
            client.set_missing_host_key_policy(ProjectHostKeyPolicy(credentials))
        else:
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connection_options = {}
        if credentials and credentials.expected_host_key is not None:
            # On a new management IP Paramiko has no hostname entry to prefer the
            # original host-key type. Negotiate that same type before comparing it.
            allowed = {credentials.expected_host_key.get_name()}
            if "ssh-rsa" in allowed:
                allowed.update({"rsa-sha2-256", "rsa-sha2-512"})
            connection_options["disabled_algorithms"] = {
                "keys": [algorithm for algorithm in paramiko.Transport._preferred_keys if algorithm not in allowed]
            }
        client.connect(
            hostname=node.bootstrap_ip,
            port=node.ssh_port or 22,
            username="root",
            password=(None if pkey else credentials.password) if credentials else password,
            pkey=pkey,
            look_for_keys=False,
            allow_agent=False,
            timeout=8,
            banner_timeout=8,
            auth_timeout=8,
            **connection_options,
        )
        transport = client.get_transport()
        if transport is None:
            raise ConnectionError("SSH transport was not established.")
        key = transport.get_remote_server_key()
        if credentials and credentials.expected_host_key is not None and key != credentials.expected_host_key:
            raise ValueError("SSH host key does not match the original node.")
        return client, _fingerprint(key)
    except Exception:
        client.close()
        raise


def _run(client: paramiko.SSHClient, command: str) -> tuple[int, str]:
    _stdin, stdout, stderr = client.exec_command(command, timeout=20)
    return _collect_channel(stdout.channel, timeout=20)


def _collect_channel(channel, timeout: int) -> tuple[int, str]:
    """Drain both SSH streams while the command runs, retaining bounded output."""
    deadline = time.monotonic() + timeout
    output = bytearray()
    while True:
        received = False
        while channel.recv_ready():
            output.extend(channel.recv(32768))
            received = True
        while channel.recv_stderr_ready():
            output.extend(channel.recv_stderr(32768))
            received = True
        if len(output) > 20000:
            del output[:-20000]
        if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
            return channel.recv_exit_status(), output.decode("utf-8", errors="replace")
        if time.monotonic() >= deadline:
            channel.close()
            raise TimeoutError(f"Remote command exceeded the {timeout}-second execution limit.")
        if not received:
            time.sleep(0.01)


def discover_node(node, password: str | SSHCredentials) -> SSHResult:
    endpoint = f"{node.bootstrap_ip or '<not configured>'}:{node.ssh_port or 22}"
    try:
        client, fingerprint = _connect(node, password)
        try:
            status, output = _run(client, DISCOVERY_COMMAND)
        finally:
            client.close()
        return SSHResult(node.hostname, endpoint, status == 0, redact_output(output, password), fingerprint)
    except Exception as exc:  # Paramiko exposes several transport-specific exceptions.
        return SSHResult(node.hostname, endpoint, False, redact_output(str(exc), password))


def run_remote_script(node, password: str | SSHCredentials, script: str) -> SSHResult:
    """Stream a reviewed script to bash without creating a remote file."""
    endpoint = f"{node.bootstrap_ip or '<not configured>'}:{node.ssh_port or 22}"
    try:
        client, fingerprint = _connect(node, password)
        try:
            stdin, stdout, stderr = client.exec_command("bash -s --", timeout=30)
            stdin.write(script)
            stdin.channel.shutdown_write()
            status, output = _collect_channel(stdout.channel, timeout=120)
        finally:
            client.close()
        return SSHResult(node.hostname, endpoint, status == 0, redact_output(output, password), fingerprint)
    except Exception as exc:
        return SSHResult(node.hostname, endpoint, False, redact_output(str(exc), password))


def bootstrap_peer_keys(nodes, password: str | SSHCredentials) -> list[SSHResult]:
    connected: list[tuple[object, paramiko.SSHClient, str]] = []
    results: list[SSHResult] = []
    key_command = (
        "install -d -m 700 /root/.ssh && "
        "test -f /root/.ssh/id_ed25519 || "
        "ssh-keygen -q -t ed25519 -N '' -C clusterweaver-bootstrap -f /root/.ssh/id_ed25519; "
        "cat /root/.ssh/id_ed25519.pub"
    )
    try:
        for node in nodes:
            endpoint = f"{node.bootstrap_ip or '<not configured>'}:{node.ssh_port or 22}"
            try:
                client, fingerprint = _connect(node, password)
                status, public_key = _run(client, key_command)
                if status != 0 or not public_key.strip().startswith("ssh-ed25519 "):
                    client.close()
                    results.append(SSHResult(node.hostname, endpoint, False, public_key or "Could not generate the SSH key.", fingerprint))
                    continue
                connected.append((node, client, public_key.strip()))
            except Exception as exc:
                results.append(SSHResult(node.hostname, endpoint, False, redact_output(str(exc), password)))

        for target, client, _target_key in connected:
            peer_keys = [key for node, _client, key in connected if node.id != target.id]
            for key in peer_keys:
                encoded = base64.b64encode((key + "\n").encode()).decode()
                command = (
                    "install -d -m 700 /root/.ssh; touch /root/.ssh/authorized_keys; "
                    "chmod 600 /root/.ssh/authorized_keys; "
                    f"key=$(printf %s {shlex.quote(encoded)} | base64 -d); "
                    "grep -qxF \"$key\" /root/.ssh/authorized_keys || printf '%s\\n' \"$key\" >> /root/.ssh/authorized_keys"
                )
                status, output = _run(client, command)
                if status != 0:
                    results.append(SSHResult(target.hostname, f"{target.bootstrap_ip}:{target.ssh_port}", False, output or "Could not install a peer public key."))
                    break
            else:
                results.append(SSHResult(target.hostname, f"{target.bootstrap_ip}:{target.ssh_port}", True, f"Generated/reused Ed25519 key and installed {len(peer_keys)} peer public key(s)."))
    finally:
        for _node, client, _key in connected:
            client.close()
    for result in results:
        result.output = redact_output(result.output, password)
    return results
