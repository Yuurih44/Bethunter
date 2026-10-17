"""Encrypted bounded backups with MFA key and safe restoration into EMPTY targets."""
import argparse,asyncio,hashlib,io,json,os,secrets,shutil,sqlite3,subprocess,tarfile,tempfile,time
from pathlib import Path
from datetime import datetime,timezone,timedelta
from cryptography.fernet import Fernet
from sqlalchemy import create_engine,inspect,select,text
from sqlalchemy.engine import make_url
from .config import settings
from .models import SystemSchedule,now
from .db import SessionLocal


def pg_env(url):
    cfg=make_url(url)
    return {**os.environ,'PGHOST':cfg.host or 'localhost','PGPORT':str(cfg.port or 5432),
            'PGDATABASE':cfg.database or '','PGUSER':cfg.username or '','PGPASSWORD':cfg.password or ''}

def pg_tool(name):
    found=shutil.which(name)
    if found:return found
    files=sorted(Path('/usr/lib/postgresql').glob('*/bin/'+name),key=lambda p:int(p.parents[1].name),reverse=True)
    if not files:raise RuntimeError('Cliente PostgreSQL não instalado')
    return str(files[0])

def bounded_command(command,env,output=None):
    proc=subprocess.Popen(command,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    started=time.monotonic()
    try:
        while proc.poll() is None:
            if time.monotonic()-started>120 or (output and output.exists() and output.stat().st_size>settings().backup_max_bytes):
                raise RuntimeError('Backup/restauração excedeu limites')
            time.sleep(.1)
        if proc.returncode:raise RuntimeError('Cliente PostgreSQL falhou; credenciais não são exibidas')
    finally:
        if proc.poll() is None:proc.kill();proc.wait()


def recent_backup_usable(details,verify_contents=False):
    """Metadata alone must never authorize deleting preserved PDF bytes."""
    try:
        if details.get('status')!='complete':return False
        created=datetime.fromisoformat(details['created'])
        if created.tzinfo is None:created=created.replace(tzinfo=timezone.utc)
        if not now()-timedelta(hours=48)<=created<=now():return False
        path=Path(details['file'])
        if not path.is_file() or path.is_symlink():return False
        if not 0<path.stat().st_size<=settings().backup_max_bytes*2:return False
        expected=details.get('sha256','')
        if len(expected)!=64:return False
        if verify_contents:
            digest=hashlib.sha256()
            with path.open('rb') as file:
                while chunk:=file.read(1024*1024):digest.update(chunk)
            if digest.hexdigest()!=expected:return False
        return True
    except (OSError,KeyError,ValueError,TypeError):return False


def create_backup(database_url=None):
    cfg=settings()
    if not cfg.backup_encryption_key:raise RuntimeError('Configure BACKUP_ENCRYPTION_KEY e preserve uma cópia fora dos backups')
    source=database_url or cfg.database_url
    with tempfile.TemporaryDirectory(prefix='bethunter-backup-') as temp:
        raw=Path(temp)/'database.dump';parsed=make_url(source)
        if parsed.get_backend_name()=='sqlite':
            if not parsed.database or parsed.database==':memory:':raise RuntimeError('Backup exige banco persistente')
            with sqlite3.connect(parsed.database) as original,sqlite3.connect(raw) as target:original.backup(target)
            format='sqlite'
        elif parsed.get_backend_name()=='postgresql':
            bounded_command([pg_tool('pg_dump'),'--format=custom','--no-owner','--no-acl','--file',str(raw)],pg_env(source),raw);format='postgresql'
        else:raise RuntimeError('Banco não suportado para backup')
        if raw.stat().st_size>cfg.backup_max_bytes:raise RuntimeError('Backup excede limite')
        data=raw.read_bytes();manifest={'format':format,'created':now().isoformat(),'database_sha256':hashlib.sha256(data).hexdigest(),
            'auth_encryption_key':cfg.auth_encryption_key,'version':1}
        stream=io.BytesIO()
        with tarfile.open(fileobj=stream,mode='w:gz') as tar:
            for name,body in [('manifest.json',json.dumps(manifest).encode()),('database.dump',data)]:
                info=tarfile.TarInfo(name);info.size=len(body);info.mode=0o600;tar.addfile(info,io.BytesIO(body))
        encrypted=Fernet(cfg.backup_encryption_key.encode()).encrypt(stream.getvalue())
        directory=Path(cfg.backup_dir);directory.mkdir(mode=0o700,parents=True,exist_ok=True);directory.chmod(0o700)
        name=now().strftime('%Y%m%dT%H%M%S')+'-'+secrets.token_hex(4)+'.bhbackup';path=directory/name
        partial=path.with_suffix('.part')
        fd=os.open(partial,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as file:file.write(encrypted);file.flush();os.fsync(file.fileno())
        os.replace(partial,path)
        # Only remove old BACKUP copies. Never delete evidence or database rows here.
        for old in sorted(directory.glob('*.bhbackup'),key=lambda p:p.stat().st_mtime,reverse=True)[cfg.backup_keep:]:old.unlink()
        return {'file':str(path.resolve()),'bytes':len(encrypted),'sha256':hashlib.sha256(encrypted).hexdigest(),'created':manifest['created']}

def restore_backup(path,target_url,config_output):
    cfg=settings();path=Path(path)
    if path.stat().st_size>cfg.backup_max_bytes*2:raise RuntimeError('Arquivo de backup excede limite')
    encrypted=path.read_bytes();plain=Fernet(cfg.backup_encryption_key.encode()).decrypt(encrypted)
    with tarfile.open(fileobj=io.BytesIO(plain),mode='r:gz') as tar:
        members={m.name:m for m in tar.getmembers()}
        if set(members)!={'manifest.json','database.dump'} or any(not m.isfile() or m.size>cfg.backup_max_bytes for m in members.values()):raise RuntimeError('Pacote de backup inválido')
        manifest=json.loads(tar.extractfile(members['manifest.json']).read());data=tar.extractfile(members['database.dump']).read()
    if hashlib.sha256(data).hexdigest()!=manifest['database_sha256']:raise RuntimeError('Hash do banco não confere')
    target=make_url(target_url)
    if target.get_backend_name()!=manifest['format'] and not (target.get_backend_name()=='postgresql' and manifest['format']=='postgresql'):raise RuntimeError('Dialeto incompatível')
    if target.render_as_string(hide_password=False)==make_url(cfg.database_url).render_as_string(hide_password=False):raise RuntimeError('Restauração no banco da aplicação foi recusada; use um alvo vazio separado')
    config_path=Path(config_output)
    if config_path.exists():raise RuntimeError('Arquivo de configuração de restauração já existe')
    if target.get_backend_name()=='sqlite':
        dest=Path(target.database)
        if dest.exists() and dest.stat().st_size:raise RuntimeError('Alvo SQLite precisa estar vazio')
        dest.write_bytes(data);dest.chmod(0o600)
        with sqlite3.connect(dest) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or db.execute('PRAGMA foreign_key_check').fetchall():raise RuntimeError('Verificação de integridade falhou')
    else:
        engine=create_engine(target_url)
        try:
            if inspect(engine).get_table_names():raise RuntimeError('Banco de destino não está vazio')
        finally:engine.dispose()
        with tempfile.TemporaryDirectory() as temp:
            dump=Path(temp)/'database.dump';dump.write_bytes(data)
            bounded_command([pg_tool('pg_restore'),'--dbname',target.database,'--exit-on-error','--no-owner','--no-acl',str(dump)],pg_env(target_url))
    validate_restore(target_url,manifest['auth_encryption_key'])
    fd=os.open(config_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as file:file.write('AUTH_ENCRYPTION_KEY='+manifest['auth_encryption_key']+'\n')
    return {'ok':True,'source_created':manifest['created'],'config_file':str(config_path)}

def validate_restore(target_url,auth_key):
    engine=create_engine(target_url)
    checks={'documents':0,'reports':0,'mfa':0}
    try:
        inspector=inspect(engine);tables=set(inspector.get_table_names())
        with engine.connect() as conn:
            for table,label in [('raw_documents','documents'),('reports','reports')]:
                if table not in tables:continue
                columns={c['name'] for c in inspector.get_columns(table)}
                if table=='raw_documents':query='SELECT content,sha256 FROM raw_documents'
                elif 'archived' in columns:query='SELECT content,sha256 FROM reports WHERE archived=false'
                else:query='SELECT content,sha256 FROM reports'
                for row in conn.execute(text(query)):
                    if hashlib.sha256(row.content).hexdigest()!=row.sha256:raise RuntimeError('Hash de evidência restaurada não confere')
                    checks[label]+=1
            if 'users' in tables and 'mfa_secret' in {c['name'] for c in inspector.get_columns('users')}:
                for row in conn.execute(text('SELECT mfa_secret FROM users WHERE mfa_enabled=true')):
                    Fernet(auth_key.encode()).decrypt(row.mfa_secret.encode());checks['mfa']+=1
        return checks
    finally:engine.dispose()


async def tick_backup():
    cfg=settings()
    if not cfg.backup_enabled or not cfg.backup_encryption_key:return False
    with SessionLocal() as db:
        job=db.get(SystemSchedule,'backup')
        if not job:job=SystemSchedule(key='backup',next_run=now(),details={});db.add(job);db.flush()
        job=db.scalar(select(SystemSchedule).where(SystemSchedule.key=='backup',SystemSchedule.next_run<=now()).with_for_update(skip_locked=True))
        if not job:return False
        try:job.details={'status':'complete',**await asyncio.to_thread(create_backup)}
        except Exception as exc:job.details={'status':'failed','error':type(exc).__name__,'checked':now().isoformat()}
        job.next_run=now()+timedelta(hours=cfg.backup_interval_hours);db.commit();return True

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['create','restore']);parser.add_argument('--file');parser.add_argument('--config-output',default='restored-auth.env')
    args=parser.parse_args()
    if args.action=='create':print(json.dumps(create_backup()))
    else:
        if not args.file or not os.getenv('RESTORE_DATABASE_URL'):raise SystemExit('Informe --file e RESTORE_DATABASE_URL para um banco vazio separado')
        print(json.dumps(restore_backup(args.file,os.environ['RESTORE_DATABASE_URL'],args.config_output)))
