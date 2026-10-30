"""Controller credentials encrypted with a service-owned key outside project exports."""
import fcntl
import os
from pathlib import Path
import stat

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app


def cipher(create=False):
    root = Path(current_app.config.get('STONITH_SECRETS_ROOT') or Path(current_app.config['PROJECTS_ROOT']).parent / 'stonith_secrets')
    if root.resolve().is_relative_to(Path(current_app.config['PROJECTS_ROOT']).resolve()):
        raise ValueError('STONITH_SECRETS_ROOT must be outside the project Git/export directory.')
    if not create and not root.exists():
        raise ValueError('Controller encryption key is unavailable; re-enter the password.')
    try:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = root.lstat()
    except OSError:
        raise ValueError('Cannot access controller secret directory. Check service permissions.') from None
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise ValueError('Controller secret directory must be service-owned with permissions 0700.')
    path = root / 'key'
    try:
        fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | (os.O_CREAT if create else 0), 0o600)
        with os.fdopen(fd, 'r+b') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise ValueError('Controller encryption key must be service-owned with permissions 0600.')
            key = stream.read()
            if not key and create:
                key = Fernet.generate_key()
                stream.write(key)
                stream.flush()
                os.fsync(stream.fileno())
        return Fernet(key)
    except (OSError, ValueError):
        raise ValueError('Controller encryption key cannot be read or created. Check service permissions; preserve the original key when restoring a database.') from None


def encrypt_password(password):
    return cipher(create=True).encrypt(password.encode()).decode()


def decrypt_password(token):
    if not token:
        return ''
    try:
        return cipher().decrypt(token.encode()).decode()
    except InvalidToken:
        raise ValueError('Saved controller password cannot be decrypted. Restore the original encryption key or enter a new password.') from None
