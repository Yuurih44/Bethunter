"""Paginated investigative queries, aggregated metrics and real operational alerts."""
from datetime import timedelta
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query,Response
from sqlalchemy import select,func,case,or_
from .db import get_db
from .security import current_user
from .models import (User,Domain,Analysis,Case,CaseDomain,Report,Complaint,Audit,Schedule,ReportJob,AnalysisJob,SystemSchedule,SecurityEvent,RawDocument,MailJob,WorkflowRun,now)
from .config import settings

router=APIRouter(prefix='/api')
def analysis_dict(a):return {'id':a.id,'domain_id':a.domain_id,'created':a.created,'score':a.score,'classification':a.classification,'review':a.review,'result':a.result}
def domain_dict(d):return {'id':d.id,'name':d.name,'created':d.created,'origin':d.origin}
def report_dict(r,c):return {'id':r.id,'case_id':r.case_id,'created':r.created,'sha256':r.sha256,'archived':r.archived,'status':c.status,'protocol':c.protocol,'confirmation':c.confirmation}
def latest_query(user):return select(Analysis.domain_id,func.max(Analysis.id).label('id')).join(Domain).where(Domain.owner_id==user.id).group_by(Analysis.domain_id).subquery()

@router.get('/inventory')
def inventory(page:int=Query(1,ge=1),size:int=Query(50,ge=1,le=200),q:str=Query('',max_length=253),priority:Literal['all','high','pending']='all',user=Depends(current_user),db=Depends(get_db)):
    latest=latest_query(user)
    stmt=select(Domain,Analysis).outerjoin(latest,latest.c.domain_id==Domain.id).outerjoin(Analysis,Analysis.id==latest.c.id).where(Domain.owner_id==user.id)
    if q:stmt=stmt.where(Domain.name.contains(q.lower(),autoescape=True))
    if priority=='high':stmt=stmt.where(Analysis.score>=50)
    if priority=='pending':stmt=stmt.where(Analysis.id.is_(None))
    total=db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows=db.execute(stmt.order_by(Domain.id.desc()).offset((page-1)*size).limit(size)).all()
    return {'total':total,'page':page,'size':size,'items':[dict(domain_dict(d),latest=analysis_dict(a) if a else None) for d,a in rows]}

@router.get('/pages/{resource}')
def pages(resource:Literal['domains','analyses','cases','reports','audit','report-jobs'],page:int=Query(1,ge=1),size:int=Query(50,ge=1,le=200),q:str=Query('',max_length=253),domain_id:int|None=None,user=Depends(current_user),db=Depends(get_db)):
    model={'domains':Domain,'analyses':Analysis,'cases':Case,'reports':Report,'audit':Audit,'report-jobs':ReportJob}[resource]
    if resource=='analyses':
        stmt=select(Analysis).join(Domain).where(Domain.owner_id==user.id)
        if domain_id:stmt=stmt.where(Analysis.domain_id==domain_id)
        if q:stmt=stmt.where(Domain.name.contains(q.lower(),autoescape=True))
    elif resource=='reports':stmt=select(Report,Complaint).join(Case).join(Complaint).where(Case.owner_id==user.id)
    elif resource=='audit':stmt=select(Audit).where(Audit.user_id==user.id)
    else:
        stmt=select(model).where(model.owner_id==user.id)
        if q:
            column=Domain.name if resource=='domains' else Case.title if resource=='cases' else None
            if column is not None:stmt=stmt.where(column.contains(q,autoescape=True))
    total=db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows=db.execute(stmt.order_by(model.id.desc()).offset((page-1)*size).limit(size)).all()
    items=[]
    for row in rows:
        value=row[0]
        if resource=='domains':items.append(domain_dict(value))
        elif resource=='analyses':items.append(analysis_dict(value))
        elif resource=='cases':items.append({'id':value.id,'title':value.title,'priority':value.priority,'status':value.status,'notes':value.notes,'created':value.created,'domain_ids':list(db.scalars(select(CaseDomain.domain_id).where(CaseDomain.case_id==value.id)))})
        elif resource=='reports':items.append(report_dict(*row))
        elif resource=='audit':items.append({'id':value.id,'created':value.created,'action':value.action,'details':value.details})
        else:items.append({'id':value.id,'case_id':value.case_id,'created':value.created,'status':value.status,'report_id':value.report_id,'error':value.error})
    return {'items':items,'total':total,'page':page,'size':size}

@router.get('/analyses/{id}')
def analysis_detail(id:int,user=Depends(current_user),db=Depends(get_db)):
    row=db.scalar(select(Analysis).join(Domain).where(Analysis.id==id,Domain.owner_id==user.id))
    if not row:raise HTTPException(404,'Análise não encontrada')
    return analysis_dict(row)


