"""Step 08a verification; secrets are redacted from persisted execution results."""
import time
from pathlib import Path
import json

from clusterweaver.core.services.dell_oem import OEMClient, OEMCheckError, inspect_profile, validate_oem_endpoint
from clusterweaver.core.services.ssh_bootstrap import SSHResult


def verify_oem_profiles(endpoint, profiles, ca_file=None):
    deadline = time.monotonic() + 45
    results = []
    for profile in profiles:
        try:
            client = OEMClient(endpoint, profile["username"], profile["password"], deadline, ca_file)
            output = inspect_profile(client, profile["hostname"], profile["profile_name"])
            ok = True
        except (OEMCheckError, ValueError) as exc:
            output = "FAIL: " + str(exc)
            ok = False
        # Never store a password even if the remote appliance echoed it in a name.
        for item in profiles:
            if item.get("password"):
                output = output.replace(item["password"], "[redacted]")
        results.append(SSHResult(profile["hostname"], endpoint, ok, output))
    return results


def generate_oem_verification_script(endpoint, profiles):
    """Standalone Python script using the same read-only adapter, with password prompts."""
    source = Path(__file__).with_name("dell_oem.py").read_text(encoding="utf-8")
    definitions = [{key: item[key] for key in ("hostname", "profile_name", "username")} for item in profiles]
    return "#!/usr/bin/env python3\n" + source + "\n" + (
        "\n# Step 08a: only HTTPS GET requests; execute from the ClusterWeaver server.\n"
        "import getpass\nimport os\n"
        f"ENDPOINT = {endpoint!r}\n"
        f"PROFILES = json.loads({json.dumps(definitions)!r})\n"
        "for profile in PROFILES:\n"
        "    profile['password'] = getpass.getpass('OEM password for ' + profile['hostname'] + ': ')\n"
        "deadline = time.monotonic() + 45\n"
        "failed = False\n"
        "for profile in PROFILES:\n"
        "    password = profile['password']\n"
        "    try:\n"
        "        client = OEMClient(ENDPOINT, profile['username'], password, deadline, os.environ.get('CLUSTERWEAVER_OEM_CA_FILE') or None)\n"
        "        print(inspect_profile(client, profile['hostname'], profile['profile_name']).replace(password, '[redacted]'))\n"
        "    except (OEMCheckError, ValueError) as exc:\n"
        "        print(('FAIL: ' + str(exc)).replace(password, '[redacted]') if password else 'FAIL: OEM password is required.')\n"
        "        failed = True\n"
        "raise SystemExit(1 if failed else 0)\n"
    )


def verify_ipmi_profiles(profiles):
    from clusterweaver.core.services.dell_ipmi import inspect_ipmi
    deadline = time.monotonic() + 45
    results = []
    for profile in profiles:
        try:
            output, ok = inspect_ipmi(profile, deadline), True
        except ValueError as exc:
            output, ok = 'FAIL: ' + str(exc), False
        for item in profiles:
            if item.get('password'):
                output = output.replace(item['password'], '[redacted]')
        results.append(SSHResult(profile['hostname'], profile['controller_endpoint'], ok, output))
    return results


def generate_ipmi_verification_script(profiles):
    source = Path(__file__).with_name('dell_ipmi.py').read_text(encoding='utf-8')
    definitions = [{key: item[key] for key in ('hostname', 'controller_endpoint', 'resource_name', 'username')} for item in profiles]
    return '#!/usr/bin/env python3\n# Run on a cluster node; the web check connects to each node over SSH.\n' + source + '\nimport getpass\nimport json\n' + (
        f'PROFILES = json.loads({json.dumps(definitions)!r})\n'
        "for profile in PROFILES:\n"
        "    profile['password'] = getpass.getpass('iDRAC password for ' + profile['hostname'] + ': ')\n"
        "deadline = time.monotonic() + 45\nfailed = False\n"
        "for profile in PROFILES:\n"
        "    try:\n        output = inspect_ipmi(profile, deadline)\n"
        "    except ValueError as exc:\n        output = 'FAIL: ' + str(exc)\n        failed = True\n"
        "    for item in PROFILES:\n"
        "        output = output.replace(item['password'], '[redacted]') if item['password'] else output\n"
        "    print(output)\n"
        "raise SystemExit(1 if failed else 0)\n"
    )


def remote_ipmi_program():
    """Public program; credentials arrive only on encrypted SSH stdin."""
    return Path(__file__).with_name('dell_ipmi.py').read_text(encoding='utf-8') + '''
import json
import sys
profile = json.load(sys.stdin)
try:
    print(inspect_ipmi(profile, time.monotonic() + min(20, profile.pop('verification_timeout', 20))))
except ValueError as exc:
    print('FAIL: ' + str(exc))
    raise SystemExit(1)
'''


def verify_ipmi_profiles_on_nodes(nodes, credentials, profiles):
    """Each node checks its associated controller; no agent runs on the web host."""
    from concurrent.futures import ThreadPoolExecutor, wait
    import shlex
    from clusterweaver.core.services.ssh_bootstrap import _connect, _collect_channel
    from clusterweaver.core.services.ssh_credentials import redact_output
    nodes_by_name = {node.hostname: node for node in nodes}
    deadline = time.monotonic() + 45
    command = 'python3 -c ' + shlex.quote(remote_ipmi_program())

    def check(profile):
        fingerprint = ''
        node = nodes_by_name.get(profile['hostname'])
        try:
            if node is None:
                raise ValueError('No matching cluster node for this iDRAC profile.')
            if not credentials:
                raise ValueError('Configure and verify the project SSH key before checking iDRAC status from cluster nodes.')
            if time.monotonic() >= deadline:
                raise TimeoutError('The 45-second verification budget expired.')
            client, fingerprint = _connect(node, credentials)
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('The 45-second verification budget expired.')
                limit = min(25, remaining)
                stdin, stdout, _stderr = client.exec_command(command, timeout=limit)
                payload = dict(profile, verification_timeout=min(20, remaining))
                stdin.write(json.dumps(payload))
                stdin.channel.shutdown_write()
                status, output = _collect_channel(stdout.channel, timeout=limit)
            finally:
                client.close()
            output = f'Verification executed on cluster node {node.hostname} via SSH ({node.bootstrap_ip}).\n' + output
            return SSHResult(profile['hostname'], profile['controller_endpoint'], status == 0, output, fingerprint)
        except Exception as exc:
            return SSHResult(profile['hostname'], profile['controller_endpoint'], False, 'FAIL: IPMI verification from the cluster node: ' + str(exc), fingerprint)

    if not profiles:
        return []
    executor = ThreadPoolExecutor(max_workers=min(8, len(profiles)))
    futures = [executor.submit(check, profile) for profile in profiles]
    try:
        done, _ = wait(futures, timeout=max(0, deadline - time.monotonic()))
        results = []
        for profile, future in zip(profiles, futures):
            if future in done:
                result = future.result()
            else:
                future.cancel()
                result = SSHResult(profile['hostname'], profile['controller_endpoint'], False, 'FAIL: cluster-node IPMI verification exceeded the 45-second budget; status is unknown.')
            result.output = redact_output(result.output, credentials)
            for item in profiles:
                if item.get('password'):
                    result.output = result.output.replace(item['password'], '[redacted]')
            results.append(result)
        return results
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
