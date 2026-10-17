#!/usr/bin/env python3
"""Back up a legacy Compose volume, then provision its bootstrap login. No volume deletion."""
import hashlib,io,json,os,secrets,subprocess,tarfile,time
from datetime import datetime,timezone
from pathlib import Path
from cryptography.fernet import Fernet
root=Path(__file__).resolve().parents[1]
values={line.split('=',1)[0]:line.split('=',1)[1] for line in (root/'.env').read_text().splitlines() if line and not line.startswith('#') and '=' in line}
secret=values.get('POSTGRES_ADMIN_PASSWORD','');key=values.get('BACKUP_ENCRYPTION_KEY','')
if not secret or not secret.isalnum() or not key:raise SystemExit('Execute scripts/configure.py e preserve BACKUP_ENCRYPTION_KEY fora dos backups')
directory=root/'.runtime/upgrade';directory.mkdir(mode=0o700,parents=True,exist_ok=True)
raw=directory/('pre-upgrade-'+secrets.token_hex(5)+'.dump')
fd=os.open(raw,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'wb') as file:
    dump=subprocess.Popen(['docker','compose','exec','-T','db','pg_dump','-U','bethunter','-d','bethunter','-Fc'],stdout=file,stderr=subprocess.DEVNULL,cwd=root)
    deadline=time.monotonic()+120
    while dump.poll() is None:
        if time.monotonic()>deadline or raw.stat().st_size>256_000_000:
            dump.kill();dump.wait();raw.unlink(missing_ok=True)
            raise SystemExit('Backup legado excedeu prazo/tamanho. Nenhum papel foi alterado.')
        time.sleep(0.1)
if dump.returncode:raw.unlink();raise SystemExit('Backup legado falhou. Nenhum papel foi alterado.')
if raw.stat().st_size>256_000_000:raw.unlink();raise SystemExit('Backup legado excedeu limite. Nenhum papel foi alterado.')
data=raw.read_bytes();manifest={'version':1,'format':'postgresql','created':datetime.now(timezone.utc).isoformat(),'database_sha256':hashlib.sha256(data).hexdigest(),'auth_encryption_key':values.get('AUTH_ENCRYPTION_KEY','')}
stream=io.BytesIO()
with tarfile.open(fileobj=stream,mode='w:gz') as tar:
    for name,body in [('manifest.json',json.dumps(manifest).encode()),('database.dump',data)]:
        member=tarfile.TarInfo(name);member.size=len(body);member.mode=0o600;tar.addfile(member,io.BytesIO(body))
cipher=Fernet(key.encode());encrypted=cipher.encrypt(stream.getvalue())
assert cipher.decrypt(encrypted)==stream.getvalue()
backup=raw.with_suffix('.bhbackup');fd=os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'wb') as file:file.write(encrypted);file.flush();os.fsync(file.fileno())
raw.unlink()
subprocess.run(['docker','compose','stop','backend','worker','frontend'],cwd=root,check=True)
statement="DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='bethunter_bootstrap') THEN CREATE ROLE bethunter_bootstrap LOGIN SUPERUSER; END IF; END $$;\nALTER ROLE bethunter_bootstrap PASSWORD '"+secret+"';\n"
result=subprocess.run(['docker','compose','exec','-T','db','psql','-U','bethunter','-d','bethunter','-v','ON_ERROR_STOP=1'],input=statement,text=True,cwd=root,capture_output=True)
if result.returncode:raise SystemExit('Provisionamento legado falhou. Backup preservado; banco não removido. Verifique o administrador existente.')
print('Backup criptografado preservado em '+str(backup)+'. Bootstrap preparado; execute docker compose up --build -d.')
