import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock
from sqlalchemy import select,func
from app.db import SessionLocal
from app.models import (User,Domain,Analysis,DiscoveryFeed,AnalysisJob,Schedule,
                        SystemSchedule,AutoQuota,WorkflowPolicy,now)
from app.autopilot import tick_autopilot
from app.automation import tick_feeds,tick_jobs
from app.worker import tick
from app.config import settings


def due(db):
    for state in db.scalars(select(SystemSchedule).where(SystemSchedule.key.like('autopilot:%'))):state.next_run=now()-timedelta(seconds=1)
    db.commit()

def test_automatic_setup_idempotent_and_pending_inventory(auth):
    auth.post('/api/domains',json={'value':'example.org'})
    assert asyncio.run(tick_autopilot())
    assert not asyncio.run(tick_autopilot())
    with SessionLocal() as db:
        feed=db.scalar(select(DiscoveryFeed));assert feed.enabled and feed.auto_analyze
        job=db.scalar(select(AnalysisJob));assert job.status=='queued'
        feed.enabled=False;job.status='paused';db.commit();due(db)
    assert not asyncio.run(tick_autopilot())
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(DiscoveryFeed))==1
        assert not db.scalar(select(DiscoveryFeed)).enabled
        assert db.scalar(select(AnalysisJob)).status=='paused'
    status=auth.get('/api/automation/status').json()
    assert status['last_reconciliation']['status']=='active'

def test_existing_analyses_get_fresh_monitoring(auth):
    with SessionLocal() as db:
        u=db.scalar(select(User));d=Domain(owner_id=u.id,name='example.org');db.add(d);db.flush()
        db.add(Analysis(domain_id=d.id,score=0,classification='test-only',result={}));db.commit()
    asyncio.run(tick_autopilot())
    with SessionLocal() as db:
        s=db.scalar(select(Schedule));assert s.automatic and s.enabled
        assert s.next_run.replace(tzinfo=now().tzinfo)<=now()
        assert not db.scalar(select(AnalysisJob))

def test_setup_disabled_and_allowlist_respected(auth,monkeypatch):
    monkeypatch.setattr(settings(),'auto_setup',False)
    assert not asyncio.run(tick_autopilot())
    with SessionLocal() as db:assert not db.scalar(select(DiscoveryFeed))
    monkeypatch.setattr(settings(),'auto_setup',True)
    monkeypatch.setattr(settings(),'discovery_allowed_hosts','other.example.org')
    asyncio.run(tick_autopilot())
    with SessionLocal() as db:assert not db.scalar(select(DiscoveryFeed))

def test_master_pause_and_resume_preserve_individual_pause(auth,monkeypatch):
    auth.post('/api/domains',json={'value':'example.org'});asyncio.run(tick_autopilot())
    d=auth.get('/api/domains').json()[0]
    auth.post('/api/schedules',json={'domain_id':d['id']})
    assert auth.put('/api/automation/workflow',json={'enabled':False}).status_code==200
    fake=AsyncMock(side_effect=AssertionError('network must remain paused'))
    monkeypatch.setattr('app.network.fetch',fake)
    assert not asyncio.run(tick_feeds())
    assert not asyncio.run(tick_jobs())
    assert not asyncio.run(tick())
    fake.assert_not_called()
    with SessionLocal() as db:
        db.scalar(select(DiscoveryFeed)).enabled=False;db.scalar(select(AnalysisJob)).status='paused';db.commit()
    auth.put('/api/automation/workflow',json={'enabled':True})
    with SessionLocal() as db:
        assert db.scalar(select(Schedule)).enabled
        assert not db.scalar(select(DiscoveryFeed)).enabled
        assert db.scalar(select(AnalysisJob)).status=='paused'

def test_retries_backoff_bounded(auth):
    auth.post('/api/domains',json={'value':'example.org'});asyncio.run(tick_autopilot())
    with SessionLocal() as db:
        job=db.scalar(select(AnalysisJob));job.status='failed';job.attempts=1;job.finished=now();db.commit();due(db)
    asyncio.run(tick_autopilot())
    with SessionLocal() as db:
        job=db.scalar(select(AnalysisJob));assert job.status=='failed'
        job.finished=now()-timedelta(minutes=6);db.commit();due(db)
    asyncio.run(tick_autopilot())
    with SessionLocal() as db:
        job=db.scalar(select(AnalysisJob));assert job.status=='queued'
        job.status='failed';job.attempts=3;job.finished=now()-timedelta(days=1);db.commit();due(db)
    asyncio.run(tick_autopilot())
    with SessionLocal() as db:assert db.scalar(select(AnalysisJob)).status=='failed'

def test_inactive_and_viewer_never_get_discovery(auth):
    with SessionLocal() as db:
        db.scalar(select(User)).active=False
        db.add(User(email='viewer@example.org',password='fixture-only',role='viewer'));db.commit()
    assert not asyncio.run(tick_autopilot())
    with SessionLocal() as db:assert not db.scalar(select(DiscoveryFeed))

def test_scheduler_shares_daily_quota_with_queue(auth,monkeypatch):
    did=auth.post('/api/domains',json={'value':'example.org'}).json()['id']
    auth.post('/api/schedules',json={'domain_id':did})
    async def fake(db,name):return {'score':0,'classification':'test-only','technical':{},'errors':[]}
    monkeypatch.setattr('app.worker.analyze',fake)
    monkeypatch.setattr(settings(),'auto_analyses_per_day',1)
    assert asyncio.run(tick())
    with SessionLocal() as db:
        quota=db.scalar(select(AutoQuota));assert quota.used==1
        quota.next_allowed=now()-timedelta(seconds=1)
        db.scalar(select(Schedule)).next_run=now()-timedelta(seconds=1);db.commit()
    assert not asyncio.run(tick())

def test_automatic_retries_respect_full_queue(auth,monkeypatch):
    for value in ['example.org','example.net']:auth.post('/api/domains',json={'value':value})
    asyncio.run(tick_autopilot())
    with SessionLocal() as db:
        jobs=db.scalars(select(AnalysisJob).order_by(AnalysisJob.id)).all()
        jobs[0].status='failed';jobs[0].attempts=1;jobs[0].finished=now()-timedelta(hours=1)
        jobs[1].status='paused';db.commit();due(db)
    monkeypatch.setattr(settings(),'auto_queue_limit',1)
    asyncio.run(tick_autopilot())
    with SessionLocal() as db:
        assert db.scalar(select(AnalysisJob).order_by(AnalysisJob.id)).status=='failed'

def test_automatic_source_respects_source_limit(auth):
    with SessionLocal() as db:
        owner=db.scalar(select(User))
        for i in range(10):db.add(DiscoveryFeed(owner_id=owner.id,name='test-only',url=f'https://raw.githubusercontent.com/fixtures/{i}',format='domains',permission_reference='test-only fixture',enabled=False))
        db.commit()
    asyncio.run(tick_autopilot())
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(DiscoveryFeed))==10
