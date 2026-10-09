from pathlib import Path
from flask import current_app
from clusterweaver.core.services.project_ssh import ProjectSSHKeys


def project_key_store(project):
    root = current_app.config.get('SSH_KEYS_ROOT') or Path(current_app.config['PROJECTS_ROOT']).parent / 'ssh_keys'
    if Path(root).resolve().is_relative_to(Path(current_app.config["PROJECTS_ROOT"]).resolve()):
        raise ValueError("SSH_KEYS_ROOT must be outside the project Git/export directory.")
    return ProjectSSHKeys(root, project.uuid)


def project_credentials(project, override=''):
    return project_key_store(project).credentials(override, current_app.config.get('SSH_BOOTSTRAP_PASSWORD', ''))


