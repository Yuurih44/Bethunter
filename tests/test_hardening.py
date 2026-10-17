import asyncio,json,hashlib,re,sqlite3
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from sqlalchemy import select,func
from cryptography.fernet import Fernet,InvalidToken
from fastapi import HTTPException
from app.config import settings
from app.db import SessionLocal
from app.models import (User,Domain,Analysis,Case,CaseDomain,Report,ReportJob,EmailToken,MailJob,RawDocument,Session,SystemSchedule,Complaint,now)
from app.security import encryption,token_hash
from app.report_queue import queue_report,tick_reports
from app.mail import queue_token,tick_mail
from app.backups import create_backup,restore_backup

PASSWORD='secure-password-12345'
def account(db):return db.scalar(select(User))
def mail_token(db,purpose):
    message=db.scalar(select(MailJob).order_by(MailJob.id.desc()))
    payload=json.loads(encryption().decrypt(message.encrypted_message.encode()))
    return payload['body'].split('#'+purpose+'=',1)[1].split()[0]

@pytest.fixture
def local_mail(monkeypatch,tmp_path):
    monkeypatch.setattr(settings(),'smtp_mode','local')
    monkeypatch.setattr(settings(),'mail_capture_dir',str(tmp_path/'mail'))


def test_email_token_hash_expiry_and_one_use(auth,local_mail):
    assert auth.post('/api/auth/email/request').status_code==200
    with SessionLocal() as db:
        token=mail_token(db,'verify-email');row=db.scalar(select(EmailToken));assert row.token_hash==token_hash(token) and row.token_hash!=token
    assert auth.post('/api/auth/email/confirm',json={'token':token}).status_code==200
    assert auth.post('/api/auth/email/confirm',json={'token':token}).status_code==400
    with SessionLocal() as db:assert account(db).email_verified_mode=='local'


def test_expired_email_token_rejected(auth,local_mail):
    auth.post('/api/auth/email/request')
    with SessionLocal() as db:
        token=mail_token(db,'verify-email');db.scalar(select(EmailToken)).expires=now()-timedelta(seconds=1);db.commit()
    assert auth.post('/api/auth/email/confirm',json={'token':token}).status_code==400


def test_password_recovery_revokes_sessions_and_does_not_reuse_token(auth,local_mail):
    r=auth.post('/api/auth/password/request-reset',json={'email':'analyst@example.org'});assert r.status_code==200
    with SessionLocal() as db:token=mail_token(db,'reset-password')
    body={'token':token,'new_password':'a replacement exclusive phrase 54321'}
    assert auth.post('/api/auth/password/reset',json=body).status_code==200
    assert auth.get('/api/auth/me').status_code==401
    assert auth.post('/api/auth/password/reset',json=body).status_code==400
    assert auth.post('/api/auth/login',json={'email':'analyst@example.org','password':body['new_password']}).status_code==200


def test_mfa_not_bypassed_by_recovery_email(auth,local_mail):
    import pyotp
    secret=auth.post('/api/auth/mfa/setup',json={'password':PASSWORD}).json()['secret']
    r=auth.post('/api/auth/mfa/confirm',json={'code':pyotp.TOTP(secret).now()}).json()
    auth.headers['x-csrf-token']=r['user']['csrf']
    auth.post('/api/auth/password/request-reset',json={'email':'analyst@example.org'})
    with SessionLocal() as db:token=mail_token(db,'reset-password')
    body={'token':token,'new_password':'a replacement exclusive phrase 54321'}
    assert auth.post('/api/auth/password/reset',json=body).status_code==401
    assert auth.post('/api/auth/password/reset',json={**body,'recovery_code':r['recovery_codes'][0]}).status_code==200
    with SessionLocal() as db:assert account(db).mfa_enabled


def test_mail_worker_captures_honestly_and_removes_queued_secret(auth,local_mail,monkeypatch):
    auth.post('/api/auth/email/request');sent=[]
    monkeypatch.setattr('app.mail.send',lambda payload:sent.append(payload))
    assert asyncio.run(tick_mail())
    assert '#verify-email=' in sent[0]['body'] and 'LOCAL' in sent[0]['body']
    with SessionLocal() as db:
        job=db.scalar(select(MailJob));assert job.status=='captured_local' and job.encrypted_message==''


