from pathlib import Path

from clusterweaver.core.services.changelog import read_changelog


def test_changelog_parser_reads_releases(tmp_path: Path):
    path = tmp_path / "CHANGELOG.md"
    path.write_text("# Changelog\n\n## [0.1.0] - 2026-09-04\n\n### Added\n\n- First feature.\n")
    releases = read_changelog(path)
    assert releases[0].version == "0.1.0"
    assert releases[0].date == "2026-09-04"
    assert releases[0].sections[0].items == ["First feature."]


def test_changelog_page_is_available(client):
    response = client.get("/changelog")
    assert response.status_code == 200
    assert b"0.1.0" in response.data
    assert b"Modular Flask application" in response.data
