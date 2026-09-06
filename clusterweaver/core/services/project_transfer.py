from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import re
import tarfile

import yaml

from clusterweaver.core.serializers.yaml_project import project_to_yaml
from clusterweaver.core.validators import validate_ip_address, validate_ipv4_cidr, validate_rhel_release
from clusterweaver.version import __version__


FORMAT_NAME = "clusterweaver-project"
FORMAT_VERSION = 1
MAX_ARCHIVE_SIZE = 8 * 1024 * 1024
MAX_MEMBER_SIZE = 2 * 1024 * 1024
MAX_TOTAL_SIZE = 8 * 1024 * 1024
ALLOWED_MEMBERS = {
    "manifest.yaml", "project.yaml", "CHECKSUMS.sha256",
    "scripts/00-ssh-discovery.sh", "scripts/00-peer-trust.sh", "scripts/00-network-configuration.sh",
    "scripts/01-prechecks.sh", "scripts/02-network-check.sh", "scripts/03-hosts-update.sh",
    "scripts/04-network-connectivity.sh",
}


class ProjectTransferError(ValueError):
    pass


def _yaml_bytes(value: dict) -> bytes:
    return yaml.safe_dump(value, sort_keys=False, allow_unicode=True).encode("utf-8")


def _add_bytes(archive: tarfile.TarFile, name: str, content: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(content)
    info.mode = 0o644
    info.mtime = 0
    archive.addfile(info, BytesIO(content))


def build_project_archive(project, scripts: dict[str, str]) -> BytesIO:
    files = {"project.yaml": project_to_yaml(project).encode("utf-8")}
    files.update({f"scripts/{name}": content.encode("utf-8") for name, content in scripts.items()})
    manifest = {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "clusterweaver_version": __version__,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source_project_uuid": str(project.uuid),
        "project_name": project.name,
        "security": {
            "contains_credentials": False,
            "contains_ssh_keys": False,
            "contains_execution_results": False,
        },
    }
    files["manifest.yaml"] = _yaml_bytes(manifest)
    checksums = "".join(f"{sha256(content).hexdigest()}  {name}\n" for name, content in sorted(files.items()))
    files["CHECKSUMS.sha256"] = checksums.encode("ascii")
    output = BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz", format=tarfile.PAX_FORMAT) as archive:
        for name, content in sorted(files.items()):
            _add_bytes(archive, name, content)
    output.seek(0)
    return output


def _text(value, field: str, *, required: bool = False, maximum: int = 5000) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ProjectTransferError(f"Invalid {field} value.")
    value = value.strip()
    if required and not value:
        raise ProjectTransferError(f"Missing required {field} value.")
    if len(value) > maximum:
        raise ProjectTransferError(f"{field} exceeds the maximum length of {maximum} characters.")
    return value


def _validate_project_document(document) -> dict:
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ProjectTransferError("Unsupported project.yaml schema version.")
    project = document.get("project")
    nodes = document.get("nodes")
    if not isinstance(project, dict) or not isinstance(nodes, list) or len(nodes) > 64:
        raise ProjectTransferError("Invalid project or node structure.")
    os_data = project.get("os")
    if not isinstance(os_data, dict) or os_data.get("distribution") != "rhel":
        raise ProjectTransferError("Only RHEL projects can be imported.")
    try:
        major = int(os_data.get("major"))
        minor = _text(os_data.get("minor"), "RHEL minor version", required=True, maximum=20)
        validate_rhel_release(major, minor)
        node_count = int(project.get("node_count"))
    except (TypeError, ValueError) as exc:
        raise ProjectTransferError(str(exc)) from exc
    if not 1 <= node_count <= 64 or len(nodes) > node_count:
        raise ProjectTransferError("Invalid expected node count.")
    platform_type = _text(project.get("platform_type"), "platform", required=True, maximum=20)
    hypervisor = _text(project.get("hypervisor"), "hypervisor", maximum=20)
    if platform_type not in {"physical", "virtual"}:
        raise ProjectTransferError("Unsupported platform type.")
    if platform_type == "virtual" and hypervisor not in {"vmware", "kvm", "proxmox"}:
        raise ProjectTransferError("Unsupported or missing hypervisor.")
    if platform_type == "physical":
        hypervisor = ""
    normalized_nodes = []
    seen_hostnames: set[str] = set()
    seen_ips: set[str] = set()
    for raw in nodes:
        if not isinstance(raw, dict):
            raise ProjectTransferError("Invalid node structure.")
        hostname = _text(raw.get("hostname"), "hostname", required=True, maximum=30)
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,28}[A-Za-z0-9])?", hostname):
            raise ProjectTransferError(f"Invalid hostname: {hostname}.")
        if hostname.casefold() in seen_hostnames:
            raise ProjectTransferError(f"Duplicate hostname: {hostname}.")
        seen_hostnames.add(hostname.casefold())
        node = {
            "hostname": hostname,
            "nodename": _text(raw.get("nodename"), "node name", required=True, maximum=253),
            "fqdn": _text(raw.get("fqdn"), "FQDN", maximum=253),
            "site": _text(raw.get("site"), "site", maximum=120),
            "management_ip": _text(raw.get("management_ip"), "management IP", required=True, maximum=45),
            "management_gateway": _text(raw.get("management_gateway"), "management gateway", required=True, maximum=45),
            "cluster_ip": _text(raw.get("cluster_ip"), "cluster IP", maximum=45),
            "cluster_gateway": _text(raw.get("cluster_gateway"), "cluster gateway", maximum=45),
            "primary_interface": _text(raw.get("primary_interface"), "primary interface", required=True, maximum=64),
            "secondary_interface": _text(raw.get("secondary_interface"), "secondary interface", maximum=64),
            "bootstrap_ip": _text(raw.get("bootstrap_ip"), "bootstrap IP", maximum=45),
        }
        try:
            management = validate_ipv4_cidr(node["management_ip"])
            validate_ip_address(node["management_gateway"])
            if node["cluster_ip"]:
                cluster = validate_ipv4_cidr(node["cluster_ip"])
            else:
                cluster = None
            validate_ip_address(node["cluster_gateway"])
            validate_ip_address(node["bootstrap_ip"])
            port = int(raw.get("ssh_port", 22))
        except (TypeError, ValueError) as exc:
            raise ProjectTransferError(str(exc)) from exc
        if not 1 <= port <= 65535:
            raise ProjectTransferError("SSH port must be between 1 and 65535.")
        from ipaddress import ip_address
        if ip_address(node["management_gateway"]) not in management.network:
            raise ProjectTransferError(f"Management gateway is outside the subnet for {hostname}.")
        if node["cluster_gateway"] and (cluster is None or ip_address(node["cluster_gateway"]) not in cluster.network):
            raise ProjectTransferError(f"Cluster gateway is outside the subnet for {hostname}.")
        addresses = [str(management.ip)] + ([str(cluster.ip)] if cluster else [])
        if seen_ips.intersection(addresses):
            raise ProjectTransferError(f"Duplicate IP address in node {hostname}.")
        seen_ips.update(addresses)
        node["ssh_port"] = port
        normalized_nodes.append(node)
    return {
        "project": {
            "name": _text(project.get("name"), "project name", required=True, maximum=160),
            "customer": _text(project.get("customer"), "customer", required=True, maximum=160),
            "description": _text(project.get("description"), "description", maximum=5000),
            "rhel_major": major, "rhel_minor": minor, "platform_type": platform_type,
            "hypervisor": hypervisor, "node_count": node_count,
        },
        "nodes": normalized_nodes,
    }


