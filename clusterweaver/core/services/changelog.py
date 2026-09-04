from dataclasses import dataclass, field
from pathlib import Path
import re


@dataclass(slots=True)
class ChangelogSection:
    title: str
    items: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ChangelogRelease:
    version: str
    date: str = ""
    sections: list[ChangelogSection] = field(default_factory=list)


RELEASE_PATTERN = re.compile(r"^## \[(.+?)](?: - (.+))?$")


def read_changelog(path: Path) -> list[ChangelogRelease]:
    """Parse the intentionally small Keep a Changelog subset used by the UI."""
    releases: list[ChangelogRelease] = []
    current_release: ChangelogRelease | None = None
    current_section: ChangelogSection | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        release_match = RELEASE_PATTERN.match(line)
        if release_match:
            current_release = ChangelogRelease(release_match.group(1), release_match.group(2) or "")
            releases.append(current_release)
            current_section = None
        elif line.startswith("### ") and current_release:
            current_section = ChangelogSection(line.removeprefix("### "))
            current_release.sections.append(current_section)
        elif line.startswith("- ") and current_section:
            current_section.items.append(line.removeprefix("- "))
    return releases

