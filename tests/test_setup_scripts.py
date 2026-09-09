from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_local_updater_preserves_state_and_supports_rollback():
    script = (ROOT / "setup" / "update-local.sh").read_text()

    assert 'database_file="${data_dir}/clusterweaver.db"' in script
    assert 'cp --preserve=timestamps "${database_file}" "${database_backup}"' in script
    assert '"${venv_dir}/bin/alembic" upgrade head' in script
    assert '"${app_dir}/setup/check.sh"' in script
    assert "Update failed; restoring the previous application and database." in script
    assert 'mv "${old_app}" "${app_dir}"' in script
    assert 'cp --preserve=timestamps "${database_backup}" "${database_file}"' in script


def test_offline_installer_uses_direct_podman_requirements_and_quadlet_start():
    preflight = (ROOT / "setup" / "offline-container" / "preflight.sh").read_text()
    installer = (ROOT / "setup" / "offline-container" / "install-offline.sh").read_text()

    assert "for package in podman openssl curl" in preflight
    assert "for component in crun netavark aardvark-dns" in preflight
    assert 'warn "subscription-manager cannot obtain the system identity' in preflight
    assert "dnf install -y podman openssl curl" in installer
    assert 'systemctl start clusterweaver.service' in installer
    assert 'systemctl enable --now clusterweaver.service' not in installer
    assert '"${data_dir}/Project-Import"' in installer


def test_native_installer_configures_server_project_import_directory():
    installer = (ROOT / "setup" / "install.sh").read_text()

    assert '"${data_dir}/Project-Import"' in installer
    assert "CLUSTERWEAVER_PROJECT_IMPORT_ROOT=/var/lib/clusterweaver/data/Project-Import" in installer


def test_code_update_builder_checks_dependencies_and_emits_checksums():
    builder = (ROOT / "setup" / "offline-container" / "build-code-update.sh").read_text()

    assert "install --dry-run --no-index" in builder
    assert "--base-image" in builder
    assert "BASE_IMAGE_ID=" in builder
    assert "CHECKSUMS.sha256" in builder
    assert '"${package_name}.sha256"' in builder


def test_code_updater_validates_and_rolls_back_persistent_installation():
    updater = (ROOT / "setup" / "offline-container" / "update-code.sh").read_text()

    assert "Code update checksum verification failed." in updater
    assert "sha256sum --check CHECKSUMS.sha256" in updater
    assert "BASE_IMAGE_ID" in updater
    assert "Volume=/opt/clusterweaver/live:/opt/clusterweaver/app:ro,Z" in updater
    assert "Code update failed; restoring the previous code, database, and Quadlet." in updater
    assert "podman healthcheck run clusterweaver" in updater


def test_full_offline_bundle_installs_incremental_updater():
    builder = (ROOT / "setup" / "offline-container" / "build-offline-bundle.sh").read_text()
    installer = (ROOT / "setup" / "offline-container" / "install-offline.sh").read_text()

    assert "update-code.sh" in builder
    assert "clusterweaver-update" in installer
