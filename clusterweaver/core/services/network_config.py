from __future__ import annotations

import shlex
import time
from dataclasses import dataclass
from types import SimpleNamespace

from clusterweaver.core.services.ssh_bootstrap import _connect, _run
from clusterweaver.core.validators import host_address


@dataclass(slots=True)
class NetworkConfigResult:
    hostname: str
    endpoint: str
    ok: bool
    output: str
    rollback_pending: bool = False


def _command(*arguments: str) -> str:
    return shlex.join(arguments)


def configure_node_network(node, password: str, rollback_seconds: int = 90) -> NetworkConfigResult:
    """Apply NetworkManager profiles with timed management rollback and reconnect verification."""
    required = {
        "management IP/subnet": node.management_ip,
        "management gateway": node.management_gateway,
        "primary interface": node.primary_interface,
    }
    missing = [name for name, value in required.items() if not value]
    endpoint = f"{node.bootstrap_ip or '<not configured>'}:{node.ssh_port or 22}"
    if missing:
        return NetworkConfigResult(node.hostname, endpoint, False, "Missing " + ", ".join(missing) + ".")

    log: list[str] = []
    client = None
    rollback_pending = False
    unit = f"clusterweaver-network-rollback-{node.id or 'node'}"
    profile = f"clusterweaver-management-{node.id or 'node'}"
    private_profile = f"clusterweaver-private-{node.id or 'node'}"
    candidate_profile = f"{profile}-candidate"
    private_change_blocked = False
    private_block_reason = ""
    try:
        client, _fingerprint = _connect(node, password)
        release_check = "source /etc/os-release && test \"${ID}\" = rhel && test \"${VERSION_ID}\" = 10.2"
        status, output = _run(client, release_check)
        if status != 0:
            return NetworkConfigResult(node.hostname, endpoint, False, "Remote node is not verified as RHEL 10.2.\n" + output)
        for interface in filter(None, [node.primary_interface, node.secondary_interface]):
            status, output = _run(client, _command("ip", "link", "show", "dev", interface))
            if status != 0:
                return NetworkConfigResult(node.hostname, endpoint, False, f"Interface {interface} was not found.\n{output}")

        management_ip_status, management_addresses = _run(
            client, _command("ip", "-4", "-o", "address", "show", "dev", node.primary_interface, "scope", "global")
        )
        _route_status, management_routes = _run(
            client, _command("ip", "-4", "route", "show", "default", "dev", node.primary_interface)
        )
        management_ip_matches = management_ip_status == 0 and node.management_ip in {
            line.split()[3] for line in management_addresses.splitlines() if len(line.split()) > 3
        }
        management_gateway_matches = any(
            "via" in (tokens := line.split()) and tokens[tokens.index("via") + 1] == node.management_gateway
            for line in management_routes.splitlines()
            if len(line.split()) > 2
        )
        management_matches = management_ip_matches and management_gateway_matches

        private_configured = bool(node.cluster_ip and node.secondary_interface)
        private_matches = True
        if private_configured:
            private_ip_status, private_addresses = _run(
                client, _command("ip", "-4", "-o", "address", "show", "dev", node.secondary_interface, "scope", "global")
            )
            private_ip_matches = private_ip_status == 0 and node.cluster_ip in {
                line.split()[3] for line in private_addresses.splitlines() if len(line.split()) > 3
            }
            _status, private_connection = _run(
                client, _command("nmcli", "-g", "GENERAL.CONNECTION", "device", "show", node.secondary_interface)
            )
            private_connection = private_connection.strip()
            never_default = ""
            if private_connection and private_connection != "--":
                _status, never_default = _run(
                    client, _command("nmcli", "-g", "ipv4.never-default", "connection", "show", private_connection)
                )
            private_matches = private_ip_matches and never_default.strip().lower() == "yes"

        if management_matches:
            log.append("PASS: management network configuration is already compliant; no changes required.")
        if private_configured and private_matches:
            log.append("PASS: cluster/private network configuration is already compliant; no changes required.")
        if management_matches and private_matches:
            return NetworkConfigResult(node.hostname, endpoint, True, "\n".join(log))

        if private_configured and not private_matches:
            pcs_installed, pcs_package = _run(client, "rpm -q pcs")
            if pcs_installed == 0:
                pcs_status, pcs_output = _run(client, "pcs status")
                normalized_status = pcs_output.lower()
                cluster_formed = any(marker in normalized_status for marker in (
                    "cluster name:", "cluster summary:", "nodes configured", "full list of resources",
                ))
                if cluster_formed:
                    private_change_blocked = True
                    private_block_reason = (
                        "Cluster/private network differs from the project configuration, but pcs reports an existing cluster. "
                        "Private network changes are blocked after cluster formation.\n--- pcs status ---\n" + pcs_output
                    )
                else:
                    log.append("pcs is installed, but pcs status did not report a formed cluster; private network changes are allowed.")
            else:
                log.append("pcs is not installed; private network changes are allowed.")

        if not management_matches:
            desired_ip = host_address(node.management_ip)
            duplicate_check = (
                "if command -v arping >/dev/null 2>&1; then "
                + _command("arping", "-D", "-c", "2", "-w", "3", "-I", node.primary_interface, desired_ip)
                + "; else exit 2; fi"
            )
            status, output = _run(client, duplicate_check)
            if status == 1:
                return NetworkConfigResult(node.hostname, endpoint, False, f"Duplicate response detected for desired management IP {desired_ip}; no changes were made.\n{output}")
            if status == 2:
                log.append("WARNING: arping is unavailable; duplicate-IP detection was skipped.")

            status, active_uuid = _run(client, _command("nmcli", "-g", "GENERAL.CON-UUID", "device", "show", node.primary_interface))
            active_uuid = active_uuid.strip()
            if status != 0 or not active_uuid or active_uuid == "--":
                return NetworkConfigResult(node.hostname, endpoint, False, "No active NetworkManager connection was found on the primary interface.")
            log.append(f"Active management profile UUID: {active_uuid}")
            _status, dns_output = _run(client, _command("nmcli", "-g", "IP4.DNS", "device", "show", node.primary_interface))
            dns_servers = ",".join(line.strip() for line in dns_output.splitlines() if line.strip())
            cleanup = (
                _command("nmcli", "connection", "delete", candidate_profile) + " >/dev/null 2>&1 || true; "
                + _command("systemctl", "stop", f"{unit}.timer", f"{unit}.service") + " >/dev/null 2>&1 || true; "
                + _command("systemctl", "reset-failed", f"{unit}.service") + " >/dev/null 2>&1 || true"
            )
            _run(client, cleanup)
            add_args = [
                "nmcli", "connection", "add", "type", "ethernet", "ifname", node.primary_interface,
                "con-name", candidate_profile, "connection.autoconnect", "yes", "connection.autoconnect-priority", "100",
                "ipv4.method", "manual", "ipv4.addresses", node.management_ip, "ipv4.gateway", node.management_gateway,
            ]
            if dns_servers:
                add_args.extend(["ipv4.dns", dns_servers])
            status, output = _run(client, _command(*add_args))
            if status != 0:
                return NetworkConfigResult(node.hostname, endpoint, False, "Could not create the candidate management profile.\n" + output)

            rollback_command = _command("/usr/bin/nmcli", "connection", "up", "uuid", active_uuid, "ifname", node.primary_interface)
            schedule = _command("systemd-run", f"--unit={unit}", f"--on-active={rollback_seconds}s", "/bin/sh", "-c", rollback_command)
            status, output = _run(client, schedule)
            if status != 0:
                return NetworkConfigResult(node.hostname, endpoint, False, "Could not schedule the safety rollback; no network change was activated.\n" + output)
            rollback_pending = True
            log.append(f"Safety rollback scheduled in {rollback_seconds} seconds.")
            activation_log = f"/run/clusterweaver-network-{node.id or 'node'}.log"
            activate = "nohup " + _command("nmcli", "connection", "up", candidate_profile, "ifname", node.primary_interface) + " >" + shlex.quote(activation_log) + " 2>&1 </dev/null &"
            try:
                _run(client, activate)
            except Exception:
                pass
            finally:
                client.close()
                client = None

            new_ip = host_address(node.management_ip)
            new_node = SimpleNamespace(bootstrap_ip=new_ip, ssh_port=node.ssh_port)
            deadline = time.monotonic() + min(rollback_seconds - 15, 60)
            last_error = ""
            while time.monotonic() < deadline:
                try:
                    client, _fingerprint = _connect(new_node, password)
                    break
                except Exception as exc:
                    last_error = str(exc)
                    time.sleep(2)
            if client is None:
                log.append(f"Could not reconnect to {new_ip}; automatic rollback remains armed. Last SSH error: {last_error}")
                return NetworkConfigResult(node.hostname, endpoint, False, "\n".join(log), rollback_pending=True)
            cancel = (
                _command("systemctl", "stop", f"{unit}.timer") + " && ! "
                + _command("systemctl", "is-active", "--quiet", f"{unit}.timer") + " && ("
                + _command("systemctl", "reset-failed", f"{unit}.service") + " >/dev/null 2>&1 || true) && "
                + _command("nmcli", "connection", "modify", "uuid", active_uuid, "connection.autoconnect", "no")
            )
            status, output = _run(client, cancel)
            if status != 0:
                log.append("WARNING: reconnected, but rollback cancellation could not be confirmed.\n" + output)
                return NetworkConfigResult(node.hostname, f"{new_ip}:{node.ssh_port or 22}", False, "\n".join(log), rollback_pending=True)
            rollback_pending = False
            log.append(f"Reconnected to {new_ip}; safety rollback cancelled.")

            archive_old_profile = f"""
set -e
backup_root=/root/clusterweaver-backups/network
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_dir="${{backup_root}}/${{timestamp}}-{shlex.quote(node.hostname)}"
profile_file=$(grep -rl --include='*.nmconnection' '^uuid={active_uuid}$' /etc/NetworkManager/system-connections 2>/dev/null | head -n 1)
if [[ -z "${{profile_file}}" ]]; then
  echo 'Old NetworkManager profile file was not found; profile retained.'
  exit 3
fi
install -d -m 700 "${{backup_dir}}"
cp -a -- "${{profile_file}}" "${{backup_dir}}/"
printf 'hostname=%s\\nconnection_uuid=%s\\nsource_file=%s\\nbackup_time_utc=%s\\n' {shlex.quote(node.hostname)} {shlex.quote(active_uuid)} "${{profile_file}}" "${{timestamp}}" > "${{backup_dir}}/manifest.txt"
chmod 600 "${{backup_dir}}/manifest.txt"
nmcli connection delete uuid {shlex.quote(active_uuid)}
echo "Old profile archived in ${{backup_dir}} and removed from NetworkManager."
"""
            status, output = _run(client, archive_old_profile)
            if status == 0:
                log.append(output.strip())
            else:
                log.append("WARNING: the new management profile is active, but the old profile was retained because archival did not complete.\n" + output)
            status, output = _run(client, _command("nmcli", "connection", "modify", candidate_profile, "connection.id", profile))
            if status != 0:
                log.append("WARNING: the candidate management profile could not be renamed.\n" + output)

        if private_change_blocked:
            log.append(private_block_reason)
            return NetworkConfigResult(
                node.hostname,
                f"{host_address(node.management_ip)}:{node.ssh_port or 22}",
                False,
                "\n".join(log),
            )

        if private_configured and not private_matches:
            delete_private = _command("nmcli", "connection", "delete", private_profile) + " >/dev/null 2>&1 || true"
            _run(client, delete_private)
            private_args = [
                "nmcli", "connection", "add", "type", "ethernet", "ifname", node.secondary_interface,
                "con-name", private_profile, "connection.autoconnect", "yes", "connection.autoconnect-priority", "100",
                "ipv4.method", "manual", "ipv4.addresses", node.cluster_ip,
            ]
            enforce_private_routing = _command("nmcli", "connection", "modify", private_profile, "ipv4.never-default", "yes")
            activate_private = _command("nmcli", "connection", "up", private_profile, "ifname", node.secondary_interface)
            status, output = _run(client, _command(*private_args) + " && " + enforce_private_routing + " && " + activate_private)
            if status != 0:
                log.append("Management succeeded, but cluster/private configuration failed.\n" + output)
                return NetworkConfigResult(node.hostname, f"{host_address(node.management_ip)}:{node.ssh_port or 22}", False, "\n".join(log))
            log.append(output.strip())

        status, output = _run(client, _command("ip", "-brief", "-4", "address") + "; " + _command("ip", "-4", "route"))
        log.append("Final network state:\n" + output)
        return NetworkConfigResult(node.hostname, f"{host_address(node.management_ip)}:{node.ssh_port or 22}", status == 0, "\n".join(log))
    except Exception as exc:
        log.append(str(exc))
        return NetworkConfigResult(node.hostname, endpoint, False, "\n".join(log), rollback_pending=rollback_pending)
    finally:
        if client is not None:
            client.close()