def read_project_archive(upload) -> dict:
    payload = upload.read(MAX_ARCHIVE_SIZE + 1)
    if not payload or len(payload) > MAX_ARCHIVE_SIZE:
        raise ProjectTransferError("The .cwp archive is empty or exceeds 8 MiB.")
    try:
        with tarfile.open(fileobj=BytesIO(payload), mode="r|gz") as archive:
            files: dict[str, bytes] = {}
            total_size = 0
            for member in archive:
                if member.name in files or member.name not in ALLOWED_MEMBERS:
                    raise ProjectTransferError("The archive contains duplicate or unsupported files.")
                if not member.isfile() or member.size > MAX_MEMBER_SIZE:
                    raise ProjectTransferError("The archive contains an invalid or oversized member.")
                total_size += member.size
                if total_size > MAX_TOTAL_SIZE:
                    raise ProjectTransferError("The uncompressed archive exceeds 8 MiB.")
                source = archive.extractfile(member)
                if source is None:
                    raise ProjectTransferError("The archive contains an unreadable member.")
                files[member.name] = source.read(member.size + 1)
                if len(files[member.name]) != member.size:
                    raise ProjectTransferError("The archive contains a truncated member.")
            if not {"manifest.yaml", "project.yaml", "CHECKSUMS.sha256"}.issubset(files):
                raise ProjectTransferError("The archive is missing required files.")
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise ProjectTransferError("The uploaded file is not a valid .cwp archive.") from exc
    try:
        manifest = yaml.safe_load(files["manifest.yaml"].decode("utf-8"))
        project_document = yaml.safe_load(files["project.yaml"].decode("utf-8"))
        checksum_lines = files["CHECKSUMS.sha256"].decode("ascii").splitlines()
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ProjectTransferError("The archive contains invalid YAML or text data.") from exc
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT_NAME or manifest.get("format_version") != FORMAT_VERSION:
        raise ProjectTransferError("Unsupported ClusterWeaver project archive version.")
    expected = {}
    for line in checksum_lines:
        parts = line.split("  ", 1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]) or parts[1] in expected:
            raise ProjectTransferError("Invalid checksum manifest.")
        expected[parts[1]] = parts[0]
    protected = set(files) - {"CHECKSUMS.sha256"}
    if set(expected) != protected or any(sha256(files[name]).hexdigest() != digest for name, digest in expected.items()):
        raise ProjectTransferError("Archive checksum verification failed.")
    return _validate_project_document(project_document)
