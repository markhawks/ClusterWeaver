"""Standalone read-only VMware status adapter, executed on cluster nodes."""
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path


def inspect_vmware(profile, deadline):
    mode = profile.get('mode')
    if mode not in {'vmware_soap', 'vmware_rest'}:
        raise ValueError('Unsupported VMware fence agent.')
    fields = {key: str(profile.get(key, '')) for key in
              ('controller_endpoint', 'profile_name', 'username', 'password')}
    if any(not value or any(c in value for c in '\r\n\x00') for value in fields.values()):
        raise ValueError('vCenter, VM name, userid and password are required and cannot contain newlines/NUL.')
    agent = 'fence_' + mode
    executable = shutil.which(agent) or next((str(p) for p in (Path('/usr/sbin') / agent, Path('/sbin') / agent, Path('/usr/bin') / agent) if p.is_file() and os.access(p, os.X_OK)), None)
    if not executable:
        raise ValueError(f'{agent} is missing on this cluster node. Install fence-agents-all and repeat the agent check.')
    remaining = min(20, deadline - time.monotonic())
    if remaining <= 0:
        raise ValueError('VMware verification timeout expired; status is unknown.')
    # Fixed read-only action; no credentials in command arguments or generated scripts.
    transport = profile.get('vmware_transport', 'https_secure')
    if transport == 'http':
        transport = 'https_insecure'
    if transport not in {'https_secure', 'https_insecure'}:
        raise ValueError('Unsupported VMware connection transport.')
    tls = ('ssl=1', 'ssl_insecure=1' if transport == 'https_insecure' else 'ssl_secure=1')
    payload = '\n'.join((
        'ipaddr=' + fields['controller_endpoint'], 'login=' + fields['username'],
        'passwd=' + fields['password'], 'port=' + fields['profile_name'],
        *tls, 'login_timeout=10', 'shell_timeout=10', 'action=status', '',
    ))
    try:
        result = subprocess.run([executable], input=payload, text=True, capture_output=True, timeout=remaining)
    except subprocess.TimeoutExpired:
        raise ValueError('vCenter status timed out after at most 20 seconds; status is unknown.') from None
    except OSError:
        raise ValueError(f'Unable to execute {agent} on the cluster node; check permissions, interpreter and package dependencies.') from None
    output = (result.stdout + '\n' + result.stderr).replace(fields['password'], '[redacted]').strip()
    if result.returncode or not re.search(r'\bStatus:\s*(ON|OFF)\b', output, re.I):
        raise ValueError('vCenter verification failed. Check the exact VM name/inventory path, credentials, the configured HTTP/HTTPS port and certificate trust on this cluster node.\n' + output)
    return f"PASS: {agent}; VM {fields['profile_name']} on {fields['controller_endpoint']}.\n{output}"


def remote_program():
    return Path(__file__).read_text(encoding='utf-8') + '''
import sys
profile = json.load(sys.stdin)
try:
    print(inspect_vmware(profile, time.monotonic() + min(20, profile.pop('verification_timeout', 20))))
except ValueError as exc:
    print('FAIL: ' + str(exc))
    raise SystemExit(1)
'''
