import pytest

from clusterweaver.core.validators import validate_rhel_release, validate_rhel_version
from clusterweaver.version import __version__


def test_application_version():
    assert __version__ == "0.1.5"


@pytest.mark.parametrize("major", [7, 9, 10])
def test_supported_versions(major):
    validate_rhel_version(major)


def test_rhel_8_is_explicitly_rejected():
    with pytest.raises(ValueError, match="RHEL 8 is not currently supported"):
        validate_rhel_version(8)


@pytest.mark.parametrize("major,minor", [(7, "9"), (9, "8"), (10, "2")])
def test_current_minor_releases_are_supported(major, minor):
    validate_rhel_release(major, minor)


@pytest.mark.parametrize("major,minor", [(9, "9"), (10, "3"), (7, "10")])
def test_unknown_minor_releases_are_rejected(major, minor):
    with pytest.raises(ValueError, match="is not supported"):
        validate_rhel_release(major, minor)