def test_verification_gate_and_local_proof_not_valid_for_real_smtp(auth,local_mail,monkeypatch):
    monkeypatch.setattr(settings(),'require_email_verification',True)
    assert auth.get('/api/dashboard').status_code==403
    assert auth.get('/api/auth/security').status_code==200
    auth.post('/api/auth/email/request')
    with SessionLocal() as db:token=mail_token(db,'verify-email')
    auth.post('/api/auth/email/confirm',json={'token':token});assert auth.get('/api/dashboard').status_code==200
    monkeypatch.setattr(settings(),'smtp_mode','smtp');assert auth.get('/api/dashboard').status_code==403
    assert auth.get('/api/auth/email/local-inbox').status_code==404


def test_inbox_only_own_messages(auth,local_mail,tmp_path):
    from email.message import EmailMessage
    directory=Path(settings().mail_capture_dir);directory.mkdir()
    for address in ['analyst@example.org','someone@example.org']:
        message=EmailMessage();message['To']=address;message['Subject']='Local fixture '+address;message.set_content('local-only fixture')
        (directory/(address+'.eml')).write_bytes(message.as_bytes())
    r=auth.get('/api/auth/email/local-inbox');assert r.status_code==200 and len(r.json()['items'])==1
    assert 'someone' not in str(r.json())


def test_inventory_pagination_and_server_side_filter(auth):
    with SessionLocal() as db:
        user=account(db)
        db.add_all([Domain(owner_id=user.id,name=f'domain{i:04}.example.org') for i in range(1005)]);db.commit()
    first=auth.get('/api/inventory?size=50&page=1').json();last=auth.get('/api/inventory?size=50&page=21').json()
    assert first['total']==1005 and len(last['items'])==5
    assert {d['id'] for d in first['items']}.isdisjoint(d['id'] for d in last['items'])
    assert auth.get('/api/inventory?q=domain0000').json()['total']==1
    assert auth.get('/api/inventory?priority=pending').json()['total']==1005
    assert auth.get('/api/inventory?size=201').status_code==422


def test_paged_results_are_isolated(auth):
    with SessionLocal() as db:
        other=User(email='other@example.org',password='fixture-only');db.add(other);db.flush();db.add(Domain(owner_id=other.id,name='secret.example.org'));db.commit()
    assert auth.get('/api/pages/domains').json()['total']==0
    assert auth.get('/api/inventory').json()['total']==0


def make_case(db,user):
    d=Domain(owner_id=user.id,name='example.org');db.add(d);db.flush()
    case=Case(owner_id=user.id,title='Fixture investigation');db.add(case);db.flush();db.add(CaseDomain(case_id=case.id,domain_id=d.id));db.flush();return case


def test_report_queue_deduplicates_and_renders_valid_pdf(auth):
    with SessionLocal() as db:
        user=account(db);case=make_case(db,user)
        one=queue_report(db,case,user.id);db.commit();two=queue_report(db,case,user.id);db.commit()
        assert one.id==two.id
    assert asyncio.run(tick_reports())
    with SessionLocal() as db:
        job=db.scalar(select(ReportJob));assert job.status=='done',job.error
        report=db.get(Report,job.report_id);assert report.content.startswith(b'%PDF')
        assert hashlib.sha256(report.content).hexdigest()==report.sha256


def test_report_limits_and_queue_failure_visible(auth,monkeypatch):
    monkeypatch.setattr(settings(),'report_max_snapshot_bytes',30)
    with SessionLocal() as db:
        user=account(db);case=make_case(db,user)
        with pytest.raises(HTTPException):queue_report(db,case,user.id)
        db.rollback()
    monkeypatch.setattr(settings(),'report_max_snapshot_bytes',2_000_000)
    with SessionLocal() as db:
        user=account(db);case=make_case(db,user);queue_report(db,case,user.id);db.commit()
    def fail(_):raise TimeoutError('test-only render timeout')
    monkeypatch.setattr('app.report_queue.render',fail)
    assert asyncio.run(tick_reports())
    assert auth.get('/api/pages/report-jobs').json()['items'][0]['status']=='failed'


