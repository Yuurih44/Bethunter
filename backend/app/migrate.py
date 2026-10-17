"""Migration credential only; narrow immutable evidence grants after DDL."""
from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine,text
from .config import settings

def finish_grants(engine):
    if engine.dialect.name!='postgresql':return
    with engine.begin() as db:
        for table in ('alembic_version','audit_logs','evidence','raw_documents','official_sources','regulatory_notices'):
            db.execute(text('REVOKE UPDATE,DELETE ON '+table+' FROM bethunter_runtime'))
        db.execute(text('REVOKE INSERT ON alembic_version FROM bethunter_runtime'))

if __name__=='__main__':
    command.upgrade(Config('alembic.ini'),'head')
    engine=create_engine(settings().database_url)
    finish_grants(engine);engine.dispose()
