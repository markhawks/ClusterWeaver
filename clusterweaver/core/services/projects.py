from pathlib import Path
import shutil

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

    def delete(self, project: ProjectData, commit_message: str) -> bool:
        self.git.initialize()
        root = self.projects_root.resolve()
        project_dir = self.projects_root / project.slug
        resolved = project_dir.resolve(strict=False)
        if resolved.parent != root or project_dir.is_symlink():
            raise ValueError("Unsafe project directory")
        project_file = project_dir / "project.yaml"
        if project_dir.exists():
            shutil.rmtree(project_dir)
        return self.git.commit_path(project_file, commit_message)