def test_backup_restore_preserves_sqlite_rows_and_mfa_key(tmp_path,monkeypatch):
    source=tmp_path/'source.db';restored=tmp_path/'restored.db';keyfile=tmp_path/'auth.env'
    with sqlite3.connect(source) as db:db.execute('CREATE TABLE samples (id INTEGER PRIMARY KEY, payload TEXT)');db.execute('INSERT INTO samples VALUES (1,?)',('fixture integrity',))
    monkeypatch.setattr(settings(),'backup_encryption_key',Fernet.generate_key().decode())
    monkeypatch.setattr(settings(),'backup_dir',str(tmp_path/'backups'))
    backup=create_backup('sqlite:///'+str(source));cipher=Path(backup['file']).read_bytes()
    assert b'fixture integrity' not in cipher
    result=restore_backup(backup['file'],'sqlite:///'+str(restored),keyfile)
    assert result['ok']
    with sqlite3.connect(restored) as db:assert db.execute('SELECT payload FROM samples').fetchone()[0]=='fixture integrity'
    assert keyfile.read_text().strip()=='AUTH_ENCRYPTION_KEY='+settings().auth_encryption_key
    assert keyfile.stat().st_mode&0o777==0o600
    with pytest.raises(RuntimeError):restore_backup(backup['file'],'sqlite:///'+str(restored),tmp_path/'second.env')
    monkeypatch.setattr(settings(),'backup_encryption_key',Fernet.generate_key().decode())
    with pytest.raises(InvalidToken):restore_backup(backup['file'],'sqlite:///'+str(tmp_path/'wrong.db'),tmp_path/'wrong.env')


def test_raw_html_is_preserved_and_download_hash_matches(auth,monkeypatch):
    raw=b'<article>Noticia sobre cassino e apostas</article>'
    monkeypatch.setattr('app.network.resolve',AsyncMock(return_value=['93.184.216.34']))
    monkeypatch.setattr('app.network.certificate',AsyncMock(return_value={}))
    monkeypatch.setattr('app.network.fetch',AsyncMock(return_value=(raw,[{'url':'https://example.org','status':200}],{'content-type':'text/html'})))
    did=auth.post('/api/domains',json={'value':'example.org'}).json()['id']
    analysis=auth.post(f'/api/domains/{did}/analyze').json()
    assert analysis['score']==0 and analysis['result']['verdict']['code']=='activity_unconfirmed'
    document=auth.get('/api/evidence/documents/'+str(analysis['result']['raw_document_ids'][0]))
    assert document.content==raw and document.headers['x-evidence-sha256']==hashlib.sha256(raw).hexdigest()
    assert document.headers['content-type']=='application/octet-stream'


def test_polling_does_not_extend_idle_session(auth):
    original=now()-timedelta(minutes=5)
    with SessionLocal() as db:db.scalar(select(Session)).last_seen=original;db.commit()
    assert auth.get('/api/dashboard').status_code==200
    with SessionLocal() as db:assert db.scalar(select(Session)).last_seen.replace(tzinfo=now().tzinfo)==original
    assert auth.post('/api/auth/activity').status_code==200
    with SessionLocal() as db:assert db.scalar(select(Session)).last_seen.replace(tzinfo=now().tzinfo)>original


def test_operational_alerts_are_real(auth):
    items=auth.get('/api/operations/alerts').json()['items']
    assert any(item['code']=='worker_stale' for item in items)
    with SessionLocal() as db:db.add(SystemSchedule(key='worker_heartbeat',next_run=now()+timedelta(minutes=5),details={}));db.commit()
    assert not any(item['code']=='worker_stale' for item in auth.get('/api/operations/alerts').json()['items'])


def test_local_tokens_cannot_be_used_after_switch_to_real_smtp(auth,local_mail,monkeypatch):
    auth.post('/api/auth/email/request')
    with SessionLocal() as db:token=mail_token(db,'verify-email')
    monkeypatch.setattr(settings(),'smtp_mode','smtp')
    assert auth.post('/api/auth/email/confirm',json={'token':token}).status_code==400