def dashboard_data(db,user):
    latest=latest_query(user)
    current=select(Analysis).join(latest,Analysis.id==latest.c.id)
    domains=db.scalar(select(func.count()).select_from(Domain).where(Domain.owner_id==user.id))
    analyzed=db.scalar(select(func.count()).select_from(latest))
    suspect=db.scalar(select(func.count()).select_from(current.where(Analysis.score>=50).subquery()))
    bucket=case((Analysis.score>=75,'75–100'),(Analysis.score>=50,'50–74'),(Analysis.score>=25,'25–49'),else_='0–24')
    distribution=dict(db.execute(select(bucket,func.count()).join(latest,Analysis.id==latest.c.id).group_by(bucket)).all())
    history=db.execute(select(func.date(Analysis.created),func.count()).join(Domain).where(Domain.owner_id==user.id).group_by(func.date(Analysis.created)).order_by(func.date(Analysis.created))).all()
    complaints=dict(db.execute(select(Complaint.status,func.count()).join(Report).join(Case).where(Case.owner_id==user.id).group_by(Complaint.status)).all())
    recent=db.execute(select(Analysis,Domain.name).join(Domain).where(Domain.owner_id==user.id).order_by(Analysis.id.desc()).limit(8)).all()
    return {'domains':domains,'analyzed':analyzed,'pending':domains-analyzed,'suspect':suspect,
        'prepared':complaints.get('prepared',0),'forwarded':complaints.get('confirmed_by_analyst',0),
        'distribution':[{'name':key,'value':distribution.get(key,0)} for key in ['0–24','25–49','50–74','75–100']],
        'history':[{'date':str(day),'analyses':count} for day,count in history],
        'recent':[dict(analysis_dict(a),domain=name) for a,name in recent]}

@router.get('/operations/alerts')
def alerts(user=Depends(current_user),db=Depends(get_db)):
    cutoff=now()-timedelta(hours=settings().backlog_alert_hours);items=[]
    jobs=db.scalar(select(func.count()).select_from(AnalysisJob).join(Domain).where(Domain.owner_id==user.id,AnalysisJob.status=='queued',AnalysisJob.created<cutoff))
    overdue=db.scalar(select(func.count()).select_from(Schedule).join(Domain).where(Domain.owner_id==user.id,Schedule.enabled.is_(True),Schedule.next_run<cutoff))
    failed=db.scalar(select(func.count()).select_from(ReportJob).where(ReportJob.owner_id==user.id,ReportJob.status=='failed'))
    mail_failures=db.scalar(select(func.count()).select_from(MailJob).where(MailJob.user_id==user.id,MailJob.status=='failed'))
    if mail_failures:items.append({'code':'mail_failures','level':'warning','message':f'{mail_failures} mensagens não puderam ser entregues; verifique o SMTP'})
    if jobs:items.append({'code':'backlog','level':'warning','message':f'{jobs} tarefas aguardam além do limite configurado'})
    if overdue:items.append({'code':'monitoring_overdue','level':'warning','message':f'{overdue} monitoramentos estão atrasados'})
    workflow_errors=db.scalar(select(func.count()).select_from(WorkflowRun).join(Analysis).join(Domain).where(Domain.owner_id==user.id,WorkflowRun.details['status'].as_string()=='failed'))
    if workflow_errors:items.append({'code':'workflow_failures','level':'warning','message':f'{workflow_errors} execuções do fluxo precisam de revisão'})
    if failed:items.append({'code':'report_failures','level':'warning','message':f'{failed} relatórios falharam; confira a fila'})
    heartbeat=db.get(SystemSchedule,'worker_heartbeat')
    if not heartbeat or heartbeat.next_run.replace(tzinfo=now().tzinfo)<now():items.append({'code':'worker_stale','level':'error','message':'Worker sem sinal recente; verifique o serviço e os logs'})
    backup=db.get(SystemSchedule,'backup')
    if user.role=='admin':
        from .backups import recent_backup_usable
        if not backup or not recent_backup_usable(backup.details):items.append({'code':'backup_unavailable','level':'error','message':'Backup automático ausente, indisponível ou com mais de 48 horas; verifique os arquivos e teste restauração'})
        attempts=db.scalar(select(func.count()).select_from(SecurityEvent).where(SecurityEvent.created>now()-timedelta(minutes=15)))
        if attempts>=5:items.append({'code':'auth_failures','level':'warning','message':f'{attempts} falhas recentes de autenticação'})
    return {'checked':now(),'items':items,'backup_status':backup.details.get('status') if backup and user.role=='admin' else None}

@router.get('/evidence/documents/{id}')
def raw_document(id:int,user=Depends(current_user),db=Depends(get_db)):
    document=db.get(RawDocument,id)
    if not document or document.owner_id not in (None,user.id):raise HTTPException(404,'Documento não encontrado')
    return Response(document.content,media_type='application/octet-stream',headers={'Content-Disposition':f'attachment; filename="evidence-{id}.bin"','X-Evidence-SHA256':document.sha256})

