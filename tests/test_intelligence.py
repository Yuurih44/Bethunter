import asyncio
from datetime import timedelta
from app.db import SessionLocal
from app.models import OfficialSource, now
from app.intelligence import score,parse_source,regulatory,analyze,LABELS
from app.reports import pdf
import pytest
from unittest.mock import AsyncMock

def test_score_explained_and_capped():
    assert score([{'key':'one'},{'key':'two'}],{'one':80,'two':70})==100
    assert score([{'key':'unknown'}],{})==0

def test_parse_official():
    html=b'<span class="documentModified"><span class="value">17/10/2026</span></span><table><tr><td>1</td><td>EMPRESA</td><td>CNPJ</td><td>MARCA</td><td>foo.bet.br</td><td>Portaria 123</td></tr></table>'
    entries,updated=parse_source(html)
    assert entries[0]['domain']=='foo.bet.br' and entries[0]['act']=='Portaria 123'
    assert updated.year==2026
    with pytest.raises(ValueError):parse_source(b'<html>changed</html>')

def test_stale_or_failed_source_never_authorizes(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings(),'regulatory_require_context',False)
    with SessionLocal() as db:
        assert regulatory(db,'foo.bet.br')['status']=='not_verified'
        s=OfficialSource(url='https://www.gov.br/',status='imported',document_updated=now()-timedelta(days=40),entries=[{'domain':'foo.bet.br'}])
        db.add(s);db.commit()
        assert regulatory(db,'foo.bet.br')['status']=='not_verified'
        s.document_updated=now();db.commit()
        assert regulatory(db,'foo.bet.br')['status']=='listed'
        assert regulatory(db,'absent.bet.br')['status']=='not_found'
        db.add(OfficialSource(url=s.url,status='failed',error='offline',entries=[]));db.commit()
        assert regulatory(db,'foo.bet.br')['status']=='not_verified'

def test_analysis_real_engine_mocked_collectors(monkeypatch):
    monkeypatch.setattr('app.network.resolve',AsyncMock(return_value=['93.184.216.34']))
    monkeypatch.setattr('app.network.certificate',AsyncMock(return_value={'issuer':'test'}))
    monkeypatch.setattr('app.network.fetch',AsyncMock(return_value=(b'<p>cassino e apostas</p>',[{'url':'https://example.org','status':200,'ip':'93.184.216.34'}],{})))
    with SessionLocal() as db:
        r=asyncio.run(analyze(db,'example.org'))
    assert r['score']==10 and r['classification']==LABELS[4]
    assert r['technical']['matched_terms']==['cassino','apostas']
    assert r['factors'][0]['weight']==10

def test_collection_failure_is_explicit(monkeypatch):
    monkeypatch.setattr('app.network.resolve',AsyncMock(side_effect=ValueError('private DNS')))
    with SessionLocal() as db:r=asyncio.run(analyze(db,'example.org'))
    assert r['errors'] and r['classification']==LABELS[4] and r['score']==0

def test_pdf_escapes_user_html_and_no_fetch(monkeypatch):
    fetched=[]
    def fetch(*args,**kw):fetched.append(args);raise AssertionError('external fetch')
    monkeypatch.setattr('app.reports.deny_resources',fetch)
    result=pdf({'Caso':'<img src="http://127.0.0.1/secret"> & revisão técnica'})
    assert result.startswith(b'%PDF') and len(result)>1000 and not fetched

def test_asn_adapter_with_mock(monkeypatch):
    import json
    from app.providers import RIPEstatProvider
    async def fake(url):
        data={'asns':[64500],'prefix':'93.184.216.0/24'} if 'network-info' in url else {'asns':[{'asn':64500,'holder':'DEMONSTRAÇÃO SOMENTE NO TESTE'}]}
        return json.dumps({'status':'ok','data':data}).encode(),[],{}
    monkeypatch.setattr('app.network.fetch',fake)
    r=asyncio.run(RIPEstatProvider().lookup('93.184.216.34'))
    assert r['asns']==[64500] and r['holders'][0]['asn']==64500
    assert len(r['source_sha256'])==64

def test_new_rule_does_not_rewrite_previous_results():
    from app.models import Rule
    from app.intelligence import current_rule
    with SessionLocal() as db:
        db.add(Rule(version='old',effective_from=now()-timedelta(days=2),config={'weights':{'betting_content':20,'cross_domain_redirect':10}}))
        db.add(Rule(version='future',effective_from=now()+timedelta(days=2),config={'weights':{'betting_content':100,'cross_domain_redirect':100}}))
        db.commit()
        assert current_rule(db).version=='old'

def test_future_document_not_verified():
    with SessionLocal() as db:
        db.add(OfficialSource(url='https://www.gov.br/',status='imported',document_updated=now()+timedelta(days=1),entries=[{'domain':'foo.bet.br'}]));db.commit()
        assert regulatory(db,'foo.bet.br')['status']=='not_verified'
