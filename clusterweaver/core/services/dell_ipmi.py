"""Read-only IPMI status via fence_ipmilan; credentials travel on stdin."""
import re
import shutil
import subprocess
import time


def validate_ipmi_definition(endpoint, resource):
    # Shared host/IP syntax; this module is also embedded in standalone scripts.
    import ipaddress
    try:
        ipaddress.ip_address(endpoint)
    except ValueError:
        if not endpoint or len(endpoint) > 253 or not all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label) and len(label) <= 63 for label in endpoint.split('.')):
            raise ValueError("Enter a valid iDRAC IP address or hostname without a URL, port or path.")
        if re.fullmatch(r"[0-9.]+", endpoint):
            raise ValueError("Invalid iDRAC IP address.")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,159}", resource or ""):
        raise ValueError("STONITH resource name must start with a letter or underscore and contain only letters, digits, underscore, dot or hyphen.")


def inspect_ipmi(profile, deadline):
    validate_ipmi_definition(profile['controller_endpoint'], profile['resource_name'])
    for key in ('username', 'password'):
        if not profile.get(key) or any(c in profile[key] for c in '\r\n\x00'):
            raise ValueError("Userid and password are required and cannot contain newlines or NUL characters.")
    agent = shutil.which('fence_ipmilan')
    if not agent:
        raise ValueError("fence_ipmilan is missing on the ClusterWeaver server. Install the RHEL fence-agents-ipmilan package before verification.")
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ValueError("The 45-second verification budget expired.")
    parameters = dict(ipaddr=profile['controller_endpoint'], login=profile['username'], passwd=profile['password'], lanplus='1', action='status', method='onoff')
    try:
        result = subprocess.run([agent], input=''.join(f'{key}={value}\n' for key, value in parameters.items()), capture_output=True, text=True, timeout=min(20, remaining))
    except subprocess.TimeoutExpired as exc:
        raise ValueError("IPMI status timed out (20 seconds per node, 45 seconds total). Check iDRAC connectivity and credentials.") from exc
    except OSError as exc:
        raise ValueError("Unable to execute fence_ipmilan on the ClusterWeaver server.") from exc
    output = (result.stdout + '\n' + result.stderr).strip()
    if result.returncode != 0:
        raise ValueError(f"fence_ipmilan status failed (exit {result.returncode}): {output}")
    if not re.search(r'(?im)^\s*Status:\s*(ON|OFF)\s*$', result.stdout):
        raise ValueError("fence_ipmilan returned no recognizable ON/OFF status: " + output)
    return f"PASS: {profile['hostname']} · {profile['controller_endpoint']} · resource {profile['resource_name']}\n{output}\nRead-only status; controller-to-host association and actual fencing have not been tested."
