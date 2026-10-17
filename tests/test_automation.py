import asyncio
import json
from datetime import timedelta
from unittest.mock import AsyncMock
import httpx
import pytest
from sqlalchemy import select
from app.db import SessionLocal
from app.models import DiscoveryFeed,DiscoveryRun,DiscoveryCandidate,AnalysisJob,AutoQuota,Domain,User,Analysis,now
from app.automation import parse_feed,tick_feeds,tick_jobs,CATALOG,enqueue
from app.config import settings
from app import network


def feed_input(**kw):
    return dict(name='Fonte de teste autorizada',url='https://raw.githubusercontent.com/test-owner/test-repo/main/list.txt',format='domains',permission_reference='MIT; fixture sintética de teste',batch_size=2,**kw)


def create_feed(auth,**kw):
    r=auth.post('/api/discovery/feeds',json=feed_input(**kw))
    assert r.status_code==201,r.text
    return r.json()['id']


@pytest.mark.parametrize('format,raw',[('csv',b'domain\nEXAMPLE.org\nexample.org\nhttp://127.0.0.1\n'),('json',b'["EXAMPLE.org",{"domain":"example.org"},123]'),('domains',b'# Source\nEXAMPLE.org\nexample.org\n127.0.0.1'),('hosts',b'# Author\n0.0.0.0 EXAMPLE.org\n127.0.0.1 example.org\n0.0.0.0 localhost')])
def test_feed_formats(format,raw):
    names,errors=parse_feed(raw,format)
    assert names==['example.org'] and errors==1


@pytest.mark.parametrize('format,raw',[('csv',b'wrong\nx'),('json',b'{"items":[]}'),('hosts',b'8.8.8.8 example.org'),('domains',b'<html>broken</html>'),('csv',b'domain\n'),('json',b'[]')])
def test_malformed_feeds_rejected(format,raw):
    with pytest.raises(ValueError):parse_feed(raw,format)


def test_source_url_restricted_and_catalog(auth):
    assert auth.get('/api/discovery/catalog').json()['sources'][0]['url']==CATALOG[0]['url']
    for url in ['http://raw.githubusercontent.com/list','https://evil.org/list','http://127.0.0.1','https://raw.githubusercontent.com/list#fragment']:
        b=feed_input();b['url']=url
        assert auth.post('/api/discovery/feeds',json=b).status_code==422


def test_feed_dedup_cursor_provenance(auth,monkeypatch):
    fid=create_feed(auth)
    fake=AsyncMock(return_value=(b'example.org\nexample.net\nexample.com\n',[],{}))
    monkeypatch.setattr('app.network.fetch',fake)
    assert asyncio.run(tick_feeds()) is True
    assert asyncio.run(tick_feeds()) is False
    assert len(auth.get('/api/domains').json())==2
    assert auth.get('/api/discovery/jobs').json()['counts']=={'queued':2}
    with SessionLocal() as db:
        f=db.get(DiscoveryFeed,fid);f.next_run=now()-timedelta(seconds=1);db.commit()
    assert asyncio.run(tick_feeds()) is True
    assert len(auth.get('/api/domains').json())==3
    with SessionLocal() as db:
        assert len(db.scalars(select(DiscoveryCandidate)).all())==3
        assert db.scalars(select(DiscoveryRun)).first().sha256
    runs=auth.get('/api/discovery/runs').json()
    assert runs[0]['counts']['added']==1 and runs[0]['counts']['duplicates']==1
    assert auth.get('/api/discovery/jobs').json()['counts']=={'queued':3}
    assert fake.call_args.kwargs['https_only'] is True


def test_feed_failure_does_not_import(auth,monkeypatch):
    create_feed(auth)
    monkeypatch.setattr('app.network.fetch',AsyncMock(side_effect=network.UnsafeTarget('private target')))
    assert asyncio.run(tick_feeds()) is True
    assert auth.get('/api/domains').json()==[]
    assert auth.get('/api/discovery/runs').json()[0]['status']=='failed'
    assert 'private target' in auth.get('/api/discovery/feeds').json()[0]['last_error']


def test_feed_without_auto_analysis(auth,monkeypatch):
    create_feed(auth,auto_analyze=False)
    monkeypatch.setattr('app.network.fetch',AsyncMock(return_value=(b'example.org',[],{})))
    asyncio.run(tick_feeds())
    assert len(auth.get('/api/domains').json())==1
    assert not auth.get('/api/discovery/jobs').json()['jobs']
    assert auth.post('/api/discovery/queue').json()['queued']==1


def test_csv_opt_in_and_queue_duplicate(auth):
    r=auth.post('/api/discovery/import',json={'csv':'domain\nexample.org\n','auto_analyze':True})
    assert r.status_code==200,r.text
    assert r.json()['queued']==1
    assert auth.post('/api/discovery/queue').json()['queued']==0


