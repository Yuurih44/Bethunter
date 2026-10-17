import asyncio
from app.worker import tick
from app.db import SessionLocal
from app.models import Schedule, Analysis, User, now
from sqlalchemy import select
from datetime import timedelta

def test_schedule_worker_and_pause(auth,monkeypatch):
    d=auth.post('/api/domains',json={'value':'example.org'}).json()
    assert auth.post('/api/schedules',json={'domain_id':d['id'],'interval_hours':0}).status_code==422
    r=auth.post('/api/schedules',json={'domain_id':d['id'],'interval_hours':24})
    assert r.status_code==200
    async def fake(db,name):
        return {'score':0,'classification':'Situação regulatória não verificada','technical':{},'errors':[]}
    monkeypatch.setattr('app.worker.analyze',fake)
    assert asyncio.run(tick()) is True
    assert asyncio.run(tick()) is False
    with SessionLocal() as db:
        assert db.scalar(select(Analysis)) is not None
        s=db.scalar(select(Schedule));assert s.last_run and s.next_run.replace(tzinfo=now().tzinfo)>now()
    assert auth.post('/api/schedules',json={'domain_id':d['id'],'enabled':False}).json()['enabled'] is False
    assert auth.get('/api/schedules').json()[0]['enabled'] is False

def test_worker_failure_is_recorded(auth,monkeypatch):
    d=auth.post('/api/domains',json={'value':'example.org'}).json()
    auth.post('/api/schedules',json={'domain_id':d['id']})
    async def fail(*args):raise RuntimeError('timeout externo')
    monkeypatch.setattr('app.worker.analyze',fail)
    asyncio.run(tick())
    assert 'timeout externo' in auth.get('/api/schedules').json()[0]['last_error']

def test_worker_respects_revoked_role(auth):
    d=auth.post('/api/domains',json={'value':'example.org'}).json()
    auth.post('/api/schedules',json={'domain_id':d['id']})
    with SessionLocal() as db:
        u=db.scalar(select(User));u.role='viewer';db.commit()
    asyncio.run(tick())
    assert auth.get('/api/schedules').json()[0]['enabled'] is False
