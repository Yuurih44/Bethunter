#!/usr/bin/env python3
"""Create missing secrets without replacing an existing deployment's values."""
import base64,os,secrets
from pathlib import Path
root=Path(__file__).resolve().parents[1];target=root/'.env'
values={}
source=root/'.env.example'
lines=source.read_text().splitlines()+(target.read_text().splitlines() if target.exists() else [])
for line in lines:
    if line.strip() and not line.startswith('#') and '=' in line:
        key,value=line.split('=',1);values[key]=value
for key in ['POSTGRES_PASSWORD','POSTGRES_ADMIN_PASSWORD','APP_DATABASE_PASSWORD','MIGRATOR_PASSWORD']:
    if not values.get(key) or values[key].startswith('troque'):values[key]=secrets.token_hex(24)
for key in ['AUTH_ENCRYPTION_KEY','BACKUP_ENCRYPTION_KEY']:
    if not values.get(key):values[key]=base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
with os.fdopen(fd,'w') as file:file.write(''.join(key+'='+value+'\n' for key,value in values.items()))
target.chmod(0o600)
print('.env configurado com permissão 0600. Preserve BACKUP_ENCRYPTION_KEY separadamente dos arquivos de backup.')
