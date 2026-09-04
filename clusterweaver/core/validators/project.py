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
