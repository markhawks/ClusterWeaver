"""Read-only cluster-node fence-agent inventory over the existing SSH transport."""
from concurrent.futures import ThreadPoolExecutor, wait
import shlex
import time

from clusterweaver.core.services.ssh_bootstrap import SSHResult, _connect, _collect_channel
from clusterweaver.core.services.ssh_credentials import redact_output

INSTALL_ALL_COMMAND = "dnf install fence-agents-all"


def generate_agent_check_script(mode):
    if mode not in {"oem", "ipmi"}:
        raise ValueError("Unsupported STONITH mode.")
    required = "fence_ipmilan" if mode == "ipmi" else ""
    return """#!/usr/bin/env bash
set -uo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
export LC_ALL=C
""" + f"required={shlex.quote(required)}\n" + r'''
echo 'Installed fence-agent RPM packages:'
rpm -qa 'fence-agents*' | sort
if rpm -q fence-agents-all >/dev/null 2>&1; then
    echo 'fence-agents-all: installed'
else
    echo 'fence-agents-all: not installed (individual agent packages may be sufficient)'
fi
echo 'Available fence_* executables:'
mapfile -t agents < <(compgen -c | sort -u | while IFS= read -r name; do
    case "$name" in fence_*) path=$(command -v "$name"); test -f "$path" && test -x "$path" && printf '%s\n' "$name" ;; esac
done)
printf '%s\n' "${agents[@]}"
if [ -n "$required" ]; then
    if ! command -v "$required" >/dev/null 2>&1; then
        echo "FAIL: required agent $required is missing on this cluster node."
        echo 'To install all available RHEL fence agents on this node as root:'
        echo 'dnf install fence-agents-all'
        echo 'Requires the RHEL High Availability repository supplied by Satellite/subscription.'
        exit 1
    fi
    echo "Required agent: $required ($(command -v "$required"))"
    if ! command -v timeout >/dev/null 2>&1; then
        echo 'FAIL: timeout is missing; unable to bound the agent metadata check.'
        exit 1
    fi
    metadata=$(timeout 10s "$required" --action=metadata 2>&1)
    status=$?
    if [ "$status" -ne 0 ] || [[ "$metadata" != *'<resource-agent'* ]]; then
        echo "FAIL: $required is installed but metadata cannot be read (exit $status). Check its dependencies/package installation."
        printf '%s\n' "$metadata"
        echo 'If the agent package is missing, install all agents: dnf install fence-agents-all'
        exit 1
    fi
    echo "PASS: $required is installed and its metadata is readable (no controller connection or power action)."
elif [ "${#agents[@]}" -eq 0 ]; then
    echo 'FAIL: no fence_* executable is available on this cluster node.'
    echo 'To install all available RHEL fence agents on this node as root:'
    echo 'dnf install fence-agents-all'
    echo 'Requires the RHEL High Availability repository supplied by Satellite/subscription.'
    exit 1
else
    echo 'PASS: fence-agent inventory collected. OEM mode does not yet select a Pacemaker fencing agent; this is not an agent compatibility test.'
fi
'''


def _check_node(node, password, script, deadline):
    endpoint = f"{node.bootstrap_ip or '<not configured>'}:{node.ssh_port or 22}"
    try:
        if time.monotonic() >= deadline:
            raise TimeoutError("The 45-second agent verification budget expired.")
        client, fingerprint = _connect(node, password)
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("The 45-second agent verification budget expired.")
            stdin, stdout, _stderr = client.exec_command("bash -s --", timeout=min(20, remaining))
            stdin.write(script)
            stdin.channel.shutdown_write()
            status, output = _collect_channel(stdout.channel, timeout=min(20, remaining))
        finally:
            client.close()
        return SSHResult(node.hostname, endpoint, status == 0, output, fingerprint)
    except Exception as exc:
        return SSHResult(node.hostname, endpoint, False, "Agent inventory could not be completed via SSH: " + str(exc))


def check_cluster_agents(nodes, password, mode):
    nodes = list(nodes)
    if not nodes:
        return []
    script = generate_agent_check_script(mode)
    deadline = time.monotonic() + 45
    executor = ThreadPoolExecutor(max_workers=min(8, len(nodes)))
    futures = [executor.submit(_check_node, node, password, script, deadline) for node in nodes]
    try:
        done, _pending = wait(futures, timeout=max(0, deadline - time.monotonic()))
        results = []
        for node, future in zip(nodes, futures):
            if future in done:
                result = future.result()
            else:
                future.cancel()
                result = SSHResult(node.hostname, f"{node.bootstrap_ip}:{node.ssh_port or 22}", False,
                    "Agent inventory incomplete: the 45-second verification budget expired. Retry the check; installation status is unknown.")
            result.output = redact_output(result.output, password)
            results.append(result)
        return results
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
