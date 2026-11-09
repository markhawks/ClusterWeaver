from ipaddress import IPv4Interface, ip_address, ip_interface


SUPPORTED_RHEL_MAJORS = frozenset({7, 9, 10})
SUPPORTED_RHEL_MINORS = {
    7: tuple(str(value) for value in range(10)),
    9: tuple(str(value) for value in range(9)),
    10: tuple(str(value) for value in range(3)),
}


def validate_rhel_version(major: int) -> None:
    if major == 8:
        raise ValueError("RHEL 8 is not currently supported by ClusterWeaver.")
    if major not in SUPPORTED_RHEL_MAJORS:
        raise ValueError(f"RHEL {major} is not supported by ClusterWeaver.")


def validate_rhel_release(major: int, minor: str) -> None:
    validate_rhel_version(major)
    normalized_minor = str(minor).strip()
    if normalized_minor not in SUPPORTED_RHEL_MINORS[major]:
        raise ValueError(f"RHEL {major}.{normalized_minor} is not supported by ClusterWeaver.")


def validate_ip_address(value: str) -> None:
    if not value:
        return
    try:
        ip_address(value)
    except ValueError as exc:
        raise ValueError(f"Invalid IP address: {value}") from exc


def validate_ipv4_cidr(value: str) -> IPv4Interface:
    if not value or "/" not in value:
        raise ValueError("Enter an IPv4 address with subnet prefix, for example 192.168.27.24/24.")
    try:
        parsed = ip_interface(value)
    except ValueError as exc:
        raise ValueError(f"Invalid IPv4 address or subnet prefix: {value}") from exc
    if not isinstance(parsed, IPv4Interface):
        raise ValueError("Only IPv4 addresses are supported here.")
    return parsed


def host_address(value: str) -> str:
    """Return the address portion of an IP or CIDR value."""
    return str(ip_interface(value).ip) if value else ""


def validate_gateway(address: str, gateway: str, role: str = 'Management') -> None:
    """Validate inventory gateways without making assumptions about router reachability."""
    interface = validate_ipv4_cidr(address)
    router = ip_address(gateway)
    network = interface.network
    if router.version != 4:
        raise ValueError(f'{role} gateway must be an IPv4 address.')
    if router.is_unspecified or router.is_multicast or router.is_loopback or router.is_reserved or int(router) >> 24 == 0:
        raise ValueError(f'{role} gateway must be a usable unicast router address.')
    if router not in network:
        subnet = 'management' if role == 'Management' else 'cluster/private'
        raise ValueError(f'{role} gateway must belong to the {subnet} subnet.')
    if router == interface.ip:
        raise ValueError(f'{role} gateway cannot equal the node IP address ({router}). Enter the router address.')
    if network.prefixlen <= 30 and router in (network.network_address, network.broadcast_address):
        raise ValueError(f'{role} gateway cannot be the subnet network or broadcast address ({router}).')


def gateway_node_conflicts(values: dict, peers: list[dict]) -> dict[str, str]:
    conflicts = {}
    inventory = [values, *peers]
    for field in ('management_gateway', 'cluster_gateway'):
        gateway = values.get(field, '')
        if not gateway:
            continue
        for node in inventory:
            for address_field in ('management_ip', 'cluster_ip'):
                address = node.get(address_field, '')
                if address and gateway == host_address(address):
                    conflicts[field] = f"Gateway {gateway} equals a node IP address ({node.get('hostname', 'this node')}). Enter the router address."
    # Also prevent assigning a new node the address already used by a router.
    for field in ('management_ip', 'cluster_ip'):
        address = values.get(field, '')
        if not address:
            continue
        for node in peers:
            if host_address(address) in {node.get('management_gateway', ''), node.get('cluster_gateway', '')}:
                conflicts[field] = f"This IP address is already configured as a gateway for {node.get('hostname', 'another node')}."
    return conflicts
