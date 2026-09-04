from ipaddress import ip_address


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
