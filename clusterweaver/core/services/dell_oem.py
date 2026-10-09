"""Read-only Dell OpenManage Enterprise profile verification (stdlib only).

API references:
https://www.dell.com/support/manuals/en-uk/dell-openmanage-enterprise/ome_p_38_api_guide/profiles?guid=guid-044ccf90-224f-4efa-9d91-43c91178eb0d
https://docs.ansible.com/ansible/latest/collections/dellemc/openmanage/ome_profile_info_module.html
"""
import base64
import ipaddress
import json
import re
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener


class OEMCheckError(ValueError):
    pass


def validate_oem_endpoint(value):
    """Accept a host or IP only; HTTPS/443 is fixed for this initial Dell adapter."""
    if not value or len(value) > 253:
        raise ValueError("Enter an OEM IP address or hostname.")
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        pass
    if re.fullmatch(r"[0-9.]+", value):
        raise ValueError("Invalid OEM IP address.")
    if not all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) for label in value.split(".")):
        raise ValueError("Enter only an OEM hostname or IP, without a URL, path, port, or credentials.")
    return value


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class OEMClient:
    def __init__(self, endpoint, username, password, deadline, ca_file=None):
        validate_oem_endpoint(endpoint)
        if not username or ":" in username or not password:
            raise OEMCheckError("Enter a userid without ':' and an OEM password.")
        host = f"[{endpoint}]" if ":" in endpoint else endpoint
        self.base = f"https://{host}"
        self.deadline = deadline
        self.authorization = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
        try:
            context = ssl.create_default_context(cafile=ca_file)
        except (OSError, ssl.SSLError):
            raise OEMCheckError("Cannot load the configured OEM CA certificate file.") from None
        self.opener = build_opener(ProxyHandler({}), NoRedirect(), HTTPSHandler(context=context))

    def get(self, path):
        url = urljoin(self.base + "/", path)
        parts = urlsplit(url)
        if (parts.scheme, parts.netloc) != ("https", urlsplit(self.base).netloc) or not parts.path.startswith("/api/"):
            raise OEMCheckError("OEM returned an invalid API link; credentials were not forwarded.")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise OEMCheckError("OEM verification exceeded its 45-second request budget.")
        request = Request(url, headers={"Authorization": self.authorization, "Accept": "application/json"}, method="GET")
        try:
            with self.opener.open(request, timeout=min(8, remaining)) as response:
                payload = response.read(2 * 1024 * 1024 + 1)
            if len(payload) > 2 * 1024 * 1024:
                raise OEMCheckError("OEM response exceeds the 2 MiB limit.")
            document = json.loads(payload)
            if not isinstance(document, dict):
                raise OEMCheckError("OEM returned an invalid JSON object.")
            return document
        except HTTPError as exc:
            messages = {401: "OEM rejected the userid/password (HTTP 401).", 403: "OEM account cannot read this API (HTTP 403).", 404: "OEM API is unavailable on this appliance/version (HTTP 404)."}
            raise OEMCheckError(messages.get(exc.code, f"OEM returned HTTP {exc.code}; no changes made.")) from None
        except (URLError, ssl.SSLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, ssl.SSLCertVerificationError):
                raise OEMCheckError("OEM TLS certificate verification failed. Trust its CA on the ClusterWeaver server or configure CLUSTERWEAVER_OEM_CA_FILE.") from None
            raise OEMCheckError("Cannot connect to OEM over HTTPS/443: check name resolution, routing, firewall and request timeout.") from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise OEMCheckError("OEM returned invalid JSON instead of API data.") from None

    def collection(self, path):
        items = []
        seen = set()
        for _ in range(20):
            if path in seen:
                raise OEMCheckError("OEM returned a pagination loop.")
            seen.add(path)
            document = self.get(path)
            page = document.get("value")
            if not isinstance(page, list) or any(not isinstance(item, dict) for item in page):
                raise OEMCheckError("OEM returned an invalid API collection.")
            items.extend(page)
            path = document.get("@odata.nextLink")
            if not path:
                count = document.get("@odata.count")
                if isinstance(count, int) and count > len(items):
                    raise OEMCheckError("OEM returned an incomplete collection without a pagination link.")
                return items
            if not isinstance(path, str):
                raise OEMCheckError("OEM returned an invalid pagination link.")
        raise OEMCheckError("OEM inventory exceeds the 20-page verification limit.")


def find_named(items, field, expected, label):
    exact = [item for item in items if item.get(field) == expected]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise OEMCheckError(f"{label} '{expected}' is ambiguous: multiple OEM records have this name.")
    insensitive = [item for item in items if isinstance(item.get(field), str) and item[field].casefold() == expected.casefold()]
    if insensitive:
        names = ", ".join(item[field] for item in insensitive)
        raise OEMCheckError(f"{label} differs only in uppercase/lowercase: configured '{expected}', OEM '{names}'. Correct the configured name.")
    raise OEMCheckError(f"{label} '{expected}' was not found in OEM.")


def inspect_profile(client, hostname, profile_name):
    device = find_named(client.collection("/api/DeviceService/Devices"), "DeviceName", hostname, "Hostname")
    try:
        profiles = client.collection("/api/ProfileService/Profiles")
    except OEMCheckError as exc:
        if "HTTP 404" not in str(exc):
            raise
        profiles = client.collection("/api/TemplateService/Profiles")
    profile = find_named(profiles, "ProfileName", profile_name, "DELL profile name")
    # Dell API generations expose different profile target fields. Slot profiles
    # supply DeviceIdInSlot; older device profiles use AssociatedEntityId.
    target_id = profile.get("DeviceIdInSlot") or (profile.get("TargetId") if profile.get("TargetTypeId") == 1000 else None)
    if target_id is None and profile.get("AssociationType") == 1:
        target_id = profile.get("AssociatedEntityId")
    if not target_id:
        raise OEMCheckError(f"Profile '{profile_name}' has no verifiable device assignment; review its target type in OEM.")
    if not device.get("Id") or str(target_id) != str(device["Id"]):
        raise OEMCheckError(f"Profile '{profile_name}' targets device ID {target_id}, not '{hostname}' (device ID {device.get('Id')}).")
    state = profile.get("ProfileState", profile.get("Status"))
    if state is None:
        raise OEMCheckError(f"OEM returned no status for profile '{profile_name}'.")
    output = [
        "PASS: OEM HTTPS connection and authentication succeeded from the ClusterWeaver server.",
        f"PASS: hostname '{hostname}' and DELL profile '{profile_name}' match exactly.",
        f"PASS: profile is assigned to device ID {device['Id']}.",
        f"INFO: profile state={state}; last run status={profile.get('LastRunStatus', 'not reported')}.",
        f"INFO: device status={device.get('Status', 'not reported')}; power state={device.get('PowerState', 'not reported')}; OEM connection state={device.get('ConnectionState', 'not reported')}.",
        "PASS: definition and status lookup completed. Profile health and fencing capability are not certified by step 08a.",
    ]
    if device.get("ConnectionState") is False:
        raise OEMCheckError("OEM reports that the target device is disconnected.")
    return "\n".join(output)
