"""Bounded durable PDF jobs. The API only captures snapshots; rendering is isolated."""
import asyncio,hashlib,json,subprocess,sys,os
from pathlib import Path
from datetime import timedelta
from sqlalchemy import select,func,cast,Text,or_
from fastapi import HTTPException
from .models import (Case,CaseDomain,Domain,Analysis,Evidence,ReportJob,Report,Complaint,Audit,WorkflowRun,WorkflowPolicy,User,now)
from .config import settings
from .db import SessionLocal


def semantic_result(value):
    """Ignore collection bookkeeping, retain technical and regulatory evidence."""
    volatile={'collected','consulted','created','first_seen','last_seen','source_id',
              'document_id','raw_document_ids','observed_run_id'}
    if isinstance(value,dict):return {key:semantic_result(item) for key,item in value.items() if key not in volatile}
    if isinstance(value,list):return [semantic_result(item) for item in value]
    return value


def snapshot_for(db,case,automatic):
    cfg=settings();ids=list(db.scalars(select(CaseDomain.domain_id).where(CaseDomain.case_id==case.id)))
    if not ids:raise HTTPException(422,'Associe ao menos um domínio')
    records=[];signature=[];budget=0
    for did in ids:
        domain=db.get(Domain,did)
        if not domain or domain.owner_id!=case.owner_id:raise HTTPException(404,'Domínio não encontrado')
        rows=list(db.scalars(select(Analysis).where(Analysis.domain_id==did).order_by(Analysis.id.desc()).limit(cfg.report_max_history)))
        count=db.scalar(select(func.count()).select_from(Analysis).where(Analysis.domain_id==did))
        rows.reverse()
        record={'domain':domain.name,'history_count':count,'history_included':len(rows),'history':[], 'evidence':[]}
        for a in rows:
            record['history'].append({'id':a.id,'created':a.created.isoformat(),'score':a.score,'classification':a.classification,'review':a.review,'result':a.result})
            for evidence in db.scalars(select(Evidence).where(Evidence.analysis_id==a.id)):
                record['evidence'].append({'sha256':evidence.sha256,'collected':evidence.collected.isoformat(),'payload':evidence.payload})
        budget+=len(json.dumps(record,default=str).encode())
        if budget>cfg.report_max_snapshot_bytes:raise HTTPException(422,'Histórico excede o limite de snapshot')
        records.append(record)
        last=rows[-1] if rows else None
        result=last.result if last else {};technical=result.get('technical',{})
        signature.append({'domain':domain.name,'review':last.review if last else '', 'score':last.score if last else None,
            'content':technical.get('content_sha256'),'ips':sorted(technical.get('ips',[])),
            'terms':technical.get('matched_terms',[]),'collection':technical.get('collection_status'),
            'verdict':result.get('verdict',{}).get('code'),'regulation':result.get('regulation',{}).get('status'),
            'rule':result.get('rule_version'),'factors':result.get('factors',[]),'errors':result.get('errors',[]),
            'classification':last.classification if last else None,
            'semantic_result':semantic_result(result),
            'recorded_reviews':[{'analysis_id':a.id,'review':a.review} for a in rows if a.review]})
    snapshot={'Caso':{'id':case.id,'title':case.title,'notes':case.notes,'status':case.status,'priority':case.priority},
        'Coleta do relatório':now().isoformat(),'Domínios e histórico':records,
        'Conclusão técnica':case.notes or 'Sem conclusão humana registrada',
        'Preparação':'Rascunho automático para revisão humana' if automatic else 'Preparado pelo analista',
        'Limitações':f'Até {cfg.report_max_history} análises recentes por domínio; contagens totais acima. Histórico completo preservado no banco. Fontes públicas, coleta pontual e revisão humana obrigatória. Não determina crime. Sem envio ou protocolo automático.'}
    encoded=json.dumps(snapshot,ensure_ascii=False,default=str).encode()
    if len(encoded)>cfg.report_max_snapshot_bytes:raise HTTPException(422,'Snapshot excede o limite. Reduza os domínios do caso ou o histórico incluído.')
    fingerprint=hashlib.sha256(json.dumps({'case':snapshot['Caso'],'domains':signature,'automatic':automatic},sort_keys=True,default=str).encode()).hexdigest()
    return snapshot,fingerprint



def storage_used(db,owner_id):
    reports=db.scalar(select(func.coalesce(func.sum(func.length(Report.content)+4*func.length(cast(Report.snapshot,Text))),0)).join(Case).where(Case.owner_id==owner_id))
    jobs=db.scalar(select(func.coalesce(func.sum(4*func.length(cast(ReportJob.snapshot,Text))),0)).where(ReportJob.owner_id==owner_id))
    return reports+jobs