def test_retention_requires_backup_and_preserves_confirmed_reports(auth,monkeypatch,tmp_path):
    from app.maintenance import tick_maintenance
    monkeypatch.setattr(settings(),'report_retention_enabled',True)
    monkeypatch.setattr(settings(),'report_minimum_keep',1)
    with SessionLocal() as db:
        user=account(db);case=make_case(db,user)
        for i in range(4):
            report=Report(case_id=case.id,sha256='f'*64,snapshot={'fixture':True},content=b'%PDF fixture',created=now()-timedelta(days=200-i));db.add(report);db.flush()
            db.add(Complaint(report_id=report.id,status='confirmed_by_analyst' if i==0 else 'prepared'))
        db.commit()
    assert asyncio.run(tick_maintenance())
    with SessionLocal() as db:
        assert not any(r.archived for r in db.scalars(select(Report)))
        backup_file=tmp_path/'fixture.bhbackup';backup_file.write_bytes(b'explicit synthetic backup fixture')
        db.add(SystemSchedule(key='backup',details={'status':'complete','created':now().isoformat(),'file':str(backup_file),'sha256':hashlib.sha256(backup_file.read_bytes()).hexdigest()},next_run=now()+timedelta(days=1)))
        db.get(SystemSchedule,'maintenance').next_run=now()-timedelta(seconds=1);db.commit()
    asyncio.run(tick_maintenance())
    with SessionLocal() as db:
        rows=db.scalars(select(Report).order_by(Report.id)).all()
        assert not rows[0].archived and not rows[-1].archived
        assert rows[1].archived and rows[2].archived
        assert rows[1].sha256=='f'*64 and rows[1].snapshot=={'fixture':True}
    assert auth.get(f'/api/reports/{rows[1].id}/pdf').status_code==410


def test_proxy_header_is_ignored_without_trusted_peer(auth,monkeypatch):
    from app.models import SecurityEvent
    monkeypatch.setattr(settings(),'trusted_proxy_ips','')
    auth.post('/api/auth/login',json={'email':'analyst@example.org','password':'wrong'},headers={'x-real-ip':'203.0.113.7'})
    with SessionLocal() as db:assert db.scalar(select(SecurityEvent)).peer!='203.0.113.7'


def test_local_smtp_protocol_captures_without_forwarding(tmp_path):
    from app.maildev import connection
    class Writer:
        def __init__(self):self.replies=bytearray()
        def write(self,data):self.replies.extend(data)
        async def drain(self):pass
        def close(self):pass
        async def wait_closed(self):pass
    async def run():
        reader=asyncio.StreamReader();writer=Writer()
        reader.feed_data(b'EHLO localhost\r\nMAIL FROM:<sender@example.org>\r\nRCPT TO:<analyst@example.org>\r\nDATA\r\nTo: analyst@example.org\r\nSubject: Local SMTP test\r\n\r\nFixture body\r\n.\r\nQUIT\r\n');reader.feed_eof()
        await connection(reader,writer,tmp_path)
        assert b'NOT DELIVERED TO INTERNET' in writer.replies
    asyncio.run(run())
    files=list(tmp_path.glob('*.eml'));assert len(files)==1 and b'Fixture body' in files[0].read_bytes()
    assert files[0].stat().st_mode&0o777==0o600


def test_restore_validates_mfa_and_document_integrity(tmp_path,monkeypatch):
    source=tmp_path/'source.db';secret=__import__('pyotp').random_base32()
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE users (id INTEGER PRIMARY KEY,mfa_secret TEXT,mfa_enabled BOOLEAN)')
        db.execute('INSERT INTO users VALUES (1,?,true)',(encryption().encrypt(secret.encode()).decode(),))
        db.execute('CREATE TABLE raw_documents (id INTEGER PRIMARY KEY,content BLOB,sha256 TEXT)')
        db.execute('INSERT INTO raw_documents VALUES (1,?,?)',(b'fixture evidence',hashlib.sha256(b'fixture evidence').hexdigest()))
    monkeypatch.setattr(settings(),'backup_encryption_key',Fernet.generate_key().decode());monkeypatch.setattr(settings(),'backup_dir',str(tmp_path/'backups'))
    backup=create_backup('sqlite:///'+str(source));target='sqlite:///'+str(tmp_path/'restored.db')
    restore_backup(backup['file'],target,tmp_path/'key.env')
    from app.backups import validate_restore
    assert validate_restore(target,settings().auth_encryption_key)=={'documents':1,'reports':0,'mfa':1}


