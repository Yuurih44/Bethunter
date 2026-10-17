import hashlib
from app.db import SessionLocal
from app.models import Analysis, Evidence, User, Domain, Rule, OfficialSource, now
from app.intelligence import LABELS
from sqlalchemy import select

def add_domain(client,name='example.org'):
    r=client.post('/api/domains',json={'value':name});assert r.status_code==201,r.text
    return r.json()['id']

def test_health(client):
    assert client.get('/api/health').json()=={'status':'ok'}

def test_unauthenticated(client):
    assert client.get('/api/dashboard').status_code==401

def test_registration_auth_csrf_logout(auth):
    assert auth.get('/api/auth/me').status_code==200
    with SessionLocal() as db:
        assert db.scalar(select(User)).password.startswith('$argon2id$')
    token=auth.headers.pop('x-csrf-token')
    assert auth.post('/api/domains',json={'value':'example.org'}).status_code==403
    auth.headers['x-csrf-token']=token
    assert auth.post('/api/auth/logout').status_code==200
    assert auth.get('/api/auth/me').status_code==401

def test_login_rate_limit(client):
    for _ in range(5):
        assert client.post('/api/auth/login',json={'email':'missing@example.org','password':'wrong-password-123'}).status_code==401
    assert client.post('/api/auth/login',json={'email':'missing@example.org','password':'wrong-password-123'}).status_code==429

def test_origin(client):
    client.headers['origin']='https://evil.example'
    assert client.post('/api/auth/register',json={'email':'a@example.org','password':'password-secure-123'}).status_code==403

def test_duplicate_and_invalid(auth):
    a=add_domain(auth,'https://EXAMPLE.org/path?q=test')
    assert add_domain(auth)==a
    assert auth.post('/api/domains',json={'value':'http://127.0.0.1'}).status_code==422
    assert auth.post('/api/auth/register',json={'email':'invalid','password':'123'}).status_code==422

def test_dashboard_zero(auth):
    d=auth.get('/api/dashboard').json()
    assert d['domains']==0 and d['history']==[] and d['recent']==[]

def test_csv_import_dedup_and_errors(auth):
    r=auth.post('/api/discovery/import',json={'csv':'domain\nexample.org\nEXAMPLE.org\nhttp://127.0.0.1\n'}).json()
    assert r['added']==1 and r['duplicates']==1 and len(r['errors'])==1
    assert auth.post('/api/discovery/import',json={'csv':'wrong\nfoo'}).status_code==422

def test_analysis_report_case_flow(auth,monkeypatch):
    async def fake(db,domain):
        return {'score':25,'classification':LABELS[4],'factors':[{'key':'betting_content','weight':25,'explanation':'apostas'}], 'technical':{'ips':['93.184.216.34']},'regulation':{'status':'not_verified','reason':'Nenhuma fonte'},'errors':[],'limitations':['Revisão humana'],'rule_version':'technical-v1'}
    monkeypatch.setattr('app.main.analyze',fake)
    did=add_domain(auth)
    r=auth.post(f'/api/domains/{did}/analyze')
    assert r.status_code==200,r.text
    a=r.json();assert a['score']==25
    assert auth.patch(f"/api/analyses/{a['id']}/review",json={'review':'Revisão técnica com limitações registradas'}).status_code==200
    with SessionLocal() as db:
        e=db.scalar(select(Evidence));assert len(e.sha256)==64
    d=auth.get('/api/dashboard').json();assert d['analyzed']==1 and d['pending']==0
    graph=auth.get('/api/intelligence/graph').json();assert len(graph['edges'])==1
    body={'title':'Caso de teste','domain_ids':[did],'notes':'Conclusão técnica revisada','priority':'high','status':'open'}
    c=auth.post('/api/cases',json=body);assert c.status_code==201,c.text
    cid=c.json()['id']
    for status in ['closed','open','investigating']:
        body['status']=status;assert auth.put(f'/api/cases/{cid}',json=body).status_code==200
    r=auth.post(f'/api/cases/{cid}/reports');assert r.status_code==202,r.text
    import asyncio
    from app.report_queue import tick_reports
    assert asyncio.run(tick_reports())
    report=auth.get('/api/pages/reports').json()['items'][0]
    r=type('Rendered',(),{'json':lambda self:dict(report,download=f"/api/reports/{report['id']}/pdf")})()
    pdf=auth.get(r.json()['download']);assert pdf.content.startswith(b'%PDF-')
    assert hashlib.sha256(pdf.content).hexdigest()==r.json()['sha256']
    assert auth.get(r.json()['download']).content==pdf.content
    assert auth.get('/api/reports').json()[0]['status']=='prepared'
    rid=r.json()['id']
    assert auth.post(f'/api/reports/{rid}/confirmation',json={'protocol':'PROTO-123','confirmation':'Canal oficial, referência da confirmação recebida em data registrada'}).status_code==200
    assert auth.get('/api/dashboard').json()['forwarded']==1
    assert any(a['action']=='case.save' for a in auth.get('/api/audit').json())

def test_tenant_isolation(auth):
    did=add_domain(auth)
    auth.post('/api/auth/logout')
    r=auth.post('/api/auth/register',json={'email':'other@example.org','password':'secure-password-45678'})
    auth.headers['x-csrf-token']=r.json()['csrf']
    assert auth.get('/api/domains').json()==[]
    assert auth.post(f'/api/domains/{did}/analyze').status_code==404
    assert auth.post('/api/cases',json={'title':'Other case','domain_ids':[did]}).status_code==404

def test_viewer_and_admin_permissions(auth):
    assert auth.post('/api/sources/sync').status_code==403
    with SessionLocal() as db:
        u=db.scalar(select(User));u.role='viewer';db.commit()
    assert auth.get('/api/dashboard').status_code==200
    assert auth.post('/api/domains',json={'value':'example.org'}).status_code==403

def test_blocklists(auth):
    did=add_domain(auth)
    for fmt,expected in [('hosts','0.0.0.0 example.org'),('adblock','||example.org^'),('domains','example.org')]:
        r=auth.post('/api/blocklists',json={'domain_ids':[did],'format':fmt})
        assert r.status_code==200 and r.text.strip()==expected

def test_source_failure_recorded(administrator,monkeypatch):
    async def fail(*a,**kw): raise RuntimeError('Fonte indisponível')
    monkeypatch.setattr('app.network.fetch',fail)
    assert administrator.post('/api/sources/sync').json()['status']=='failed'
    assert 'Fonte indisponível' in administrator.get('/api/sources').json()[0]['error']

def test_rule_versioning(administrator):
    body={'version':'review-1','effective_from':'2026-01-01T00:00:00Z','weights':{'betting_content':40,'cross_domain_redirect':20},'rationale':'Revisão humana documentada da política técnica'}
    assert administrator.post('/api/rules',json=body).status_code==201
    assert administrator.post('/api/rules',json=body).status_code==409
    body['version']='bad';body['weights']['betting_content']=-1
    assert administrator.post('/api/rules',json=body).status_code==422
    assert len(administrator.get('/api/rules').json())==1

def test_empty_case_report(auth):
    c=auth.post('/api/cases',json={'title':'Caso vazio'}).json()
    assert auth.post(f"/api/cases/{c['id']}/reports").status_code==422

def test_body_limit(auth):
    assert auth.post('/api/discovery/import',content='x'*300001).status_code==413


def test_version_identifies_loaded_api(client):
    from app.build import BUILD_ID
    r=client.get('/api/version')
    assert r.status_code==200 and r.json()['build_id']==BUILD_ID
    assert r.json()['required_schema_revision']=='0005'
