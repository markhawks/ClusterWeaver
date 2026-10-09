"""Service-owned per-project SSH keys, provisioning and key-only verification."""
import base64
import fcntl
import ipaddress
import os
from pathlib import Path
import shlex
import stat
from uuid import UUID

from concurrent.futures import ThreadPoolExecutor, wait
import time

import paramiko

from clusterweaver.core.services.ssh_credentials import SSHCredentials, redact_output
from clusterweaver.core.services.ssh_bootstrap import SSHResult, _connect, _run, _fingerprint


def _private_file(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise ValueError("SSH credential files must be regular service-owned files with mode 0600.")


class ProjectSSHKeys:
    def __init__(self, root, project_uuid):
        self.directory = Path(root) / str(UUID(str(project_uuid)))
        self.private = self.directory / 'id_rsa'
        self.pending = self.directory / 'id_rsa.pending'
        self.previous = self.directory / 'id_rsa.previous'
        self.known_hosts = self.directory / 'known_hosts'

    def prepare_directory(self):
        self.directory.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.mkdir(mode=0o700, exist_ok=True)
        for path in (self.directory.parent, self.directory):
            info = path.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
                raise ValueError("SSH key directories must be service-owned directories, not symlinks.")
            path.chmod(0o700)

    def key(self, path=None):
        path = path or self.private
        _private_file(path)
        try:
            return paramiko.RSAKey.from_private_key_file(str(path))
        except paramiko.SSHException as exc:
            raise ValueError("Project SSH private key is invalid or unreadable; restore its protected server backup.") from exc

    def available(self):
        return self.private.exists() or self.private.is_symlink()

    def status(self):
        result = {}
        for name, path in [('active', self.private), ('pending', self.pending), ('previous', self.previous)]:
            if path.exists() or path.is_symlink():
                try:
                    key = self.key(path)
                    result[name] = dict(fingerprint=_fingerprint(key), public_key=f'{key.get_name()} {key.get_base64()} clusterweaver:{self.directory.name}')
                except (OSError, ValueError, paramiko.SSHException):
                    result[name] = dict(error='Key unavailable: check owner, permissions or key file integrity.')
        return result

    def prepare(self, rotate=False):
        self.prepare_directory()
        # Serialize creation/activation between Gunicorn processes. No key is overwritten.
        with self.lock():
            if self.pending.exists():
                self.key(self.pending)
                return self.pending
            if self.available() and not rotate:
                self.key()
                return self.private
            if rotate and self.previous.exists():
                raise ValueError("Revoke the previous key on every node before starting another rotation.")
            key = paramiko.RSAKey.generate(3072)
            fd = os.open(self.pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'w') as stream:
                key.write_private_key(stream)
            return self.pending

    def lock(self):
        return _KeyLock(self.directory / '.lock')

    def activate(self, candidate):
        if candidate == self.private:
            return
        with self.lock():
            if not self.pending.exists():
                raise ValueError("Pending SSH key changed during installation; reload and verify again.")
            if self.available():
                os.replace(self.private, self.previous)
            os.replace(self.pending, self.private)

    def credentials(self, override='', default=''):
        # An explicitly entered password is a deliberate recovery request.
        if override:
            if self.available():
                return SSHCredentials(password=override, known_hosts=self.known_hosts)
            return override
        if self.available():
            return SSHCredentials(private_key=self.private, known_hosts=self.known_hosts)
        return default or None


class _KeyLock:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *args):
        fcntl.flock(self.fd, fcntl.LOCK_UN)
        os.close(self.fd)


def authorized_key_line(store, key_path, source_ip):
    address = str(ipaddress.ip_address(source_ip))
    key = store.key(key_path)
    return f'from="{address}",restrict {key.get_name()} {key.get_base64()} clusterweaver:{store.directory.name}'


def public_key_install_script(line):
    encoded = base64.b64encode((line + '\n').encode()).decode()
    return ("set -e\numask 077\ninstall -d -m 700 /root/.ssh\n"
        "test ! -L /root/.ssh/authorized_keys || { echo 'FAIL: authorized_keys is a symlink; review manually.'; exit 1; }\n"
        "touch /root/.ssh/authorized_keys\nchmod 600 /root/.ssh/authorized_keys\n"
        "exec 9>/root/.ssh/.clusterweaver-authorized-keys.lock\nflock -x 9\n"
        f"key=$(printf %s {shlex.quote(encoded)} | base64 -d)\n"
        "if ! grep -qxF \"$key\" /root/.ssh/authorized_keys; then\n"
        "  test ! -s /root/.ssh/authorized_keys || printf '\\n' >> /root/.ssh/authorized_keys\n"
        "  printf '%s\\n' \"$key\" >> /root/.ssh/authorized_keys\nfi\n"
        "command -v restorecon >/dev/null 2>&1 && restorecon -R /root/.ssh || true\n"
        "echo 'Public key installed/reused; existing authorized keys preserved.'\n")


def _verify(node, credentials):
    client, fingerprint = _connect(node, credentials)
    try:
        status, output = _run(client, "test \"$(id -u)\" = 0 && printf '%s\\n' 'PASS: key-only SSH authentication as root.'")
    finally:
        client.close()
    if status:
        raise ValueError("Key authentication did not establish a usable root command session.")
    return fingerprint, output