def queue_report(db,case,actor_id,automatic=False,analysis_id=None):
    # Owner lock serializes concurrent quota and deduplication checks.
    db.scalar(select(User).where(User.id==case.owner_id).with_for_update())
    snapshot,fingerprint=snapshot_for(db,case,automatic)
    existing=db.scalar(select(ReportJob).where(ReportJob.case_id==case.id,ReportJob.fingerprint==fingerprint))
    archived=existing and existing.report_id and db.get(Report,existing.report_id).archived
    if existing and not archived and not (existing.status=='failed' and not existing.snapshot):return existing
    pending=db.scalar(select(func.count()).select_from(ReportJob).where(ReportJob.owner_id==case.owner_id,ReportJob.status.in_(['queued','failed']),func.length(cast(ReportJob.snapshot,Text))>2))
    if pending>=20:raise HTTPException(429,'Fila de relatórios cheia; conclua ou descarte falhas pendentes')
    if storage_used(db,case.owner_id)+4*len(json.dumps(snapshot,default=str))>settings().report_storage_limit_mb*1_000_000:raise HTTPException(422,'Cota de relatórios e snapshots excedida')
    if existing:
        existing.status='queued';existing.error='';existing.snapshot=snapshot;existing.finished=None;existing.report_id=None;existing.analysis_id=analysis_id;return existing
    job=ReportJob(automatic=automatic,owner_id=case.owner_id,case_id=case.id,analysis_id=analysis_id,fingerprint=fingerprint,snapshot=snapshot)
    db.add(job);db.flush();db.add(Audit(user_id=actor_id,action='report.queue',details={'job_id':job.id,'automatic':automatic}))
    return job


def render(snapshot):
    cfg=settings();encoded=json.dumps(snapshot,ensure_ascii=False).encode()
    renderer_env={key:os.environ[key] for key in ('PATH','LANG','LC_ALL','SYSTEMROOT') if key in os.environ}
    renderer_env.update({'APP_ENV':'development','DATABASE_URL':'sqlite://','ORIGIN':'http://localhost:8080',
                        'REPORT_MAX_SNAPSHOT_BYTES':str(cfg.report_max_snapshot_bytes),'REPORT_MAX_PDF_BYTES':str(cfg.report_max_pdf_bytes)})
    result=subprocess.run([sys.executable,'-m','app.render_pdf'],input=encoded,capture_output=True,timeout=35,cwd=Path(__file__).resolve().parents[1],env=renderer_env)
    if result.returncode or not result.stdout.startswith(b'%PDF'):
        detail=result.stderr.decode('utf-8',errors='replace').strip().splitlines()
        raise ValueError('Renderização falhou (código '+str(result.returncode)+'): '+(detail[-1][:250] if detail else 'processo encerrado por limite ou saída PDF inválida'))
    if len(result.stdout)>cfg.report_max_pdf_bytes:raise ValueError('PDF excede limite de tamanho')
    return result.stdout


async def tick_reports(job_id=None,owner_id=None):
    with SessionLocal() as db:
        statement=select(ReportJob).outerjoin(WorkflowPolicy,WorkflowPolicy.owner_id==ReportJob.owner_id).where(ReportJob.status=='queued',or_(ReportJob.automatic.is_(False),WorkflowPolicy.owner_id.is_(None),WorkflowPolicy.enabled.is_(True)))
        if job_id is not None:statement=statement.where(ReportJob.id==job_id)
        if owner_id is not None:statement=statement.where(ReportJob.owner_id==owner_id)
        job=db.scalar(statement.order_by(ReportJob.id).with_for_update(skip_locked=True,of=ReportJob).limit(1))
        if not job:return False
        owner=db.scalar(select(User).where(User.id==job.owner_id).with_for_update(skip_locked=True))
        if owner is None:return False
        try:
            if not owner.active or owner.role not in ('admin','analyst'):raise ValueError('Conta sem permissão de geração')
            used=storage_used(db,owner.id)
            if used>=settings().report_storage_limit_mb*1_000_000:raise ValueError('Cota de armazenamento de relatórios excedida')
            content=await asyncio.to_thread(render,job.snapshot)
            if used+len(content)>settings().report_storage_limit_mb*1_000_000:raise ValueError('Cota de armazenamento de relatórios excedida')
            with db.begin_nested():
                report=Report(case_id=job.case_id,sha256=hashlib.sha256(content).hexdigest(),snapshot=job.snapshot,content=content)
                db.add(report);db.flush();db.add(Complaint(report_id=report.id,status='prepared'))
                job.report_id=report.id;job.status='done';job.error='';job.snapshot={}
                for run in db.scalars(select(WorkflowRun).where(WorkflowRun.case_id==job.case_id,WorkflowRun.report_id.is_(None))):
                    if run.details.get('report_job_id')==job.id:run.report_id=report.id
                db.add(Audit(user_id=owner.id,action='report.rendered',details={'report_id':report.id,'job_id':job.id,'sha256':report.sha256}))
        except Exception as exc:job.status='failed';job.error=f'{type(exc).__name__}: {str(exc)[:200]}'
        job.finished=now();db.commit();return True
