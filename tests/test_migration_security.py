"""Upgrade a populated disposable database, never the application database."""
import os
from pathlib import Path
import subprocess
import sqlite3

def test_security_migration_preserves_existing_accounts(tmp_path):
    root=Path(__file__).parents[1]
    path=tmp_path/'upgrade.sqlite'
    env={**os.environ,'DATABASE_URL':'sqlite:///'+str(path)}
    def migrate(target):
        r=subprocess.run(['python3','-m','alembic','upgrade',target],cwd=root/'backend',env=env,capture_output=True,text=True)
        assert r.returncode==0,r.stderr
    migrate('0003')
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO users (id,email,password,role) VALUES (1,'existing@example.org','existing-hash','analyst')")
        db.execute("INSERT INTO sessions (id,user_id,csrf,expires) VALUES ('hash',1,'csrf','2030-01-01 00:00:00')")
        db.execute("INSERT INTO domains (id,owner_id,name,created,origin) VALUES (1,1,'example.org','2026-01-01','manual')")
    migrate('head')
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT password,active,mfa_enabled FROM users').fetchone()==('existing-hash',1,0)
        assert db.execute('SELECT last_seen,mfa_verified FROM sessions').fetchone()[0]
        assert db.execute('SELECT owner_id FROM domains').fetchone()==(1,)
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