def install_project_key(store, nodes, passwords, source_ip, rotate=False):
    candidate = store.prepare(rotate)
    line = authorized_key_line(store, candidate, source_ip)
    target_credentials = SSHCredentials(private_key=candidate, known_hosts=store.known_hosts)
    def install_node(node, deadline):
        endpoint = f'{node.bootstrap_ip}:{node.ssh_port or 22}'
        secret = passwords.get(node.id, '')
        try:
            # Reuse an installed active key when bootstrapping or rotating. Otherwise
            # the current per-node password is required. Never try cached passwords.
            credentials = SSHCredentials(private_key=store.private, known_hosts=store.known_hosts) if store.available() and not secret else None
            if credentials is None and secret:
                credentials = SSHCredentials(password=secret, known_hosts=store.known_hosts, enroll_host=True)
            if credentials is None:
                # A previously successful partial installation may already accept the pending key.
                fingerprint, output = _verify(node, target_credentials)
            else:
                client, fingerprint = _connect(node, credentials)
                try:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Project key installation budget expired before changing authorized_keys.")
                    status, output = _run(client, 'bash -s <<\'CLUSTERWEAVER_PUBLIC_KEY\'\n' + public_key_install_script(line) + '\nCLUSTERWEAVER_PUBLIC_KEY')
                finally:
                    client.close()
                if status:
                    raise ValueError(output or 'Failed to install the project public key.')
                fingerprint, verified = _verify(node, target_credentials)
                output += '\n' + verified
            return SSHResult(node.hostname, endpoint, True, redact_output(output, secret), fingerprint)
        except Exception as exc:
            output = 'FAIL: ' + str(exc) + '\nProvide the current root password for this node if the project key has not been installed. Check sshd public-key policy and the permitted ClusterWeaver source IP.'
            return SSHResult(node.hostname, endpoint, False, redact_output(output, secret))
    results = _parallel_nodes(nodes, install_node)
    if results and all(result.ok for result in results):
        store.activate(candidate)
        for result in results:
            result.output += '\nProject key active. Future SSH operations can run without the root password.'
    elif candidate == store.pending:
        for result in results:
            result.output += "\nPending key is not active yet. Resume installation after correcting the failed nodes; the existing active key is unchanged."
    return results


def _parallel_nodes(nodes, operation):
    nodes = list(nodes)
    if not nodes:
        return []
    deadline = time.monotonic() + 90
    executor = ThreadPoolExecutor(max_workers=min(8, len(nodes)))
    def perform(node):
        if time.monotonic() >= deadline:
            return SSHResult(node.hostname, f'{node.bootstrap_ip}:{node.ssh_port or 22}', False, 'The 90-second project SSH operation budget expired.')
        return operation(node, deadline)
    futures = [executor.submit(perform, node) for node in nodes]
    try:
        done, _pending = wait(futures, timeout=max(0, deadline - time.monotonic()))
        results = []
        for node, future in zip(nodes, futures):
            if future in done:
                results.append(future.result())
            else:
                future.cancel()
                results.append(SSHResult(node.hostname, f'{node.bootstrap_ip}:{node.ssh_port or 22}', False,
                    'The 90-second SSH operation budget expired. A partial public-key update may have completed; resume installation or verification.'))
        return results
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def verify_project_key(store, nodes):
    credentials = SSHCredentials(private_key=store.private, known_hosts=store.known_hosts)
    def verify_node(node, deadline):
        endpoint = f'{node.bootstrap_ip}:{node.ssh_port or 22}'
        try:
            fingerprint, output = _verify(node, credentials)
            return SSHResult(node.hostname, endpoint, True, output, fingerprint)
        except Exception as exc:
            return SSHResult(node.hostname, endpoint, False, 'FAIL: key-only SSH verification: ' + str(exc))
    return _parallel_nodes(nodes, verify_node)


def revoke_previous_key(store, nodes):
    key = store.key(store.previous)
    # Delete only lines containing the exact old public key blob, preserving all other keys.
    blob = key.get_base64()
    command = ("set -e; exec 9>/root/.ssh/.clusterweaver-authorized-keys.lock; flock -x 9; "
        "test ! -L /root/.ssh/authorized_keys; "
        "tmp=$(mktemp /root/.ssh/authorized_keys.XXXXXX); "
        "trap 'rm -f \"$tmp\"' EXIT; "
        f"awk -v key={shlex.quote(blob)} '{{keep=1; for(i=1;i<=NF;i++) if($i==key) keep=0; if(keep) print}}' "
        "/root/.ssh/authorized_keys > \"$tmp\"; chmod 600 \"$tmp\"; "
        "cat \"$tmp\" > /root/.ssh/authorized_keys; echo 'Previous project key revoked.'")
    credentials = SSHCredentials(private_key=store.private, known_hosts=store.known_hosts)
    def revoke_node(node, deadline):
        endpoint = f'{node.bootstrap_ip}:{node.ssh_port or 22}'
        try:
            client, fingerprint = _connect(node, credentials)
            try:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Previous-key revocation budget expired before changing authorized_keys.")
                status, output = _run(client, command)
            finally:
                client.close()
            return SSHResult(node.hostname, endpoint, status == 0, output, fingerprint)
        except Exception as exc:
            return SSHResult(node.hostname, endpoint, False, 'FAIL: previous-key revocation: ' + str(exc))
    results = _parallel_nodes(nodes, revoke_node)
    if results and all(result.ok for result in results):
        with store.lock():
            store.previous.unlink(missing_ok=True)
    return results