def test_pause_resume_worker_quota_and_retry(auth,monkeypatch):
    auth.post('/api/discovery/import',json={'csv':'domain\nexample.org\nexample.net\n','auto_analyze':True})
    jobs=auth.get('/api/discovery/jobs').json()['jobs']
    oldest=jobs[-1]['id']
    assert auth.post(f'/api/discovery/jobs/{oldest}/action',json={'action':'pause'}).json()['status']=='paused'
    assert auth.post(f'/api/discovery/jobs/{oldest}/action',json={'action':'resume'}).json()['status']=='queued'
    calls=[]
    async def fake(db,name):
        calls.append(name)
        return {'score':0,'classification':'Situação regulatória não verificada','technical':{'ips':['93.184.216.34']},'errors':[]}
    monkeypatch.setattr('app.automation.analyze',fake)
    assert asyncio.run(tick_jobs()) is True
    assert asyncio.run(tick_jobs()) is False  # delay enforced
    with SessionLocal() as db:
        quota=db.scalar(select(AutoQuota));quota.next_allowed=now()-timedelta(seconds=1);quota.used=settings().auto_analyses_per_day;db.commit()
    assert asyncio.run(tick_jobs()) is False  # UTC daily quota enforced
    with SessionLocal() as db:
        quota=db.scalar(select(AutoQuota));quota.day='2000-01-01';db.commit()
    assert asyncio.run(tick_jobs()) is True  # next-day reset
    assert len(calls)==2
    assert auth.get('/api/discovery/jobs').json()['counts']=={'done':2}
    assert auth.post(f'/api/discovery/jobs/{oldest}/action',json={'action':'retry'}).status_code==409


def test_failed_collection_recorded_and_manual_retry(auth,monkeypatch):
    auth.post('/api/discovery/import',json={'csv':'domain\nexample.org\n','auto_analyze':True})
    async def failed(db,name):
        return {'score':0,'classification':'Situação regulatória não verificada','technical':{},'errors':['DNS unavailable']}
    monkeypatch.setattr('app.automation.analyze',failed)
    assert asyncio.run(tick_jobs()) is True
    job=auth.get('/api/discovery/jobs').json()['jobs'][0]
    assert job['status']=='failed' and job['analysis_id']
    assert auth.post(f"/api/discovery/jobs/{job['id']}/action",json={'action':'retry'}).status_code==200
    with SessionLocal() as db:
        q=db.scalar(select(AutoQuota));q.next_allowed=now()-timedelta(seconds=1);db.commit()
    async def recovered(db,name):
        return {'score':0,'classification':'Situação regulatória não verificada','technical':{'ips':['93.184.216.34']},'errors':[]}
    monkeypatch.setattr('app.automation.analyze',recovered)
    assert asyncio.run(tick_jobs()) is True
    with SessionLocal() as db:assert len(db.scalars(select(Analysis)).all())==2
    assert auth.get('/api/discovery/jobs').json()['jobs'][0]['status']=='done'


def test_batch_pause_and_revoked_permission(auth):
    auth.post('/api/discovery/import',json={'csv':'domain\nexample.org\n','auto_analyze':True})
    assert auth.post('/api/discovery/queue/pause').json()['paused']==1
    job=auth.get('/api/discovery/jobs').json()['jobs'][0]
    auth.post(f"/api/discovery/jobs/{job['id']}/action",json={'action':'resume'})
    with SessionLocal() as db:
        u=db.scalar(select(User));u.role='viewer';db.commit()
    assert asyncio.run(tick_jobs()) is True
    assert auth.get('/api/discovery/jobs').json()['jobs'][0]['status']=='paused'
    assert auth.post('/api/discovery/queue').status_code==403


def test_tenant_isolation_of_feeds_and_queue(auth):
    fid=create_feed(auth)
    auth.post('/api/discovery/import',json={'csv':'domain\nexample.org\n','auto_analyze':True})
    jid=auth.get('/api/discovery/jobs').json()['jobs'][0]['id']
    auth.post('/api/auth/logout')
    r=auth.post('/api/auth/register',json={'email':'other@example.org','password':'different-password-1234'})
    auth.headers['x-csrf-token']=r.json()['csrf']
    assert auth.get('/api/discovery/feeds').json()==[]
    assert auth.get('/api/discovery/jobs').json()['jobs']==[]
    assert auth.patch(f'/api/discovery/feeds/{fid}/state',json={'enabled':False}).status_code==404
    assert auth.post(f'/api/discovery/jobs/{jid}/action',json={'action':'pause'}).status_code==404


def test_feed_network_restricts_redirect_host_before_request(monkeypatch):
    requests=[]
    async def handler(request):
        requests.append(request)
        return httpx.Response(302,headers={'location':'https://other.org/list'})
    real=httpx.AsyncClient
    monkeypatch.setattr(network.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handler),**kw))
    monkeypatch.setattr(network,'resolve',AsyncMock(return_value=['93.184.216.34']))
    with pytest.raises(network.UnsafeTarget,match='não autorizado'):
        asyncio.run(network.fetch('https://raw.githubusercontent.com/list',allowed_hosts={'raw.githubusercontent.com'},https_only=True))
    assert len(requests)==1


