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
    assert b"0.1.12" in response.data
    assert b"2026-10-09" in response.data
    assert b"Cluster STONITH Configuration and Testing" in response.data
    assert b"mandatory password replacement" in response.data
    assert b"Added Project Groups" in response.data


def test_changelog_preserves_notes_without_subsections(tmp_path: Path):
    path = tmp_path / "CHANGELOG.md"
    path.write_text(
        "# Changelog\n\n## [Unreleased]\n\n"
        "## [0.1.12] - 2026-10-09\n\n### Fixed\n\n- New fix.\n\n"
        "## [0.1.11] - 2026-09-16\n\n- Existing feature.\n- Existing fix.\n\n"
        "### Documentation\n\n- Existing documentation.\n"
    )
    releases = read_changelog(path)
    assert releases[0].sections == []
    assert releases[1].sections[0].title == "Fixed"
    assert releases[1].sections[0].items == ["New fix."]
    assert releases[2].sections[0].title == "Changes"
    assert releases[2].sections[0].items == ["Existing feature.", "Existing fix."]
    assert releases[2].sections[1].items == ["Existing documentation."]
