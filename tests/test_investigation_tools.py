from datetime import timedelta
from sqlalchemy import select,func
from app.db import SessionLocal
from app.models import User,Domain,Analysis,Case,CaseDomain,Report,Audit,Evidence,now


def make_case(db):
    owner=db.scalar(select(User));domain=Domain(owner_id=owner.id,name='checklist.example.org')
    db.add(domain);db.flush();case=Case(owner_id=owner.id,title='Caso de teste de revisão')
    db.add(case);db.flush();db.add(CaseDomain(case_id=case.id,domain_id=domain.id));db.flush()
    return owner,domain,case


def test_checklist_reports_missing_records_and_preserves_case(auth):
    with SessionLocal() as db:
        _,domain,case=make_case(db);db.commit();identifier=case.id
    result=auth.get(f'/api/cases/{identifier}/checklist')
    assert result.status_code==200
    data=result.json();assert data['pending']==6
    assert data['checks'][0]['passed'] and not data['domains'][0]['analyzed']
    with SessionLocal() as db:assert db.get(Case,identifier).status=='open'


def test_checklist_uses_latest_analysis_not_old_review(auth):
    with SessionLocal() as db:
        _,domain,case=make_case(db)
        db.add(Analysis(domain_id=domain.id,score=25,classification='Requer investigação',review='Parecer anterior',result={'technical':{'collection_status':'complete'}},created=now()-timedelta(days=2)))
        db.flush()
        latest=Analysis(domain_id=domain.id,score=0,classification='Não verificada',review='',result={'technical':{'collection_status':'incomplete'}})
        db.add(latest);db.flush();db.add(Evidence(analysis_id=latest.id,sha256='a'*64,payload={'fixture':True}));db.commit();identifier=case.id
    data=auth.get(f'/api/cases/{identifier}/checklist').json()
    checks={r['key']:r['passed'] for r in data['checks']}
    assert checks['analyzed'] and checks['recent_24h'] and checks['evidence_preserved']
    assert not checks['human_review_recorded'] and not checks['collection_complete'] and not checks['regulatory_verified']


def test_notifications_acknowledgement_is_idempotent_and_does_not_hide_alert(auth):
    result=auth.get('/api/notifications').json()
    item=next(i for i in result['items'] if i['code']=='worker_stale')
    for _ in range(2):assert auth.post('/api/notifications/acknowledge',json={'notification_id':item['id']}).status_code==200
    again=auth.get('/api/notifications').json()
    assert next(i for i in again['items'] if i['id']==item['id'])['acknowledged']
    assert any(i['code']=='worker_stale' for i in auth.get('/api/operations/alerts').json()['items'])
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(Audit).where(Audit.action=='notification.ack'))==1
    assert auth.post('/api/notifications/acknowledge',json={'notification_id':'0'*64}).status_code==404


def test_notifications_and_checklists_are_owner_scoped(auth):
    with SessionLocal() as db:
        other=User(email='other-notification@example.org',password='unused',role='analyst');db.add(other);db.flush()
        case=Case(owner_id=other.id,title='Outro caso');db.add(case);db.flush()
        report=Report(case_id=case.id,sha256='b'*64,snapshot={},content=b'%PDF fixture');db.add(report);db.commit();identifier=case.id;report_id=report.id
    assert auth.get(f'/api/cases/{identifier}/checklist').status_code==404
    assert not any(i['code']==f'report_ready:{report_id}' for i in auth.get('/api/notifications').json()['items'])


def test_recent_pdf_notification_contains_no_document_bytes(auth):
    with SessionLocal() as db:
        _,_,case=make_case(db);report=Report(case_id=case.id,sha256='b'*64,snapshot={'private':'fixture'},content=b'%PDF fixture')
        db.add(report);db.commit();identifier=report.id
    data=auth.get('/api/notifications').json();item=next(i for i in data['items'] if i['code']==f'report_ready:{identifier}')
    assert item['link']=='/reports' and not item['acknowledged']
    assert 'snapshot' not in item and 'content' not in item


def test_checklist_rejects_changed_regulatory_context_and_future_collection(auth,monkeypatch):
    monkeypatch.setattr('app.regulation.context',lambda db:{'verified':True,'document_sha256':'current','version':'v2'})
    with SessionLocal() as db:
        _,domain,case=make_case(db)
        db.add(Analysis(domain_id=domain.id,score=25,classification='Requer investigação',created=now()+timedelta(days=1),result={'technical':{'collection_status':'complete'},'regulation':{'status':'restricted_framework','normative_context':{'verified':True,'document_sha256':'old','version':'v1'}}}));db.commit();identifier=case.id
    result=auth.get(f'/api/cases/{identifier}/checklist').json()['domains'][0]
    assert not result['regulatory_verified']
    assert not result['recent_24h']
    with SessionLocal() as db:
        analysis=db.scalar(select(Analysis));analysis.created=now()
        analysis.result={**analysis.result,'regulation':{'status':'restricted_framework','normative_context':{'verified':True,'document_sha256':'current','version':'v2'}}};db.commit()
    current=auth.get(f'/api/cases/{identifier}/checklist').json()['domains'][0]
    assert current['regulatory_verified'] and current['recent_24h']
