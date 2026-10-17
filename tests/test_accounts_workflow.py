from datetime import timedelta
from unittest.mock import AsyncMock
import asyncio
import pytest
import pyotp
from sqlalchemy import select,func
from app.config import settings,Settings
from app.db import SessionLocal
from app.models import (User,Invitation,Session,MfaRecovery,RegulatoryNotice,Domain,Analysis,Schedule,Case,Report,Complaint,WorkflowRun,now)
from app.security import token_hash,buckets
from app.regulation import parse_notice,context,verdict,sync_notice
from app.collection import persist_analysis

PASSWORD='secure-password-12345'
def test_invite_registration_required(client,monkeypatch):
    monkeypatch.setattr(settings(),'registration_mode','invite')
    assert client.post('/api/auth/register',json={'email':'new@example.org','password':PASSWORD}).status_code==403

def make_invitation(email='new@example.org',**kw):
    with SessionLocal() as db:
        admin=User(email='admin@example.org',password='unused',role='admin');db.add(admin);db.flush()
        invite=Invitation(token_hash=token_hash('private-invite'),email=email,role='viewer',issuer_id=admin.id,expires=now()+timedelta(hours=1),**kw);db.add(invite);db.commit()

def test_invite_bound_email_and_one_use(client,monkeypatch):
    monkeypatch.setattr(settings(),'registration_mode','invite');make_invitation()
    payload={'email':'wrong@example.org','password':PASSWORD,'invitation':'private-invite'}
    assert client.post('/api/auth/register',json=payload).status_code==403
    payload['email']='new@example.org'
    r=client.post('/api/auth/register',json=payload);assert r.status_code==201,r.text
    assert r.json()['role']=='viewer'
    assert client.post('/api/auth/register',json=payload).status_code in (403,409)
    with SessionLocal() as db:
        i=db.scalar(select(Invitation));assert i.used_at and i.token_hash!='private-invite'

@pytest.mark.parametrize('revoked',[True,False])
def test_revoked_expired_invite(client,monkeypatch,revoked):
    monkeypatch.setattr(settings(),'registration_mode','invite');make_invitation(revoked=revoked)
    if not revoked:
        with SessionLocal() as db:db.scalar(select(Invitation)).expires=now()-timedelta(seconds=1);db.commit()
    assert client.post('/api/auth/register',json={'email':'new@example.org','password':PASSWORD,'invitation':'private-invite'}).status_code==403

@pytest.mark.parametrize('password',['short','123456789012345','passwordpassword','aaaaaaaaaaaaaaaaaaaa'])
def test_weak_password(client,password):
    assert client.post('/api/auth/register',json={'email':'new@example.org','password':password}).status_code==422

def enable_mfa(auth):
    r=auth.post('/api/auth/mfa/setup',json={'password':PASSWORD});assert r.status_code==200,r.text
    secret=r.json()['secret']
    r=auth.post('/api/auth/mfa/confirm',json={'code':pyotp.TOTP(secret).now()});assert r.status_code==200,r.text
    auth.headers['x-csrf-token']=r.json()['user']['csrf']
    return secret,r.json()['recovery_codes']

def test_mfa_encrypted_and_replay_recovery_one_use(auth):
    secret,codes=enable_mfa(auth)
    assert len(codes)==8
    with SessionLocal() as db:
        user=db.scalar(select(User));assert user.mfa_enabled and user.mfa_secret!=secret
        assert db.scalar(select(func.count()).select_from(MfaRecovery))==8
    assert auth.post('/api/auth/login',json={'email':'analyst@example.org','password':PASSWORD}).status_code==401
    assert auth.post('/api/auth/login',json={'email':'analyst@example.org','password':PASSWORD,'otp_code':pyotp.TOTP(secret).now()}).status_code==401
    r=auth.post('/api/auth/login',json={'email':'analyst@example.org','password':PASSWORD,'recovery_code':codes[0]});assert r.status_code==200
    assert auth.post('/api/auth/login',json={'email':'analyst@example.org','password':PASSWORD,'recovery_code':codes[0]}).status_code==401

def test_mfa_disable_revokes_sessions(auth):
    _,codes=enable_mfa(auth)
    r=auth.post('/api/auth/mfa/disable',json={'password':PASSWORD,'recovery_code':codes[0]});assert r.status_code==200
    assert auth.get('/api/auth/me').status_code==401
    with SessionLocal() as db:
        assert not db.scalar(select(User)).mfa_enabled
        assert db.scalar(select(func.count()).select_from(Session))==0

