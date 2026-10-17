import os
os.environ.setdefault('DATABASE_URL','sqlite://')
from database_guard import ensure_test_database
ensure_test_database(os.environ['DATABASE_URL'],os.environ.get('BETHUNTER_ALLOW_TEST_DB_RESET')=='1')
os.environ.setdefault('COOKIE_SECURE','false')
os.environ.setdefault('ORIGIN','http://localhost:8080')
os.environ.setdefault('REGISTRATION_MODE','open')
# Unit tests never deliver mail or create operational backups from inherited settings.
os.environ['SMTP_MODE']='disabled'
os.environ['BACKUP_ENABLED']='false'
os.environ['APP_ENV']='development'
os.environ['REQUIRE_EMAIL_VERIFICATION']='false'
from cryptography.fernet import Fernet
os.environ.setdefault('AUTH_ENCRYPTION_KEY',Fernet.generate_key().decode())
import pytest
from fastapi.testclient import TestClient
from app.db import Base, engine, SessionLocal
from app.main import app
from app.security import buckets
from app.models import User
from sqlalchemy import select

@pytest.fixture(autouse=True)
def database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    buckets.clear()
    yield

# Inline ASGI mode is only for sandboxes that deny AnyIO's thread wake-up sockets.
# CI and normal hosts retain the unmodified FastAPI thread dispatch.
@pytest.fixture(autouse=True)
def inline_dispatch(monkeypatch):
    if os.getenv('BETHUNTER_INLINE_TESTS') != '1':
        return
    import contextlib
    import fastapi.routing
    import fastapi.dependencies.utils
    async def direct(fn,*args,**kwargs):
        return fn(*args,**kwargs)
    @contextlib.asynccontextmanager
    async def inline_context(cm):
        with cm as value:
            yield value
    import asyncio
    monkeypatch.setattr(asyncio,'to_thread',direct)
    monkeypatch.setattr(fastapi.routing,'run_in_threadpool',direct)
    monkeypatch.setattr(fastapi.dependencies.utils,'run_in_threadpool',direct)
    monkeypatch.setattr(fastapi.dependencies.utils,'contextmanager_in_threadpool',inline_context)

class InlineClient:
    def __init__(self):
        import httpx
        self.headers=httpx.Headers()
        self.cookies=httpx.Cookies()
    def request(self,method,url,**kwargs):
        import asyncio,httpx
        async def run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://localhost:8080',headers=self.headers,cookies=self.cookies) as c:
                response=await c.request(method,url,**kwargs)
                self.cookies=c.cookies
                return response
        return asyncio.run(run())
    def get(self,url,**kw):return self.request('GET',url,**kw)
    def post(self,url,**kw):return self.request('POST',url,**kw)
    def patch(self,url,**kw):return self.request('PATCH',url,**kw)
    def put(self,url,**kw):return self.request('PUT',url,**kw)

@pytest.fixture
def client():
    if os.getenv('BETHUNTER_INLINE_TESTS') == '1':
        c=InlineClient()
        c.headers['origin']='http://localhost:8080'
        yield c
        return
    with TestClient(app,base_url='http://localhost:8080') as c:
        c.headers['origin']='http://localhost:8080'
        yield c

@pytest.fixture
def auth(client):
    r=client.post('/api/auth/register',json={'email':'analyst@example.org','password':'secure-password-12345'})
    assert r.status_code==201,r.text
    client.headers['x-csrf-token']=r.json()['csrf']
    return client

@pytest.fixture
def administrator(auth,monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings(),'require_mfa_admin',False)
    with SessionLocal() as db:
        u=db.scalar(select(User));u.role='admin';db.commit()
    return auth
