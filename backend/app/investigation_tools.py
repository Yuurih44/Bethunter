"""Actionable notifications and factual case readiness, derived from stored records."""
import hashlib
import json
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from .db import get_db
from .security import current_user, limit
from .models import Audit, Case, CaseDomain, Domain, Analysis, Evidence, Report, User, now
from .operations import alerts

router = APIRouter(prefix='/api')


def notification_items(db, user):
    items = alerts(user=user, db=db)['items']
    for item in items:
        item['link'] = '/reports' if item['code'] == 'report_failures' else '/security' if item['code'] in ('auth_failures','mail_failures') else '/discovery'
    reports = db.scalars(select(Report).join(Case).where(
        Case.owner_id == user.id, Report.archived.is_(False),
        Report.created >= now()-timedelta(days=7)).order_by(Report.id.desc()).limit(10)).all()
    for report in reports:
        items.append({'code':f'report_ready:{report.id}', 'level':'info',
                      'message':f'PDF #{report.id} disponível para o caso #{report.case_id}', 'link':'/reports'})
    for item in items:
        item['id'] = hashlib.sha256(json.dumps([item['code'],item['message']], ensure_ascii=False).encode()).hexdigest()
    acknowledged = {row.details.get('notification_id') for row in db.scalars(
        select(Audit).where(Audit.user_id==user.id,Audit.action=='notification.ack')
        .order_by(Audit.id.desc()).limit(2000))}
    return [dict(item, acknowledged=item['id'] in acknowledged) for item in items]


@router.get('/notifications')
def notifications(user=Depends(current_user), db=Depends(get_db)):
    items=notification_items(db,user)
    return {'checked':now(), 'unread':sum(not i['acknowledged'] for i in items), 'items':items,
            'notice':'Avisos atuais e os dez PDFs mais recentes dos últimos sete dias. Reconhecer um aviso não resolve sua causa.'}


class Acknowledge(BaseModel):
    notification_id: str=Field(pattern=r'^[0-9a-f]{64}$')


@router.post('/notifications/acknowledge')
def acknowledge(body:Acknowledge,user=Depends(current_user),db=Depends(get_db)):
    limit(('notification.ack',user.id),30,60)
    db.scalar(select(User).where(User.id==user.id).with_for_update())
    item=next((i for i in notification_items(db,user) if i['id']==body.notification_id),None)
    if item is None:raise HTTPException(404,'Aviso não disponível para esta conta')
    if not item['acknowledged']:
        db.add(Audit(user_id=user.id,action='notification.ack',details={'notification_id':item['id'],'code':item['code']}));db.commit()
    return {'acknowledged':True}


@router.get('/cases/{id}/checklist')
def case_checklist(id:int,user=Depends(current_user),db=Depends(get_db)):
    case=db.scalar(select(Case).where(Case.id==id,Case.owner_id==user.id))
    if case is None:raise HTTPException(404,'Caso não encontrado')
    domains=db.scalars(select(Domain).join(CaseDomain).where(CaseDomain.case_id==case.id)).all()
    from .regulation import context
    current_context=context(db)
    rows=[]
    for domain in domains:
        analysis=db.scalar(select(Analysis).where(Analysis.domain_id==domain.id).order_by(Analysis.id.desc()).limit(1))
        collected=bool(analysis and analysis.result.get('technical',{}).get('collection_status')=='complete')
        fresh=bool(analysis and now()-timedelta(hours=24)<=analysis.created.replace(tzinfo=now().tzinfo)<=now())
        evidence=bool(analysis and db.scalar(select(func.count()).select_from(Evidence).where(Evidence.analysis_id==analysis.id)))
        regulation=analysis.result.get('regulation',{}) if analysis else {}
        # Even a verified historical result requires the current legal context to remain valid.
        analysis_context=regulation.get('normative_context',{})
        regulatory=bool(regulation.get('status') in ('restricted_framework','listed','not_found')
                        and analysis_context.get('verified') and current_context.get('verified')
                        and current_context.get('document_sha256')
                        and analysis_context.get('document_sha256')==current_context.get('document_sha256')
                        and analysis_context.get('version')==current_context.get('version'))
        rows.append({'id':domain.id,'domain':domain.name,'analysis_id':analysis.id if analysis else None,
                     'analyzed':analysis is not None,'collection_complete':collected,'recent_24h':fresh,
                     'evidence_preserved':evidence,'human_review_recorded':bool(analysis and analysis.review.strip()),
                     'regulatory_verified':regulatory})
    checks=[{'key':'domains','label':'Ao menos um domínio associado','passed':bool(rows)}]
    for key,label in [('analyzed','Todos os domínios têm análise'),('collection_complete','Últimas coletas completas'),
                      ('recent_24h','Últimas análises nas últimas 24 horas'),('evidence_preserved','Evidências estruturadas preservadas'),
                      ('human_review_recorded','Parecer humano registrado em cada última análise'),('regulatory_verified','Contexto regulatório atual disponível e consultado na análise')]:
        checks.append({'key':key,'label':label,'passed':bool(rows) and all(row[key] for row in rows)})
    return {'case_id':case.id,'checked':now(),'checks':checks,'domains':rows,
            'pending':sum(not check['passed'] for check in checks),
            'limitations':'Checklist auxiliar, sem certificação jurídica. Não bloqueia PDF ou encerramento. Parecer registrado não comprova sua qualidade. Colete novamente se o resultado estiver desatualizado.'}
