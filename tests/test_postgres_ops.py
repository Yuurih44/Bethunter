"""Runs in the dedicated PostgreSQL CI database, skipped on local SQLite."""
import secrets
from pathlib import Path
import pytest
from sqlalchemy import select,text,create_engine
from cryptography.fernet import Fernet
from app.db import engine,SessionLocal
from app.config import settings
from app.models import User

pytestmark=pytest.mark.skipif(engine.dialect.name!='postgresql',reason='Requer PostgreSQL dedicado de testes')

def test_postgres_backup_restores_rows_to_separate_database(auth,tmp_path,monkeypatch):
    from app.backups import create_backup,restore_backup
    target_name='test_bethunter_restore_'+secrets.token_hex(5)
    monkeypatch.setattr(settings(),'backup_encryption_key',Fernet.generate_key().decode())
    monkeypatch.setattr(settings(),'backup_dir',str(tmp_path/'backups'))
    target_url=engine.url.set(database=target_name)
    with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:conn.execute(text('CREATE DATABASE '+target_name))
    try:
        backup=create_backup()
        restore_backup(backup['file'],target_url.render_as_string(hide_password=False),tmp_path/'restored-auth.env')
        restored=create_engine(target_url)
        try:
            with restored.connect() as conn:assert conn.execute(text('SELECT email FROM users')).scalar()=='analyst@example.org'
        finally:restored.dispose()
    finally:
        with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:conn.execute(text('DROP DATABASE '+target_name+' WITH (FORCE)'))


def test_runtime_role_cannot_create_tables_or_alter_evidence(auth):
    import psycopg
    from app.bootstrap import provision
    from app.migrate import finish_grants
    app_password=secrets.token_hex(24);migration_password=secrets.token_hex(24)
    provision(settings().database_url,app_password,migration_password)
    finish_grants(engine)
    url=engine.url
    with psycopg.connect(host=url.host,port=url.port,dbname=url.database,user='bethunter_runtime',password=app_password) as conn:
        assert conn.execute("SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user").fetchone()==(False,False,False)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):conn.execute('CREATE TABLE forbidden_runtime_table (id integer)')
        conn.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):conn.execute("DELETE FROM evidence")
        conn.rollback()
        owner=conn.execute('SELECT id FROM users LIMIT 1').fetchone()[0]
        conn.execute("INSERT INTO domains (owner_id,name,created,origin) VALUES (%s,%s,CURRENT_TIMESTAMP,'test-only')",(owner,'runtime.example.org'));conn.commit()
