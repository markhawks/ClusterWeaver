from pathlib import Path

from clusterweaver.core.models import ProjectData
from clusterweaver.core.serializers import write_project_yaml
from clusterweaver.core.services.git import GitService


class ProjectFileService:
    def __init__(self, projects_root: Path) -> None:
        self.projects_root = Path(projects_root)
        self.git = GitService(self.projects_root)

    def save(self, project: ProjectData, commit_message: str) -> tuple[Path, bool]:
        self.git.initialize()
        path, changed = write_project_yaml(project, self.projects_root)
        committed = self.git.commit_path(path, commit_message) if changed else False
        return path, committed
