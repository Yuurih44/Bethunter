from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool
from .config import settings

class Base(DeclarativeBase):
    pass

engine = create_engine(settings().database_url, pool_pre_ping=True, **({"connect_args": {"check_same_thread": False}, "poolclass": StaticPool} if settings().database_url.startswith("sqlite") else {"connect_args":{"connect_timeout":5,"options":"-c timezone=UTC"}}))
if settings().database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def sqlite_fk(conn, record):
        conn.execute("PRAGMA foreign_keys=ON")
SessionLocal = sessionmaker(engine, expire_on_commit=False)

def get_db():
    with SessionLocal() as session:
        yield session