def test_password_rotation_and_old_password(auth):
    r=auth.post('/api/auth/password',json={'password':PASSWORD,'new_password':'a new exclusive password phrase 987'});assert r.status_code==200,r.text
    assert auth.post('/api/auth/login',json={'email':'analyst@example.org','password':PASSWORD}).status_code==401
    assert auth.post('/api/auth/login',json={'email':'analyst@example.org','password':'a new exclusive password phrase 987'}).status_code==200

def test_idle_and_disabled_sessions(auth):
    with SessionLocal() as db:db.scalar(select(Session)).last_seen=now()-timedelta(minutes=31);db.commit()
    assert auth.get('/api/auth/me').status_code==401
    r=auth.post('/api/auth/login',json={'email':'analyst@example.org','password':PASSWORD});assert r.status_code==200
    with SessionLocal() as db:db.scalar(select(User)).active=False;db.commit()
    assert auth.get('/api/auth/me').status_code==401

def test_bruteforce_survives_memory_reset(client):
    for _ in range(5):
        buckets.clear();assert client.post('/api/auth/login',json={'email':'absent@example.org','password':'wrong'}).status_code==401
    buckets.clear()
    assert client.post('/api/auth/login',json={'email':'absent@example.org','password':'wrong'}).status_code==429

def test_admin_requires_mfa(auth):
    with SessionLocal() as db:db.scalar(select(User)).role='admin';db.commit()
    assert auth.get('/api/security/invitations').status_code==403
    _,codes=enable_mfa(auth)
    r=auth.post('/api/security/invitations',json={'email':'invited@example.org','password':PASSWORD,'recovery_code':codes[0]});assert r.status_code==201,r.text
    assert r.json()['token']
    listing=auth.get('/api/security/invitations');assert listing.status_code==200 and 'token' not in listing.json()[0]

def test_host_header_rejected(client):
    assert client.get('/api/health',headers={'host':'untrusted.example'}).status_code==400

def test_external_http_rejected():
    with pytest.raises(ValueError):Settings(origin='http://public.example',cookie_secure=False)
    with pytest.raises(ValueError):Settings(auth_encryption_key='invalid')

NOTICE='<h3>A Medida Provisória nº 1.394/2026 proibiu as apostas de quota fixa no território nacional.</h3>'.encode()
def add_notice(db,**kw):
    row=RegulatoryNotice(url='https://www.gov.br/',status='official_restriction_notice',version='test-only',effective_from=now()-timedelta(days=1),details={'fixture':True},**kw);db.add(row);db.commit();return row

def test_notice_parser_conservative():
    assert parse_notice(NOTICE)['version']=='spa-alert-mp1394-2026-v1'
    with pytest.raises(ValueError):parse_notice(b'<p>unrecognized source</p>')

def test_latest_failed_or_stale_notice_blocks_verdict():
    with SessionLocal() as db:
        row=add_notice(db);assert context(db)['verified']
        row.consulted=now()-timedelta(hours=25);db.commit();assert not context(db)['verified']
        row.consulted=now();db.commit()
        db.add(RegulatoryNotice(url=row.url,status='failed',details={},error='offline'));db.commit();assert not context(db)['verified']

def test_verdict_never_determines_crime():
    r=verdict({'normative_context':{'verified':True,'kind':'official_restriction_notice'}},{'matched_terms':['apostas']})
    assert r['code']=='possible_noncompliance' and not r['crime_determined'] and r['requires_human_review']
    assert verdict({'status':'listed'},{})['code']=='historical_match'
    assert verdict({'status':'not_found'},{})['code']=='not_located'

def test_notice_failure_recorded(monkeypatch):
    monkeypatch.setattr('app.network.fetch',AsyncMock(side_effect=ValueError('offline')))
    with SessionLocal() as db:
        row=asyncio.run(sync_notice(db));assert row.status=='failed' and 'offline' in row.error
        assert not context(db)['verified']

RESULT={'score':75,'classification':'Suspeito','technical':{'ips':['93.184.216.34']},'factors':[],'regulation':{'status':'not_verified'},'errors':[],'limitations':[],'rule_version':'test-only'}
def collect(db,domain):
    a=persist_analysis(db,domain,RESULT,domain.owner_id);db.commit();return a

