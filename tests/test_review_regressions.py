import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock
from sqlalchemy import select
from app.db import SessionLocal
from app.models import User,Domain,Analysis,Indicator,Schedule,AutoQuota,now
from app import worker


def test_graph_observation_is_latest(auth):
    with SessionLocal() as db:
        user=db.scalar(select(User));domain=Domain(owner_id=user.id,name='example.org');db.add(domain);db.flush()
        for age in [2,0]:
            analysis=Analysis(domain_id=domain.id,score=0,classification='test-only',result={},created=now()-timedelta(days=age))
            db.add(analysis);db.flush();db.add(Indicator(analysis_id=analysis.id,kind='ip',value='93.184.216.34'))
        db.commit()
    observed=auth.get('/api/intelligence/graph').json()['edges'][0]['observed']
    assert observed[:10]==now().date().isoformat()


def test_scheduler_database_error_is_recorded_without_poisoning_transaction(auth,monkeypatch):
    did=auth.post('/api/domains',json={'value':'example.org'}).json()['id']
    auth.post('/api/schedules',json={'domain_id':did})
    monkeypatch.setattr('app.worker.analyze',AsyncMock(return_value={'score':0,'classification':'test-only','technical':{},'errors':[]}))
    def duplicate(db,domain,result,actor_id,**kwargs):
        db.add(Domain(owner_id=domain.owner_id,name=domain.name));db.flush()
    monkeypatch.setattr('app.worker.persist_analysis',duplicate)
    assert asyncio.run(worker.tick())
    with SessionLocal() as db:
        schedule=db.scalar(select(Schedule));assert 'IntegrityError' in schedule.last_error
        assert not db.scalar(select(Analysis))
        assert db.scalar(select(AutoQuota)).used==1


def test_failed_collection_does_not_look_clean_with_fresh_regulation(monkeypatch):
    from app.intelligence import analyze
    monkeypatch.setattr('app.network.resolve',AsyncMock(side_effect=ValueError('test-only unavailable')))
    monkeypatch.setattr('app.intelligence.regulatory',lambda db,domain:{'status':'restricted_framework','normative_context':{'verified':True,'kind':'official_restriction_notice'}})
    with SessionLocal() as db:result=asyncio.run(analyze(db,'example.org'))
    assert result['classification']!='Sem indicadores relevantes'
    assert result['verdict']['code']=='collection_incomplete'


def test_scheduler_and_discovery_both_receive_shared_budget(auth,monkeypatch):
    from app.automation import enqueue
    from app.models import AnalysisJob
    from app.config import settings
    with SessionLocal() as db:
        user=db.scalar(select(User))
        for i in range(4):
            d=Domain(owner_id=user.id,name=f'monitor{i}.example.org');db.add(d);db.flush()
            db.add(Schedule(domain_id=d.id,next_run=now()-timedelta(hours=1)))
        for i in range(4):
            d=Domain(owner_id=user.id,name=f'candidate{i}.example.org');db.add(d);db.flush();enqueue(db,d)
        db.commit()
    monkeypatch.setattr(settings(),'auto_analyses_per_day',4)
    no_work=AsyncMock(return_value=False)
    for name in ['tick_autopilot','tick_regulation','tick_feeds']:monkeypatch.setattr(worker,name,no_work)
    result={'score':0,'classification':'test-only','technical':{},'errors':[]}
    monkeypatch.setattr('app.worker.analyze',AsyncMock(return_value=result))
    monkeypatch.setattr('app.automation.analyze',AsyncMock(return_value=result))
    for i in range(4):
        assert asyncio.run(worker.run_cycle(prefer_jobs=bool(i%2)))
        with SessionLocal() as db:db.scalar(select(AutoQuota)).next_allowed=now()-timedelta(seconds=1);db.commit()
    with SessionLocal() as db:
        assert db.scalar(select(AutoQuota)).used==4
        assert len(db.scalars(select(AnalysisJob).where(AnalysisJob.status=='done')).all())==2
        assert len(db.scalars(select(Schedule).where(Schedule.last_run.is_not(None))).all())==2


def test_database_guard_rejects_application_db_even_when_reset_allowed():
    from database_guard import ensure_test_database
    import pytest
    for allowed in [False,True]:
        with pytest.raises(RuntimeError):ensure_test_database('postgresql://app:private@localhost/bethunter',allowed)
    with pytest.raises(RuntimeError):ensure_test_database('postgresql://app:private@localhost/bethunter_test')
    ensure_test_database('postgresql://app:private@localhost/bethunter_test',True)
    ensure_test_database('sqlite://')


def test_pinned_redirect_hosts_have_distinct_sni_and_no_connection_reuse(monkeypatch):
    import httpx
    from app import network
    requests=[];configured=[]
    async def handler(request):
        requests.append(request)
        if len(requests)==1:return httpx.Response(302,headers={'location':'https://second.example.org/'})
        return httpx.Response(200,content=b'fixture only')
    original=httpx.AsyncClient
    def client(**kwargs):
        configured.append(kwargs['limits'].max_keepalive_connections)
        return original(transport=httpx.MockTransport(handler),**kwargs)
    monkeypatch.setattr(network.httpx,'AsyncClient',client)
    monkeypatch.setattr(network,'resolve',AsyncMock(return_value=['93.184.216.34']))
    body,_,_=asyncio.run(network.fetch('https://first.example.org'))
    assert body==b'fixture only'
    assert [r.extensions['sni_hostname'] for r in requests]==['first.example.org','second.example.org']
    assert configured==[0]
