from pathlib import Path
import subprocess


class GitServiceError(RuntimeError):
    pass


class GitService:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _run(self, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                ["git", *arguments], cwd=self.root, check=check, capture_output=True, text=True
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            detail = getattr(exc, "stderr", "") or str(exc)
            raise GitServiceError(detail.strip()) from exc

    def initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if not (self.root / ".git").exists():
            self._run("init", "--initial-branch=main")
        self._run("config", "user.name", "ClusterWeaver")
        self._run("config", "user.email", "clusterweaver@localhost")
        ignore = self.root / ".gitignore"
        expected = "*.db\n*.db-*\nsecrets.yml\nsecrets.yaml\n*.log\n"
        if not ignore.exists() or ignore.read_text(encoding="utf-8") != expected:
            ignore.write_text(expected, encoding="utf-8")

    def commit_path(self, path: Path, message: str) -> bool:
        relative = path.resolve().relative_to(self.root.resolve())
        self._run("add", "--", str(relative), ".gitignore")
        changed = self._run("diff", "--cached", "--quiet", "--", str(relative), ".gitignore", check=False)
        if changed.returncode == 0:
            return False
        if changed.returncode != 1:
            raise GitServiceError(changed.stderr.strip() or "Unable to inspect Git changes")
        self._run("commit", "-m", message, "--", str(relative), ".gitignore")
        return True