def test_queue_cap(auth,monkeypatch):
    monkeypatch.setattr(settings(),'auto_queue_limit',1)
    r=auth.post('/api/discovery/import',json={'csv':'domain\nexample.org\nexample.net\n','auto_analyze':True})
    assert r.json()['queued']==1
    assert auth.get('/api/discovery/jobs').json()['counts']=={'queued':1}


def test_queue_resume_all_and_csv_existing(auth):
    auth.post('/api/discovery/import',json={'csv':'domain\nexample.org\n'})
    r=auth.post('/api/discovery/import',json={'csv':'domain\nexample.org\n','auto_analyze':True})
    assert r.json()['added']==0 and r.json()['queued']==1 and r.json()['duplicates']==1
    auth.post('/api/discovery/queue/pause')
    assert auth.post('/api/discovery/queue/resume').json()['resumed']==1
    assert auth.get('/api/discovery/jobs').json()['counts']=={'queued':1}


def test_paused_feed_and_changed_allowlist(auth,monkeypatch):
    fid=create_feed(auth,enabled=False)
    mock=AsyncMock(return_value=(b'example.org',[],{}))
    monkeypatch.setattr('app.network.fetch',mock)
    assert asyncio.run(tick_feeds()) is False
    auth.patch(f'/api/discovery/feeds/{fid}/state',json={'enabled':True})
    monkeypatch.setattr(settings(),'discovery_allowed_hosts','different.org')
    assert asyncio.run(tick_feeds()) is True
    mock.assert_not_called()
    assert auth.get('/api/discovery/runs').json()[0]['status']=='failed'


def test_malformed_response_never_creates_candidates(auth,monkeypatch):
    b=feed_input();b['format']='json'
    assert auth.post('/api/discovery/feeds',json=b).status_code==201
    monkeypatch.setattr('app.network.fetch',AsyncMock(return_value=(b'<html>service unavailable</html>',[],{})))
    asyncio.run(tick_feeds())
    assert not auth.get('/api/domains').json()
    assert auth.get('/api/discovery/runs').json()[0]['status']=='failed'


def test_https_downgrade_on_feed_is_blocked(monkeypatch):
    requests=[]
    async def handler(request):
        requests.append(request)
        return httpx.Response(302,headers={'location':'http://raw.githubusercontent.com/list'})
    real=httpx.AsyncClient
    monkeypatch.setattr(network.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handler),**kw))
    monkeypatch.setattr(network,'resolve',AsyncMock(return_value=['93.184.216.34']))
    with pytest.raises(network.UnsafeTarget,match='HTTPS'):
        asyncio.run(network.fetch('https://raw.githubusercontent.com/list',allowed_hosts={'raw.githubusercontent.com'},https_only=True))
    assert len(requests)==1


def test_feed_origin_reaches_analysis_evidence_and_report(auth,monkeypatch):
    from app.models import Evidence,Report
    create_feed(auth)
    monkeypatch.setattr('app.network.fetch',AsyncMock(return_value=(b'example.org',[],{})))
    asyncio.run(tick_feeds())
    async def collected(db,name):
        return {'score':0,'classification':'Situação regulatória não verificada','technical':{'ips':['93.184.216.34']},'errors':[]}
    monkeypatch.setattr('app.automation.analyze',collected)
    asyncio.run(tick_jobs())
    analysis=auth.get('/api/analyses').json()[0]
    origin=analysis['result']['discovery']
    assert origin['method']=='public_feed' and origin['source_url'].startswith('https://raw.githubusercontent.com/')
    assert len(origin['document_sha256'])==64 and analysis['score']==0
    with SessionLocal() as db:
        assert db.scalar(select(Evidence)).payload['analysis']['discovery']==origin
    did=auth.get('/api/domains').json()[0]['id']
    c=auth.post('/api/cases',json={'title':'Revisão de candidato automático','domain_ids':[did]}).json()
    report=auth.post(f"/api/cases/{c['id']}/reports")
    assert report.status_code==202,report.text
    from app.report_queue import tick_reports
    assert asyncio.run(tick_reports())
    with SessionLocal() as db:
        snapshot=db.scalar(select(Report)).snapshot
        assert snapshot['Domínios e histórico'][0]['history'][0]['result']['discovery']==origin


def test_exhausted_quota_does_not_block_other_user(auth,monkeypatch):
    auth.post('/api/discovery/import',json={'csv':'domain\nfirst.example.org\n','auto_analyze':True})
    with SessionLocal() as db:
        q=db.scalar(select(AutoQuota));q.used=settings().auto_analyses_per_day;db.commit()
    auth.post('/api/auth/logout')
    r=auth.post('/api/auth/register',json={'email':'second@example.org','password':'second-owner-password-1234'})
    auth.headers['x-csrf-token']=r.json()['csrf']
    auth.post('/api/discovery/import',json={'csv':'domain\nsecond.example.org\n','auto_analyze':True})
    calls=[]
    async def collected(db,name):
        calls.append(name)
        return {'score':0,'classification':'Situação regulatória não verificada','technical':{'ips':['93.184.216.34']},'errors':[]}
    monkeypatch.setattr('app.automation.analyze',collected)
    assert asyncio.run(tick_jobs()) is True
    assert calls==['second.example.org']
