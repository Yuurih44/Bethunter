#!/usr/bin/env python3
"""Linux local launcher. Keeps services, secrets and logs inside .runtime/."""
import argparse
import base64
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import venv

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime'
PYTHON = ROOT / '.venv/bin/python'
PGDATA = RUNTIME / 'postgres'
PGPORT = 55432


def say(message):
    print(message, flush=True)


def run(args, *, cwd=ROOT, env=None, capture=False):
    return subprocess.run([str(a) for a in args], cwd=cwd, env=env,
                          check=True, text=True, capture_output=capture)


def pg_bin(name):
    found = shutil.which(name)
    if found:
        return Path(found)
    candidates = sorted(Path('/usr/lib/postgresql').glob(f'*/bin/{name}'),
                        key=lambda p: int(p.parents[1].name), reverse=True)
    if not candidates:
        raise RuntimeError('PostgreSQL ausente. Instale: sudo apt install postgresql')
    return candidates[0]


def mail_configuration():
    values={}
    path=RUNTIME/'local.env'
    if path.exists():
        for line in path.read_text().splitlines():
            if line and not line.startswith('#') and '=' in line:
                key,value=line.split('=',1);values[key]=value
    return values.get('SMTP_MODE','local'),int(values.get('SMTP_PORT','1025'))


def check_ports():
    mode,mail_port=mail_configuration()
    ports=(PGPORT,8000,8080,mail_port) if mode=='local' else (PGPORT,8000,8080)
    for port in ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                # Match Uvicorn/PostgreSQL restart semantics: TIME_WAIT is not a live listener.
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(('127.0.0.1', port))
        except PermissionError as exc:
            raise RuntimeError('Este terminal bloqueia sockets locais. Execute ./iniciar.sh no terminal normal do Kali, fora do sandbox do agente.') from exc
        except OSError as exc:
            raise RuntimeError(f'Porta {port} indisponível: {exc}. Use ./iniciar.sh status e encerre uma execução anterior antes de iniciar.') from exc


def health(url):
    try:
        # Local health checks never inherit HTTP_PROXY/HTTPS_PROXY.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=3) as response:
            return response.status == 200
    except Exception:
        return False


def expected_build():
    spec=importlib.util.spec_from_file_location('bethunter_source_identity',ROOT/'backend/app/build.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.BUILD_ID


def current_backend(url='http://127.0.0.1:8000/api/version'):
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url,timeout=3) as response:
            payload=json.load(response)
        return payload.get('build_id')==expected_build()
    except (OSError,ValueError):
        return False