@router.post('/report-jobs/{id}/generate')
async def generate_report_job(id:int,user=Depends(current_user),db=Depends(get_db)):
    from .report_queue import tick_reports
    from .security import limit
    if user.role not in ('admin','analyst'):raise HTTPException(403,'Perfil sem permissão de geração')
    limit(('report.generate',user.id),3,60)
    job=db.scalar(select(ReportJob).where(ReportJob.id==id,ReportJob.owner_id==user.id))
    if not job:raise HTTPException(404,'Tarefa não encontrada')
    if job.status=='failed':raise HTTPException(409,'Repita a tarefa antes de gerar')
    if job.status=='queued':
        db.rollback()
        worked=await tick_reports(job_id=id,owner_id=user.id)
        if not worked:raise HTTPException(409,'Tarefa em processamento ou automação pausada')
    db.expire_all();job=db.get(ReportJob,id)
    return {'id':job.id,'status':job.status,'report_id':job.report_id,'error':job.error}

@router.post('/report-jobs/{id}/{action}')
def report_job_action(id:int,action:Literal['retry','discard'],user=Depends(current_user),db=Depends(get_db)):
    job=db.scalar(select(ReportJob).where(ReportJob.id==id,ReportJob.owner_id==user.id).with_for_update())
    if not job:raise HTTPException(404,'Tarefa não encontrada')
    if job.status!='failed':raise HTTPException(409,'Ação disponível apenas para falhas')
    if action=='retry':
        if not job.snapshot:raise HTTPException(409,'Snapshot descartado; solicite novo relatório pelo caso')
        job.status='queued';job.error='';job.finished=None
    else:job.snapshot={};job.error='Snapshot descartado pelo analista; evidências originais preservadas'
    db.add(Audit(user_id=user.id,action='report.job.'+action,details={'job_id':id}));db.commit()
    return {'id':id,'status':job.status}




@router.get('/automation/diagnostics')
def automation_diagnostics(user=Depends(current_user),db=Depends(get_db)):
    from .models import AutoQuota,WorkflowPolicy,DiscoveryFeed
    quota=db.get(AutoQuota,user.id);policy=db.get(WorkflowPolicy,user.id)
    heartbeat=db.get(SystemSchedule,'worker_heartbeat')
    healthy=bool(heartbeat and heartbeat.next_run.replace(tzinfo=now().tzinfo)>now())
    feeds=db.scalars(select(DiscoveryFeed).where(DiscoveryFeed.owner_id==user.id)).all()
    today=now().date().isoformat();used=quota.used if quota and quota.day==today else 0
    return {'worker_healthy':healthy,'worker_stage':heartbeat.details.get('stage') if heartbeat else None,
        'enabled':policy.enabled if policy else True,'minimum_score':policy.minimum_score if policy else 25,
        'daily_used':used,'daily_limit':settings().auto_analyses_per_day,
        'next_collection':quota.next_allowed if quota else None,
        'queue_pending':db.scalar(select(func.count()).select_from(AnalysisJob).join(Domain).where(Domain.owner_id==user.id,AnalysisJob.status=='queued')),
        'feeds':[{'id':f.id,'name':f.name,'enabled':f.enabled,'next_run':f.next_run,'error':f.last_error,'interval_hours':f.interval_hours,'batch_size':f.batch_size} for f in feeds],
        'notice':'Descoberta em fontes permitidas, sujeita a cotas. Não enumera toda a internet nem determina crime.'}

@router.post('/automation/continuous')
def continuous_automation(user=Depends(current_user),db=Depends(get_db)):
    from .models import WorkflowPolicy,DiscoveryFeed,SystemSchedule
    from .automation import CATALOG,validate_feed_url
    from .security import limit
    limit(('automation.continuous',user.id),5,60)
    if user.role not in ('admin','analyst'):raise HTTPException(403,'Perfil sem permissão')
    policy=db.get(WorkflowPolicy,user.id)
    if not policy:policy=WorkflowPolicy(owner_id=user.id);db.add(policy)
    policy.enabled=True;policy.create_cases=True;policy.prepare_reports=True;policy.minimum_score=25
    for source in CATALOG:
        try:validate_feed_url(source['url'])
        except ValueError:raise HTTPException(422,'Fonte padrão não permitida na configuração do servidor')
        feed=db.scalar(select(DiscoveryFeed).where(DiscoveryFeed.owner_id==user.id,DiscoveryFeed.url==source['url']))
        if not feed:
            if db.scalar(select(func.count()).select_from(DiscoveryFeed).where(DiscoveryFeed.owner_id==user.id))>=10:raise HTTPException(422,'Limite de fontes atingido')
            feed=DiscoveryFeed(owner_id=user.id,name=source['name'],url=source['url'],format=source['format'],permission_reference=source['permission_reference']);db.add(feed)
        feed.enabled=True;feed.auto_analyze=True;feed.interval_hours=1;feed.batch_size=100;feed.next_run=now()
    state=db.get(SystemSchedule,'autopilot:'+str(user.id))
    if state:state.next_run=now()
    db.add(Audit(user_id=user.id,action='automation.continuous',details={'source_interval_hours':1,'batch_size':100,'minimum_score':25}))
    db.commit()
    return {'notice':'Descoberta horária ativada; fila contínua dentro da cota do servidor. Casos e PDFs a partir de score 25 para revisão humana. Monitoramentos individuais preservados.'}
