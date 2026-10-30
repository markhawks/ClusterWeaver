"""Adjust generated launchers before moving a staged venv to its final path."""
from pathlib import Path
import sys


def prepare(source, destination):
    source = Path(source)
    old = str(source.resolve()).encode()
    new = str(Path(destination).resolve()).encode()
    for path in (source / 'bin').iterdir():
        if path.is_symlink() or not path.is_file():
            continue
        content = path.read_bytes()
        if b'\x00' not in content and old in content:
            path.write_bytes(content.replace(old, new))


if __name__ == '__main__':
    prepare(*sys.argv[1:])