def test_workflow_case_report_monitor_idempotent(auth):
    from app.workflow import apply_workflow
    with SessionLocal() as db:
        u=db.scalar(select(User));d=Domain(owner_id=u.id,name='example.org');db.add(d);db.flush()
        a=collect(db,d)
        run=db.get(WorkflowRun,a.id);assert run.details['status']=='applied',run.details
        from app.report_queue import tick_reports
        assert run.case_id and not run.report_id
        assert asyncio.run(tick_reports())
        db.expire_all();run=db.get(WorkflowRun,a.id)
        assert run.report_id
        assert db.scalar(select(Schedule)).automatic
        report=db.get(Report,run.report_id);assert report.content.startswith(b'%PDF')
        assert report.snapshot['Preparação']=='Rascunho automático para revisão humana'
        assert db.scalar(select(Complaint)).status=='prepared'
        apply_workflow(db,d,a,u.id);db.commit()
        assert db.scalar(select(func.count()).select_from(Report))==1
        case=db.get(Case,run.case_id);case.status='closed';db.commit()
        second=collect(db,d);assert db.get(WorkflowRun,second.id).details['status']=='skipped_closed'
        assert db.scalar(select(func.count()).select_from(Case))==1
    history=auth.get('/api/automation/history');assert len(history.json())==2

def test_workflow_disable_and_validation(auth):
    assert auth.put('/api/automation/workflow',json={'create_cases':False,'prepare_reports':True}).status_code==422
    assert auth.put('/api/automation/workflow',json={'enabled':False}).status_code==200
    with SessionLocal() as db:
        u=db.scalar(select(User));d=Domain(owner_id=u.id,name='example.org');db.add(d);db.flush();a=collect(db,d)
        assert db.get(WorkflowRun,a.id).details['status']=='disabled'
        assert not db.scalar(select(Schedule)) and not db.scalar(select(Case))

def test_workflow_failure_preserves_analysis(auth,monkeypatch):
    def fail(*args):raise ValueError('test-only failure')
    monkeypatch.setattr('app.workflow.apply_workflow',fail)
    with SessionLocal() as db:
        u=db.scalar(select(User));d=Domain(owner_id=u.id,name='example.org');db.add(d);db.flush();a=collect(db,d)
        assert db.get(Analysis,a.id) and db.get(WorkflowRun,a.id).details['status']=='failed'

def test_totp_accepts_new_interval_and_rejects_reuse(auth,monkeypatch):
    secret,_=enable_mfa(auth)
    later=now()+timedelta(seconds=60)
    monkeypatch.setattr('app.security.now',lambda:later)
    payload={'email':'analyst@example.org','password':PASSWORD,'otp_code':pyotp.TOTP(secret).at(later)}
    assert auth.post('/api/auth/login',json=payload).status_code==200
    assert auth.post('/api/auth/login',json=payload).status_code==401

def test_workflow_pdf_failure_rolls_back_draft_only(auth,monkeypatch):
    def fail(snapshot):raise RuntimeError('PDF test-only failure')
    monkeypatch.setattr('app.report_queue.render',fail)
    with SessionLocal() as db:
        u=db.scalar(select(User));d=Domain(owner_id=u.id,name='example.org');db.add(d);db.flush();a=collect(db,d)
        from app.report_queue import tick_reports
        from app.models import ReportJob
        assert asyncio.run(tick_reports())
        db.expire_all()
        assert db.get(Analysis,a.id) and db.get(WorkflowRun,a.id).details['status']=='applied'
        assert db.scalar(select(Case)) and not db.scalar(select(Report))
        assert db.scalar(select(ReportJob)).status=='failed'

def test_workflow_history_tenant_isolation(auth):
    with SessionLocal() as db:
        other=User(email='other@example.org',password='test-only');db.add(other);db.flush()
        d=Domain(owner_id=other.id,name='other.example.org');db.add(d);db.flush();collect(db,d)
    assert auth.get('/api/automation/history').json()==[]

def test_notice_sync_success_records_provenance(monkeypatch):
    monkeypatch.setattr('app.network.fetch',AsyncMock(return_value=(NOTICE,[],{})))
    with SessionLocal() as db:
        row=asyncio.run(sync_notice(db));assert row.status=='official_restriction_notice'
        assert len(row.sha256)==64 and row.details['act_url'].startswith('https://www.planalto.gov.br/')
