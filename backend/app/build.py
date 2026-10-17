"""Non-secret source identity, frozen when each server process imports this module."""
import hashlib
from pathlib import Path


def source_id(directory=None):
    root=Path(directory) if directory else Path(__file__).parent
    digest=hashlib.sha256()
    for path in sorted(root.rglob('*.py')):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b'\0')
        digest.update(path.read_bytes())
        digest.update(b'\0')
    return digest.hexdigest()


BUILD_ID=source_id()
REQUIRED_SCHEMA_REVISION='0005'
