"""Privileged one-shot provisioning. Runtime never receives this credential."""
import os
import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url


def provision(admin_url,runtime_password,migrator_password):
    url=make_url(admin_url)
    with psycopg.connect(host=url.host,port=url.port or 5432,dbname=url.database,user=url.username,password=url.password,autocommit=True) as conn:
        database=conn.execute('SELECT current_database()').fetchone()[0]
        for role,password in [('bethunter_runtime',runtime_password),('bethunter_migrator',migrator_password)]:
            if not conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone():conn.execute(sql.SQL('CREATE ROLE {} LOGIN').format(sql.Identifier(role)))
            conn.execute(sql.SQL('ALTER ROLE {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(role),sql.Literal(password)))
        # Transfer only project relations in this database. Do not reassign cluster/templates.
        objects=conn.execute("SELECT c.relname,c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','S','v','m') AND (c.relkind<>'S' OR NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid='pg_class'::regclass AND d.objid=c.oid AND d.deptype IN ('a','i'))) ORDER BY CASE c.relkind WHEN 'r' THEN 0 ELSE 1 END").fetchall()
        for name,kind in objects:
            command={'r':'TABLE','S':'SEQUENCE','v':'VIEW','m':'MATERIALIZED VIEW'}[kind]
            conn.execute(sql.SQL('ALTER '+command+' public.{} OWNER TO bethunter_migrator').format(sql.Identifier(name)))
        conn.execute(sql.SQL('ALTER DATABASE {} OWNER TO bethunter_migrator').format(sql.Identifier(database)))
        conn.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
        conn.execute('GRANT USAGE,CREATE ON SCHEMA public TO bethunter_migrator')
        conn.execute('GRANT USAGE ON SCHEMA public TO bethunter_runtime')
        conn.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO bethunter_runtime')
        conn.execute('GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO bethunter_runtime')
        conn.execute('ALTER DEFAULT PRIVILEGES FOR ROLE bethunter_migrator IN SCHEMA public GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO bethunter_runtime')
        conn.execute('ALTER DEFAULT PRIVILEGES FOR ROLE bethunter_migrator IN SCHEMA public GRANT USAGE,SELECT ON SEQUENCES TO bethunter_runtime')
        conn.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO bethunter_runtime').format(sql.Identifier(database)))
        if os.getenv('POSTGRES_ADMIN_PASSWORD'):
            if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname='bethunter_bootstrap'").fetchone():conn.execute('CREATE ROLE bethunter_bootstrap LOGIN SUPERUSER')
            conn.execute(sql.SQL('ALTER ROLE bethunter_bootstrap PASSWORD {}').format(sql.Literal(os.environ['POSTGRES_ADMIN_PASSWORD'])))
        # Legacy application credential is retired, without deleting its role/data.
        if conn.execute("SELECT 1 FROM pg_roles WHERE rolname='bethunter'").fetchone():conn.execute('ALTER ROLE bethunter NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE')

if __name__=='__main__':
    required=['ADMIN_DATABASE_URL','APP_DATABASE_PASSWORD','MIGRATOR_PASSWORD']
    if any(not os.getenv(k) for k in required):raise SystemExit('Configure as credenciais de provisionamento no ambiente')
    provision(*(os.environ[k] for k in required));print('Papéis de runtime e migração provisionados; segredos não são exibidos.')
