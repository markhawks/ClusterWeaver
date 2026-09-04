from __future__ import annotations

import base64
import hashlib
import shlex
from dataclasses import dataclass

import paramiko


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


def _connect(node, password: str) -> tuple[paramiko.SSHClient, str]:
    if not node.bootstrap_ip:
        raise ValueError("SSH bootstrap IP is not configured.")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=node.bootstrap_ip,
        port=node.ssh_port or 22,
        username="root",
        password=password,
        look_for_keys=False,
        allow_agent=False,
        timeout=8,
        banner_timeout=8,
        auth_timeout=8,
    )
    transport = client.get_transport()
    if transport is None:
        client.close()
        raise ConnectionError("SSH transport was not established.")
    return client, _fingerprint(transport.get_remote_server_key())


def _run(client: paramiko.SSHClient, command: str) -> tuple[int, str]:
    _stdin, stdout, stderr = client.exec_command(command, timeout=20)
    status = stdout.channel.recv_exit_status()
    output = (stdout.read() + stderr.read()).decode("utf-8", errors="replace")
    return status, output[-20000:]


def discover_node(node, password: str) -> SSHResult:
    endpoint = f"{node.bootstrap_ip or '<not configured>'}:{node.ssh_port or 22}"
    try:
        client, fingerprint = _connect(node, password)
        try:
            status, output = _run(client, DISCOVERY_COMMAND)
        finally:
            client.close()
        return SSHResult(node.hostname, endpoint, status == 0, output, fingerprint)
    except Exception as exc:  # Paramiko exposes several transport-specific exceptions.
        return SSHResult(node.hostname, endpoint, False, str(exc))


def run_read_only_script(node, password: str, script: str) -> SSHResult:
    """Stream a reviewed script to bash without creating a remote file."""
    endpoint = f"{node.bootstrap_ip or '<not configured>'}:{node.ssh_port or 22}"
    try:
        client, fingerprint = _connect(node, password)
        try:
            stdin, stdout, stderr = client.exec_command("bash -s --", timeout=30)
            stdin.write(script)
            stdin.channel.shutdown_write()
            status = stdout.channel.recv_exit_status()
            output = (stdout.read() + stderr.read()).decode("utf-8", errors="replace")[-20000:]
        finally:
            client.close()
        return SSHResult(node.hostname, endpoint, status == 0, output, fingerprint)
    except Exception as exc:
        return SSHResult(node.hostname, endpoint, False, str(exc))


def bootstrap_peer_keys(nodes, password: str) -> list[SSHResult]:
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
                results.append(SSHResult(node.hostname, endpoint, False, str(exc)))

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
    return results
