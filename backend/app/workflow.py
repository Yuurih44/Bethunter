"""Collection -> monitoring -> investigation draft -> preserved PDF; no automatic sending."""
import hashlib
import json
from sqlalchemy import select
from fastapi import HTTPException
from .models import (WorkflowPolicy,WorkflowRun,Domain,Schedule,Case,CaseDomain,Analysis,
                     Evidence,Report,Complaint,Audit,now)
from .reports import pdf


def analysis_record(a):
    return {'id':a.id,'domain_id':a.domain_id,'created':a.created,'score':a.score,
            'classification':a.classification,'review':a.review,'result':a.result}


def prepare_report(db,case,actor_id,automatic=False):
    from .report_queue import queue_report
    return queue_report(db,case,actor_id,automatic)


def apply_workflow(db,domain,analysis,actor_id):
    if db.get(WorkflowRun,analysis.id):return
    db.scalar(select(Domain).where(Domain.id==domain.id).with_for_update())
    policy=db.get(WorkflowPolicy,domain.owner_id)
    if not policy:
        policy=WorkflowPolicy(owner_id=domain.owner_id,enabled=True,recurring_hours=24,create_cases=True,prepare_reports=True,minimum_score=25)
        db.add(policy);db.flush()
    run=WorkflowRun(analysis_id=analysis.id,details={'status':'disabled' if not policy.enabled else 'applied'})
    db.add(run)
    if not policy.enabled:return
    if not db.scalar(select(Schedule.id).where(Schedule.domain_id==domain.id)):
        from datetime import timedelta
        db.add(Schedule(domain_id=domain.id,interval_hours=policy.recurring_hours,enabled=True,automatic=True,next_run=now()+timedelta(hours=policy.recurring_hours)))
    result=analysis.result
    eligible=bool(result.get('technical',{}).get('ips')) and (analysis.score>=policy.minimum_score or result.get('verdict',{}).get('code')=='possible_noncompliance')
    if not eligible:
        run.details={**run.details,'reason':'Sem IP público coletado' if not result.get('technical',{}).get('ips') else f'Score {analysis.score} abaixo do mínimo {policy.minimum_score}; sem contexto de possível desconformidade'}
    elif not policy.create_cases:
        run.details={**run.details,'reason':'Criação automática de casos desabilitada'}
    if eligible and policy.create_cases:
        case=db.scalar(select(Case).join(WorkflowRun,WorkflowRun.case_id==Case.id).join(CaseDomain,CaseDomain.case_id==Case.id).where(Case.owner_id==domain.owner_id,CaseDomain.domain_id==domain.id).order_by(Case.id).limit(1))
        if case and case.status=='closed':
            run.case_id=case.id;run.details={'status':'skipped_closed','reason':'Caso encerrado pelo analista não é reaberto automaticamente'}
            return
        if not case:
            case=Case(owner_id=domain.owner_id,title=f'Revisar {domain.name}'[:200],priority='high' if analysis.score>=75 else 'normal',status='open',
                notes='Rascunho aberto automaticamente a partir de indicadores documentados. Sem conclusão humana. Revisar atividade, fontes oficiais, âmbito territorial e limitações antes de qualquer encaminhamento.')
            db.add(case);db.flush();db.add(CaseDomain(case_id=case.id,domain_id=domain.id));db.flush()
            db.add(Audit(user_id=actor_id,action='case.create.automatic',details={'case_id':case.id,'analysis_id':analysis.id}))
        run.case_id=case.id
        if policy.prepare_reports:
            from .report_queue import queue_report
            job=queue_report(db,case,actor_id,automatic=True,analysis_id=analysis.id)
            run.report_id=job.report_id
            run.details={**run.details,'report_job_id':job.id}
    db.add(Audit(user_id=actor_id,action='workflow.applied',details={'analysis_id':analysis.id,'case_id':run.case_id,'report_id':run.report_id}))
