"""Step 08a orchestration; OEM passwords are never persisted."""
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
    return '#!/usr/bin/env python3\n' + source + '\nimport getpass\nimport json\n' + (
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
