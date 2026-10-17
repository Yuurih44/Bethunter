"""Time-bounded official regulatory context, never a machine finding of crime."""
import asyncio
import hashlib
import re
import unicodedata
from datetime import datetime,timedelta,timezone
from bs4 import BeautifulSoup
from sqlalchemy import select
from . import network
from .config import settings
from .models import RegulatoryNotice,SystemSchedule,OfficialSource,now

SPA_URL='https://www.gov.br/fazenda/pt-br/composicao/orgaos/secretaria-de-premios-e-apostas'
MP_URL='https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2026/mpv/mpv1394.htm'
HISTORICAL_LIST_URL=SPA_URL+'/transparencia-ativa-processos-de-autorizacao-de-apostas-de-quota-fixa/empresas-autorizadas'


def plain(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',value.lower()) if not unicodedata.combining(c))


def parse_notice(raw):
    soup=BeautifulSoup(raw,'html.parser')
    for heading in soup.select('h2,h3,.portalMessage'):
        text=heading.get_text(' ',strip=True)
        normalized=plain(text)
        if re.search(r'1[.\s]?394',normalized) and '2026' in normalized and 'proibiu' in normalized and 'apostas de quota fixa' in normalized:
            return {'version':'spa-alert-mp1394-2026-v1','effective_from':datetime(2026,9,25,tzinfo=timezone.utc),
                'excerpt':text[:1200],'act_url':MP_URL,
                'scope':'Possível enquadramento em apostas de quota fixa oferecidas no Brasil; requer verificação de atividade, público-alvo, exceções e situação jurídica atual.'}
    raise ValueError('Aviso regulatório não reconhecido; revisão da integração necessária')


async def sync_notice(db,commit=True):
    record=RegulatoryNotice(url=SPA_URL,status='failed',details={})
    try:
        async with network.semaphore:
            raw,hops,headers=await asyncio.wait_for(network.fetch(SPA_URL,allowed_hosts={'www.gov.br','gov.br'},https_only=True),30)
        from .documents import preserve_official
        document_id=preserve_official(db,SPA_URL,raw)
        parsed=parse_notice(raw)
        parsed['document_id']=document_id
        record.status='official_restriction_notice'
        record.version=parsed.pop('version')
        record.effective_from=parsed.pop('effective_from')
        record.details=parsed
        record.sha256=hashlib.sha256(raw).hexdigest()
    except Exception as exc:
        record.error=f'{type(exc).__name__}: {str(exc)[:300]}'
    db.add(record)
    if commit:db.commit()
    else:db.flush()
    return record


def context(db):
    record=db.scalar(select(RegulatoryNotice).order_by(RegulatoryNotice.id.desc()).limit(1))
    if not record:return {'verified':False,'reason':'Contexto normativo oficial ainda não consultado'}
    result={'verified':False,'source_id':record.id,'url':record.url,'consulted':record.consulted.isoformat(),
            'document_sha256':record.sha256,'version':record.version,'details':record.details,
            'effective_from':record.effective_from.isoformat() if record.effective_from else None}
    if record.status!='official_restriction_notice' or record.consulted.replace(tzinfo=timezone.utc)>now() or record.consulted.replace(tzinfo=timezone.utc)<now()-timedelta(hours=settings().regulatory_notice_max_hours):
        result['reason']='Fonte normativa indisponível, não reconhecida ou consulta vencida'
        return result
    if not record.effective_from or record.effective_from.replace(tzinfo=timezone.utc)>now():
        result['reason']='Regra sem vigência temporal aplicável'
        return result
    result.update(verified=True,kind=record.status,reason='A fonte oficial consultada informa restrição geral; o enquadramento deste domínio não está comprovado')
    return result


def verdict(regulation,technical):
    ctx=regulation.get('normative_context',{})
    terms=technical.get('matched_terms',[])
    base={'crime_determined':False,'requires_human_review':True,'evidence_terms':terms,
          'limitations':['Termos de apostas não comprovam oferta de quota fixa nem direcionamento ao Brasil.',
                         'Lista histórica, extensão do domínio, IP e score não comprovam legalidade ou crime.']}
    if technical.get('collection_status')=='incomplete':
        return dict(base,code='collection_incomplete',label='Coleta incompleta — requer nova verificação',
                    explanation='A coleta DNS/HTTP não foi concluída. Não há base para avaliar a atividade do domínio nesta tentativa.',source=ctx)
    if terms and technical.get('activity_context') in ('informational','unconfirmed'):
        return dict(base,code='activity_unconfirmed',label='Menções a apostas — atividade não confirmada',
                    explanation='O conteúdo cita apostas, mas a coleta não confirmou oferta operacional. Notícias e páginas informativas podem conter os mesmos termos.',source=ctx)
    if ctx.get('verified') and ctx.get('kind')=='official_restriction_notice':
        if terms:
            return dict(base,code='possible_noncompliance',label='Possível incompatibilidade com regra oficial',
                explanation='Há termos associados a apostas e um aviso oficial de restrição aplicável ao contexto. É necessário confirmar atividade, escopo territorial e exceções; não é uma declaração de ilegalidade.',source=ctx)
        return dict(base,code='scope_unconfirmed',label='Enquadramento regulatório não confirmado',
            explanation='O aviso oficial foi identificado, mas a coleta não confirmou atividade enquadrável neste domínio.',source=ctx)
    if regulation.get('status')=='listed':
        return dict(base,code='historical_match',label='Consta em documento — vigência não confirmada',
                    explanation='Correspondência documental não resolve o regime regulatório atual.')
    if regulation.get('status')=='not_found':
        return dict(base,code='not_located',label='Não localizado na fonte consultada',explanation='Ausência em uma fonte não comprova irregularidade.')
    return dict(base,code='not_verified',label='Situação regulatória não verificada',explanation=regulation.get('reason','Fonte indisponível'))


async def tick_regulation():
    if not settings().auto_official_sync:return False
    from .db import SessionLocal
    from .intelligence import sync_source
    from sqlalchemy.exc import IntegrityError
    with SessionLocal() as db:
        if db.get(SystemSchedule,'official_regulation') is None:
            try:
                with db.begin_nested():
                    db.add(SystemSchedule(key='official_regulation',next_run=now(),details={}))
                    db.flush()
            except IntegrityError:pass
        job=db.scalar(select(SystemSchedule).where(SystemSchedule.key=='official_regulation',SystemSchedule.next_run<=now()).with_for_update(skip_locked=True))
        if not job:return False
        notice=await sync_notice(db,commit=False)
        source=await sync_source(db,commit=False)
        job.next_run=now()+timedelta(hours=settings().official_sync_hours)
        job.details={'last_run':now().isoformat(),'notice_status':notice.status,'source_status':source.status,
                     'notice_error':notice.error,'source_error':source.error}
        db.commit()
        return True
