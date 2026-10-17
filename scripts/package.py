#!/usr/bin/env python3
"""Create a source delivery archive without deployment secrets or collected data."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {'.runtime', '.env', '.venv', 'venv', 'node_modules', 'dist', '__pycache__',
            '.pytest_cache', '.git', 'backups', 'mail-capture', 'artifacts', '.ruff_cache'}
SUFFIXES = {'.bhbackup', '.eml', '.db', '.sqlite', '.sqlite3', '.pyc', '.tsbuildinfo', '.dump'}

def package():
    destination = ROOT.parent / 'bethunter-entrega.zip'
    count = 0
    with ZipFile(destination, 'w', ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob('*')):
            relative = path.relative_to(ROOT)
            if not path.is_file() or path.is_symlink():
                continue
            if any(part in EXCLUDED for part in relative.parts):
                continue
            if path.suffix in SUFFIXES or path.name.startswith('.env.') and path.name != '.env.example':
                continue
            if path.name in {'restored-auth.env', 'local.env'} or path.suffix in {'.key', '.pem'}:
                continue
            archive.write(path, Path('bethunter') / relative)
            count += 1
    print(f'{destination}: {count} arquivos de código/documentação')

if __name__ == '__main__':
    package()