def test_report_discard_and_retry_do_not_delete_evidence(auth,monkeypatch):
    with SessionLocal() as db:
        user=account(db);case=make_case(db,user);job=queue_report(db,case,user.id);job.status='failed';db.commit();identifier=job.id
    assert auth.post(f'/api/report-jobs/{identifier}/discard').status_code==200
    with SessionLocal() as db:
        assert db.get(ReportJob,identifier).snapshot=={}
        case=db.scalar(select(Case));new=queue_report(db,case,case.owner_id);db.commit()
        assert new.id==identifier and new.status=='queued'
    assert auth.post(f'/api/report-jobs/{identifier}/discard').status_code==409


def test_master_pause_stops_automatic_pdf_but_manual_request_still_runs(auth):
    from app.models import WorkflowPolicy
    with SessionLocal() as db:
        user=account(db);case=make_case(db,user);job=queue_report(db,case,user.id,automatic=True);db.add(WorkflowPolicy(owner_id=user.id,enabled=False));db.commit()
    assert not asyncio.run(tick_reports())
    with SessionLocal() as db:
        case=db.scalar(select(Case));queue_report(db,case,case.owner_id,automatic=False);db.commit()
    assert asyncio.run(tick_reports())
    with SessionLocal() as db:
        jobs=db.scalars(select(ReportJob).order_by(ReportJob.id)).all()
        assert jobs[0].status=='queued' and jobs[1].status=='done'


def test_archived_report_can_be_regenerated(auth):
    with SessionLocal() as db:
        user=account(db);case=make_case(db,user);job=queue_report(db,case,user.id);db.commit();identifier=job.id
    assert asyncio.run(tick_reports())
    with SessionLocal() as db:
        job=db.get(ReportJob,identifier);report=db.get(Report,job.report_id)
        old_report_id=report.id;report.archived=True;report.content=b'';db.commit()
        case=db.scalar(select(Case));replacement=queue_report(db,case,case.owner_id)
        assert replacement.id==identifier and replacement.status=='queued' and replacement.report_id is None
        db.commit()
    assert asyncio.run(tick_reports())
    with SessionLocal() as db:
        assert db.get(ReportJob,identifier).report_id!=old_report_id
        assert db.get(Report,old_report_id).archived


def test_manual_pdf_generation_without_worker_and_download(auth):
    with SessionLocal() as db:
        user=account(db);case=make_case(db,user);job=queue_report(db,case,user.id);db.commit();identifier=job.id
    response=auth.post(f'/api/report-jobs/{identifier}/generate')
    assert response.status_code==200,response.text
    result=response.json();assert result['status']=='done',result
    document=auth.get(f"/api/reports/{result['report_id']}/pdf")
    assert document.status_code==200 and document.content.startswith(b'%PDF')
    assert auth.post(f'/api/report-jobs/{identifier}/generate').json()['report_id']==result['report_id']


def test_manual_generation_is_owner_scoped(auth):
    with SessionLocal() as db:
        other=User(email='pdf-other@example.org',password='unused',role='analyst');db.add(other);db.flush()
        case=make_case(db,other);job=queue_report(db,case,other.id);db.commit();identifier=job.id
    assert auth.post(f'/api/report-jobs/{identifier}/generate').status_code==404
    with SessionLocal() as db:assert db.get(ReportJob,identifier).status=='queued'


