"""Fingerprint only the source and dependency files actually copied into /app."""
import hashlib
from pathlib import Path


def fingerprint(root):
    root = Path(root)
    files = [root / 'run_agent.py', root / 'requirements.lock', *sorted((root / 'harness').rglob('*.py'))]
    digest = hashlib.sha256()
    for path in files:
        if path.is_symlink() or not path.is_file():
            raise ValueError('source fingerprint requires regular files')
        digest.update(path.relative_to(root).as_posix().encode() + b'\0')
        digest.update(path.read_bytes().replace(b'\r\n', b'\n') + b'\0')
    return digest.hexdigest()
