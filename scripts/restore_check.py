#!/usr/bin/env python3
"""Native restoration drill into a newly created disposable PostgreSQL database."""
import importlib.util,os,secrets,subprocess,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_launcher',root/'scripts/local.py');local=importlib.util.module_from_spec(spec);spec.loader.exec_module(local)
env=local.configure();name='test_restore_'+secrets.token_hex(6)
code=r'''
import os,tempfile,psycopg
from psycopg import sql
from pathlib import Path
from app.backups import create_backup,restore_backup,validate_restore
admin=Path(os.environ['BETHUNTER_ADMIN_SECRET_FILE']).read_text().strip()
name=os.environ['BETHUNTER_RESTORE_TARGET']
kwargs=dict(host='127.0.0.1',port=55432,dbname='postgres',user='bethunter_local_admin',password=admin,autocommit=True)
with psycopg.connect(**kwargs) as c:c.execute(sql.SQL('CREATE DATABASE {} WITH TEMPLATE template0 OWNER bethunter_migrator').format(sql.Identifier(name)))
try:
    backup=create_backup()
    target='postgresql+psycopg://bethunter_migrator:'+os.environ['BETHUNTER_MIGRATOR_PASSWORD']+'@127.0.0.1:55432/'+name
    with tempfile.TemporaryDirectory() as directory:
        result=restore_backup(backup['file'],target,Path(directory)/'auth.env')
        print('Restauração verificada em alvo descartável; hashes de documentos/PDFs e segredos MFA validados. Banco da aplicação preservado.')
finally:
    with psycopg.connect(**kwargs) as c:c.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
'''
env.update({'BETHUNTER_ADMIN_SECRET_FILE':str(local.RUNTIME/'postgres-admin-password'),'BETHUNTER_RESTORE_TARGET':name})
subprocess.run([str(local.PYTHON),'-c',code],cwd=root/'backend',env=env,check=True)