def start_stamp(pid):
    try:
        stat = Path(f'/proc/{pid}/stat').read_text()
        return stat.rsplit(')', 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def records():
    path = RUNTIME / 'processes.json'
    return json.loads(path.read_text()) if path.exists() else {}


def alive(record):
    return bool(record and record.get('stamp') is not None and start_stamp(record['pid']) == record['stamp'])


def save_records(data):
    (RUNTIME / 'processes.json').write_text(json.dumps(data, indent=2))


def launch(name, command, cwd, env, state):
    logpath = RUNTIME / f'{name}.log'
    with logpath.open('ab') as log:
        process = subprocess.Popen([str(x) for x in command], cwd=cwd, env=env,
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                   start_new_session=True)
    state[name] = {'pid': process.pid, 'stamp': start_stamp(process.pid)}
    save_records(state)
    return process


def configure():
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    RUNTIME.chmod(0o700)
    path = RUNTIME / 'local.env'
    if not path.exists():
        password = secrets.token_hex(24)
        config = {
            'DATABASE_URL': f'postgresql+psycopg://bethunter_runtime:{password}@127.0.0.1:{PGPORT}/bethunter',
            'ORIGIN': 'http://localhost:8080',
            'COOKIE_SECURE': 'false',
            'REGISTRATION_ENABLED': 'true',
            'REGISTRATION_MODE': 'invite',
            'ENRICH_ASN': 'false',
            'SOURCE_MAX_AGE_DAYS': '7',
            'BETHUNTER_DB_PASSWORD': password,
        }
        with path.open('x') as file:
            os.chmod(path, 0o600)
            file.write(''.join(f'{key}={value}\n' for key, value in config.items()))
    entries=path.read_text()
    existing={line.split('=',1)[0]:line.split('=',1)[1] for line in entries.splitlines() if line and not line.startswith('#') and '=' in line}
    additions={}
    for name in ('AUTH_ENCRYPTION_KEY','BACKUP_ENCRYPTION_KEY'):
        if not existing.get(name):additions[name]=base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    if not existing.get('BETHUNTER_MIGRATOR_PASSWORD'):additions['BETHUNTER_MIGRATOR_PASSWORD']=secrets.token_hex(24)
    for name,value in {'SMTP_MODE':'local','SMTP_HOST':'127.0.0.1','SMTP_PORT':'1025',
        'MAIL_CAPTURE_DIR':str(RUNTIME/'mail'),'BACKUP_DIR':str(RUNTIME/'backups')}.items():
        if name not in existing:additions[name]=value
    if existing.get('DATABASE_URL','').startswith('postgresql+psycopg://bethunter:'):
        additions['DATABASE_URL']=existing['DATABASE_URL'].replace('://bethunter:', '://bethunter_runtime:',1)
    if additions:
        with path.open('a') as file:file.write('\n'+''.join(k+'='+v+'\n' for k,v in additions.items()))
    path.chmod(0o600)
    env = dict(os.environ)
    for line in path.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            env[key] = value
    env['MIGRATION_DATABASE_URL']=f"postgresql+psycopg://bethunter_migrator:{env['BETHUNTER_MIGRATOR_PASSWORD']}@127.0.0.1:{PGPORT}/bethunter"
    return env


def python_dependencies():
    if not PYTHON.exists():
        say('Criando ambiente Python local…')
        venv.EnvBuilder(with_pip=True, system_site_packages=True).create(ROOT / '.venv')
    modules = ['fastapi', 'uvicorn', 'sqlalchemy', 'psycopg', 'pydantic_settings',
               'alembic', 'httpx', 'argon2', 'dns', 'bs4', 'weasyprint', 'pyotp', 'cryptography', 'email_validator']
    probe = 'import importlib; ' + '; '.join(f'importlib.import_module({m!r})' for m in modules)
    result = subprocess.run([str(PYTHON), '-c', probe], capture_output=True)
    if result.returncode:
        say('Instalando dependências Python…')
        run([PYTHON, '-m', 'pip', 'install', '-r', ROOT / 'backend/requirements.txt'])
    else:
        say('Dependências Python disponíveis no ambiente local.')


def postgres(env):
    admin_secret = RUNTIME / 'postgres-admin-password'
    if not admin_secret.exists():
        with admin_secret.open('x') as file:
            os.chmod(admin_secret, 0o600)
            file.write(secrets.token_hex(24))
    if not (PGDATA / 'PG_VERSION').exists():
        say('Inicializando PostgreSQL privado do projeto…')
        run([pg_bin('initdb'), '-D', PGDATA, '-U', 'bethunter_local_admin',
             '-A', 'scram-sha-256', '--pwfile', admin_secret], capture=True)
    say('Iniciando PostgreSQL em 127.0.0.1:55432…')
    run([pg_bin('pg_ctl'), '-D', PGDATA, '-l', RUNTIME / 'postgres.log',
         '-o', f"-h 127.0.0.1 -p {PGPORT} -k {RUNTIME}", '-w', 'start'])
    # Application role has no superuser privilege. Secrets only travel via env/stdin.
    setup = """import os,psycopg
from app.bootstrap import provision
admin=os.environ['BETHUNTER_PG_ADMIN']
with psycopg.connect(host='127.0.0.1',port=55432,user='bethunter_local_admin',password=admin,dbname='postgres',autocommit=True) as c:
    if not c.execute('SELECT 1 FROM pg_database WHERE datname=%s',('bethunter',)).fetchone():c.execute('CREATE DATABASE bethunter')
provision('postgresql+psycopg://bethunter_local_admin:'+admin+'@127.0.0.1:55432/bethunter',os.environ['BETHUNTER_DB_PASSWORD'],os.environ['BETHUNTER_MIGRATOR_PASSWORD'])
"""
    db_env = dict(env, BETHUNTER_PG_ADMIN=admin_secret.read_text().strip())
    run([PYTHON, '-c', setup], cwd=ROOT/'backend',env=db_env, capture=True)



def stop():
    state = records()
    for name in ('frontend', 'worker', 'backend','maildev'):
        record = state.get(name)
        if alive(record):
            os.killpg(record['pid'], signal.SIGTERM)
            say(f'{name}: sinal de encerramento enviado')
    deadline = time.monotonic() + 10
    while any(alive(r) for r in state.values()) and time.monotonic() < deadline:
        time.sleep(0.2)
    if PGDATA.exists():
        result = subprocess.run([str(pg_bin('pg_ctl')), '-D', str(PGDATA), 'status'], capture_output=True)
        if result.returncode == 0:
            run([pg_bin('pg_ctl'), '-D', PGDATA, '-m', 'fast', '-w', 'stop'])
    if RUNTIME.exists():
        save_records({})
    say('Dados preservados em .runtime/postgres.')


def start():
    if os.geteuid() == 0:
        raise RuntimeError('Execute como usuário normal, sem sudo. PostgreSQL não deve iniciar como root.')
    previous=records()
    if any(alive(r) for r in previous.values()):
        required=('backend','worker','frontend','maildev') if mail_configuration()[0]=='local' else ('backend','worker','frontend')
        complete=all(alive(previous.get(name)) for name in required)
        if complete and health('http://localhost:8080/api/health') and current_backend():
            say('BetHunter já está disponível e atualizado: http://localhost:8080')
            return
        say('Execução anterior incompleta ou desatualizada. Reiniciando os serviços do projeto…')
        stop()
    check_ports()
    for command in ('node', 'npm'):
        if not shutil.which(command):
            raise RuntimeError(f'{command} ausente. Instale Node.js 22+ e npm.')
    pg_bin('initdb')
    env = configure()
    python_dependencies()
    say('Instalando dependências do frontend…')
    run(['npm', 'ci' if (ROOT / 'frontend/package-lock.json').exists() else 'install', '--no-audit', '--no-fund'], cwd=ROOT / 'frontend')
    say('Validando TypeScript e gerando frontend…')
    run(['npm', 'run', 'build'], cwd=ROOT / 'frontend')
    state = {}
    try:
        postgres(env)
        say('Aplicando migrações…')
        run([PYTHON, '-m', 'app.migrate'], cwd=ROOT / 'backend', env=dict(env,DATABASE_URL=env['MIGRATION_DATABASE_URL']))
        if env.get('SMTP_MODE')=='local':
            launch('maildev',[PYTHON,'-m','app.maildev','--port',env['SMTP_PORT'],'--directory',env['MAIL_CAPTURE_DIR']],ROOT/'backend',env,state)
        launch('backend', [PYTHON, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1',
                          '--port', '8000', '--no-proxy-headers'], ROOT / 'backend', env, state)
        deadline = time.monotonic() + 60
        while not health('http://127.0.0.1:8000/api/health'):
            if not alive(state['backend']) or time.monotonic() > deadline:
                raise RuntimeError('API não iniciou. Consulte .runtime/backend.log')
            time.sleep(0.5)
        if not current_backend():
            raise RuntimeError('A API iniciada não corresponde ao código atual. Consulte .runtime/backend.log')
        launch('worker', [PYTHON, '-m', 'app.worker'], ROOT / 'backend', env, state)
        launch('frontend', ['node', ROOT / 'frontend/node_modules/vite/bin/vite.js',
                            'preview', '--host', '127.0.0.1', '--port', '8080', '--strictPort'],
               ROOT / 'frontend', env, state)
        deadline = time.monotonic() + 30
        while not health('http://localhost:8080/api/health'):
            if not alive(state['frontend']) or time.monotonic() > deadline:
                raise RuntimeError('Frontend/proxy não iniciou. Consulte .runtime/frontend.log')
            time.sleep(0.5)
    except Exception:
        stop()
        raise
    say('\nBetHunter iniciado: http://localhost:8080\nConfigure o administrador: ./iniciar.sh admin EMAIL; depois ative MFA em Segurança.\nLogs: .runtime/*.log\nEncerrar: ./iniciar.sh stop')


def status():
    for name, record in records().items():
        say(f'{name}: {"ativo" if alive(record) else "parado"}')
    healthy=health('http://localhost:8080/api/health')
    say('API via interface: ' + ('saudável' if healthy else 'indisponível'))
    if healthy:
        say('Código da API: ' + ('atualizado' if current_backend() else 'desatualizado ou sem identificação; execute ./iniciar.sh'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start', 'stop', 'status', 'check','admin','invite','reset-mfa','disable','backup','restore','inbox'), nargs='?', default='start')
    parser.add_argument('email',nargs='?')
    arguments=parser.parse_args()
    action = arguments.action
    try:
        if action in ('backup','restore','inbox'):
            env=configure();python_dependencies()
            if action=='inbox':
                run([PYTHON,'-m','app.maildev','--directory',env['MAIL_CAPTURE_DIR'],'--inbox'],cwd=ROOT/'backend',env=env)
            else:
                command=[PYTHON,'-m','app.backups','create' if action=='backup' else 'restore']
                if action=='restore':
                    if not arguments.email:raise RuntimeError('Informe o caminho do backup e RESTORE_DATABASE_URL para alvo vazio')
                    command+=['--file',arguments.email,'--config-output',str(RUNTIME/'restored-auth.env')]
                run(command,cwd=ROOT/'backend',env=env)
        elif action in ('admin','invite','reset-mfa','disable'):
            if not arguments.email:raise RuntimeError('Informe o email da conta')
            env=configure();python_dependencies()
            command=[PYTHON,'-m','app.cli',arguments.email]
            if action!='admin':command.append('--'+action)
            run(command,cwd=ROOT/'backend',env=env)
        elif action == 'start':
            start()
        elif action == 'stop':
            stop()
        elif action == 'status':
            status()
        else:
            check_ports()
            say('Sockets locais permitidos e portas livres.')
    except (RuntimeError, subprocess.CalledProcessError, OSError) as exc:
        say(f'Não foi possível concluir: {exc}')
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            # Avoid printing captured setup errors that could contain credentials.
            say('Uma dependência/comando de inicialização falhou. Consulte os logs locais.')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