def test_continuous_profile_updates_existing_settings_and_is_idempotent(auth):
    from app.models import WorkflowPolicy,DiscoveryFeed,Audit
    from app.automation import CATALOG
    with SessionLocal() as db:
        user=account(db);db.add(WorkflowPolicy(owner_id=user.id,enabled=False,minimum_score=50))
        source=CATALOG[0];db.add(DiscoveryFeed(owner_id=user.id,name=source['name'],url=source['url'],format=source['format'],permission_reference=source['permission_reference'],interval_hours=24,batch_size=50,enabled=False));db.commit()
    assert auth.post('/api/automation/continuous').status_code==200
    assert auth.post('/api/automation/continuous').status_code==200
    result=auth.get('/api/automation/diagnostics').json()
    assert result['enabled'] and result['minimum_score']==25
    assert len(result['feeds'])==1 and result['feeds'][0]['interval_hours']==1 and result['feeds'][0]['batch_size']==100
    assert not result['worker_healthy']


def test_continuous_profile_respects_server_source_allowlist(auth,monkeypatch):
    monkeypatch.setattr(settings(),'discovery_allowed_hosts','none.example.org')
    assert auth.post('/api/automation/continuous').status_code==422


def test_default_workflow_creates_pdf_job_for_operator_score_25(auth):
    from app.collection import persist_analysis
    from app.models import WorkflowRun
    with SessionLocal() as db:
        user=account(db);domain=Domain(owner_id=user.id,name='operator-fixture.example.org');db.add(domain);db.flush()
        result={'score':25,'classification':'Requer investigação','technical':{'ips':['1.1.1.1'],'matched_terms':['apostar agora']},'verdict':{'code':'requires_investigation'},'errors':[]}
        analysis=persist_analysis(db,domain,result,user.id);db.commit()
        run=db.get(WorkflowRun,analysis.id)
        assert run.case_id and run.details.get('report_job_id')
        assert db.get(ReportJob,run.details['report_job_id']).status=='queued'


def test_report_snapshot_changes_when_tls_or_old_review_changes(auth):
    from app.report_queue import snapshot_for
    with SessionLocal() as db:
        user=account(db);case=make_case(db,user);domain=db.scalar(select(Domain))
        older=Analysis(domain_id=domain.id,score=0,classification='Requer investigação',review='Parecer inicial',result={})
        latest=Analysis(domain_id=domain.id,score=25,classification='Requer investigação',result={'technical':{'ips':['1.1.1.1'],'tls':{'notAfter':'2027-01-01'}},'regulation':{'status':'not_verified'}})
        db.add_all([older,latest]);db.flush()
        _,before=snapshot_for(db,case,False)
        latest.result={**latest.result,'technical':{**latest.result['technical'],'tls':{'notAfter':'2028-01-01'}}};db.flush()
        _,after_tls=snapshot_for(db,case,False)
        assert before!=after_tls
        older.review='Parecer anterior corrigido';db.flush()
        _,after_review=snapshot_for(db,case,False)
        assert after_review!=after_tls


def test_retention_does_not_archive_when_recorded_backup_file_is_missing(auth,monkeypatch,tmp_path):
    from app.maintenance import tick_maintenance
    monkeypatch.setattr(settings(),'report_retention_enabled',True)
    monkeypatch.setattr(settings(),'report_minimum_keep',1)
    with SessionLocal() as db:
        user=account(db);case=make_case(db,user)
        for i in range(2):
            report=Report(case_id=case.id,sha256='f'*64,snapshot={},content=b'%PDF fixture',created=now()-timedelta(days=200-i));db.add(report);db.flush();db.add(Complaint(report_id=report.id,status='prepared'))
        db.add(SystemSchedule(key='backup',details={'status':'complete','created':now().isoformat(),'file':str(tmp_path/'missing.bhbackup'),'sha256':'a'*64}));db.commit()
    assert asyncio.run(tick_maintenance())
    with SessionLocal() as db:assert not any(report.archived for report in db.scalars(select(Report)))


def test_backup_integrity_and_expiry_guard(tmp_path):
    from app.backups import recent_backup_usable
    file=tmp_path/'fixture.bhbackup';file.write_bytes(b'explicit synthetic fixture')
    details={'status':'complete','created':now().isoformat(),'file':str(file),'sha256':hashlib.sha256(file.read_bytes()).hexdigest()}
    assert recent_backup_usable(details,verify_contents=True)
    file.write_bytes(b'changed fixture');assert not recent_backup_usable(details,verify_contents=True)
    details['created']=(now()-timedelta(hours=49)).isoformat();assert not recent_backup_usable(details)
