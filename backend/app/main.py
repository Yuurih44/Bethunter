from .security import hash_password
import asyncio
import csv
import hashlib
import io
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Literal
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from starlette.middleware.trustedhost import TrustedHostMiddleware
from urllib.parse import urlsplit
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession
from .db import get_db
from .build import BUILD_ID, REQUIRED_SCHEMA_REVISION
from .models import User, Session, Domain, Analysis, Indicator, Evidence, Case, CaseDomain, Report, Complaint, Audit, OfficialSource, Rule, Schedule, DiscoveryFeed, DiscoveryRun, AnalysisJob, AutoQuota, Invitation, now
from .security import current_user, admin, hasher, issue_session, limit, token_hash, password_policy, throttle_row, authentication_failure, verify_password, verify_second_factor
from .config import settings
from .network import normalize, UnsafeTarget
from .intelligence import analyze, sync_source, DEFAULT_WEIGHTS
from .reports import pdf
from .collection import persist_analysis
from .automation import CATALOG, allowed_hosts, validate_feed_url, enqueue
from .accounts import router as account_router, normalize_email
from .workflow import prepare_report
from .models import WorkflowPolicy,WorkflowRun,RegulatoryNotice,SystemSchedule
from .regulation import context as regulatory_context, sync_notice

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("bethunter")
app = FastAPI(title="BetHunter",version="0.1.0",docs_url="/api/docs" if settings().app_env!='production' else None,openapi_url="/api/openapi.json" if settings().app_env!='production' else None,redoc_url=None)
app.include_router(account_router)
from .email_accounts import router as email_router
app.include_router(email_router)
from .operations import router as operations_router,dashboard_data
app.include_router(operations_router)
from .investigation_tools import router as investigation_router
app.include_router(investigation_router)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=list({urlsplit(settings().origin).hostname,'localhost','127.0.0.1','[::1]'}))

@app.middleware("http")
async def safeguards(request: Request, call_next):
    started = time.monotonic()
    # Trust an address header only from the explicitly configured reverse proxy.
    peer=request.client.host if request.client else ''
    if peer in {ip.strip() for ip in settings().trusted_proxy_ips.split(',') if ip.strip()}:
        import ipaddress
        try:
            client_ip=str(ipaddress.ip_address(request.headers.get('x-real-ip','')))
            request.scope['client']=(client_ip,0)
        except ValueError:pass
    if request.method in ("POST","PUT","PATCH","DELETE"):
        if request.headers.get("origin") != settings().origin:
            return Response('Origem não permitida',403)
        # Stream accounting rather than trusting Content-Length.
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 300_000:
                return Response("Corpo excede limite",413)
        request._body = bytes(body)
    response = await call_next(request)
    response.headers.update({"X-Content-Type-Options":"nosniff","X-Frame-Options":"DENY","Referrer-Policy":"no-referrer","Cache-Control":"no-store"})
    response.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
    if request.url.path!='/api/docs':
        response.headers['Content-Security-Policy']="default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    if settings().origin.startswith('https://'):
        response.headers['Strict-Transport-Security']='max-age=31536000'
    log.info(json.dumps({"event":"request","method":request.method,"path":request.url.path,"status":response.status_code,"ms":round((time.monotonic()-started)*1000)}))
    return response

def audit(db,user,action,details):
    db.add(Audit(user_id=user.id,action=action,details=jsonable_encoder(details)))

def owned(db, model, id, user):
    row = db.get(model,id)
    if not row or row.owner_id != user.id:
        raise HTTPException(404,"Registro não encontrado")
    return row

def domain_dict(d):
    return {"id":d.id,"name":d.name,"created":d.created,"origin":d.origin}

def analysis_dict(a):
    return {"id":a.id,"domain_id":a.domain_id,"created":a.created,"score":a.score,"classification":a.classification,"review":a.review,"result":a.result}

def case_dict(db,c):
    return {"id":c.id,"title":c.title,"priority":c.priority,"status":c.status,"notes":c.notes,"created":c.created,"domain_ids":list(db.scalars(select(CaseDomain.domain_id).where(CaseDomain.case_id==c.id)))}

class Credentials(BaseModel):
    email: str = Field(min_length=5,max_length=254)
    password: str = Field(min_length=1,max_length=128)
    @field_validator('email')
    @classmethod
    def email_check(cls,value):return normalize_email(value)

class Registration(Credentials):
    invitation: str | None = Field(default=None,max_length=200)
    @field_validator('password')
    @classmethod
    def strong(cls,value):return password_policy(value)

class LoginInput(Credentials):
    otp_code: str | None = Field(default=None,pattern=r'^\d{6}$')
    recovery_code: str | None = Field(default=None,max_length=100)
    @field_validator('otp_code','recovery_code',mode='before')
    @classmethod
    def empty(cls,value):return value or None

@app.get('/api/version')
def version():
    return {'build_id':BUILD_ID,'required_schema_revision':REQUIRED_SCHEMA_REVISION}

@app.get("/api/health")
def health(db: DBSession=Depends(get_db)):
    db.execute(select(1))
    return {"status":"ok"}

@app.post('/api/auth/register',status_code=201)
def register(body:Registration,request:Request,response:Response,db:DBSession=Depends(get_db)):
    limit(('register',request.client.host),5,3600)
    cfg=settings()
    if not cfg.registration_enabled or cfg.registration_mode=='closed':
        raise HTTPException(403,'Cadastro fechado')
    invitation=None
    if cfg.registration_mode=='invite':
        invitation=db.scalar(select(Invitation).where(Invitation.token_hash==token_hash(body.invitation or '')).with_for_update())
        if not invitation or invitation.revoked or invitation.used_at or invitation.expires.replace(tzinfo=timezone.utc)<=now() or invitation.email!=body.email:
            raise HTTPException(403,'Convite inválido, expirado, utilizado ou não corresponde ao email')
    user=User(email=body.email,password=hash_password(body.password),role=invitation.role if invitation else 'analyst')
    db.add(user)
    try:db.flush()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'Não foi possível cadastrar esta conta')
    if invitation:invitation.used_at=now()
    if cfg.smtp_mode!='disabled':
        from .mail import queue_token
        queue_token(db,user,'verify')
    audit(db,user,'user.register',{'invitation_id':invitation.id if invitation else None})
    return issue_session(db,user,response)

@app.post('/api/auth/login')
def login(body:LoginInput,request:Request,response:Response,db:DBSession=Depends(get_db)):
    limit(('login',request.client.host),10,60)
    throttle=throttle_row(db,'login:'+body.email)
    user=db.scalar(select(User).where(User.email==body.email).with_for_update().execution_options(populate_existing=True))
    valid=verify_password(user,body.password)
    if not user or not user.active or not valid or not verify_second_factor(db,user,body.otp_code,body.recovery_code):
        authentication_failure(db,throttle,request.client.host,user.id if user else None)
    throttle.failures=0;throttle.blocked_until=None
    if hasher.check_needs_rehash(user.password):user.password=hash_password(body.password)
    audit(db,user,'user.login',{'mfa':user.mfa_enabled})
    return issue_session(db,user,response,mfa_verified=user.mfa_enabled)

@app.get("/api/auth/me")
def me(request: Request,user=Depends(current_user)):
    return {"id":user.id,"email":user.email,"role":user.role,"csrf":request.state.session.csrf,"mfa_enabled":user.mfa_enabled,"email_verified":user.email_verified}

@app.post("/api/auth/logout")
def logout(request: Request,response: Response,user=Depends(current_user),db: DBSession=Depends(get_db)):
    db.delete(request.state.session); audit(db,user,"user.logout",{}); db.commit()
    response.delete_cookie("bh_session",path="/api",secure=settings().cookie_secure,httponly=True,samesite="strict")
    return {"ok":True}

class DomainInput(BaseModel):
    value: str = Field(min_length=3,max_length=2048)
    @field_validator("value")
    @classmethod
    def check(cls,v):
        return normalize(v)

@app.get("/api/domains")
def domains(user=Depends(current_user),db: DBSession=Depends(get_db)):
    return [domain_dict(d) for d in db.scalars(select(Domain).where(Domain.owner_id==user.id).order_by(Domain.id.desc()).limit(1000))]

@app.post("/api/domains",status_code=201)
def add_domain(body: DomainInput,user=Depends(current_user),db: DBSession=Depends(get_db)):
    d=db.scalar(select(Domain).where(Domain.owner_id==user.id,Domain.name==body.value))
    if not d:
        d=Domain(owner_id=user.id,name=body.value); db.add(d)
        try:
            db.flush()
        except IntegrityError:
            db.rollback(); raise HTTPException(409,"Domínio já cadastrado")
        audit(db,user,"domain.create",{"domain_id":d.id}); db.commit()
    return domain_dict(d)

@app.post("/api/domains/{id}/analyze")
async def run_analysis(id:int,user=Depends(current_user),db: DBSession=Depends(get_db)):
    d=owned(db,Domain,id,user)
    limit(("analysis",user.id),6,60)
    try:
        result=await asyncio.wait_for(analyze(db,d.name),60)
    except TimeoutError:
        raise HTTPException(504,"Tempo total de coleta excedido")
    a=persist_analysis(db,d,result,user.id)
    db.commit()
    return analysis_dict(a)

@app.get("/api/analyses")
def analyses(user=Depends(current_user),db: DBSession=Depends(get_db)):
    return [analysis_dict(a) for a in db.scalars(select(Analysis).join(Domain).where(Domain.owner_id==user.id).order_by(Analysis.id.desc()).limit(1000))]

class ReviewInput(BaseModel):
    review: str = Field(min_length=1,max_length=10000)

@app.patch("/api/analyses/{id}/review")
def review(id:int,body:ReviewInput,user=Depends(current_user),db: DBSession=Depends(get_db)):
    a=db.get(Analysis,id)
    if not a: raise HTTPException(404,"Análise não encontrada")
    owned(db,Domain,a.domain_id,user)
    old=a.review; a.review=body.review
    audit(db,user,"analysis.review",{"id":id,"before":old,"after":a.review}); db.commit()
    return analysis_dict(a)

@app.get("/api/dashboard")
def dashboard(user=Depends(current_user),db: DBSession=Depends(get_db)):
    return dashboard_data(db,user)

class CaseInput(BaseModel):
    title:str=Field(min_length=3,max_length=200)
    priority:Literal["low","normal","high"]="normal"
    status:Literal["open","investigating","closed"]="open"
    notes:str=Field(default="",max_length=20000)
    domain_ids:list[int]=Field(default_factory=list,max_length=200)

@app.get("/api/cases")
def cases(user=Depends(current_user),db: DBSession=Depends(get_db)):
    return [case_dict(db,c) for c in db.scalars(select(Case).where(Case.owner_id==user.id).order_by(Case.id.desc()))]

def save_case(db,user,body,c):
    for id in body.domain_ids: owned(db,Domain,id,user)
    before=case_dict(db,c) if c.id else None
    for key in ("title","priority","status","notes"): setattr(c,key,getattr(body,key))
    db.add(c); db.flush()
    for link in db.scalars(select(CaseDomain).where(CaseDomain.case_id==c.id)): db.delete(link)
    db.flush()
    for id in set(body.domain_ids): db.add(CaseDomain(case_id=c.id,domain_id=id))
    db.flush(); audit(db,user,"case.save",{"id":c.id,"before":before,"after":case_dict(db,c)}); db.commit()
    return case_dict(db,c)

@app.post("/api/cases",status_code=201)
def create_case(body:CaseInput,user=Depends(current_user),db: DBSession=Depends(get_db)):
    return save_case(db,user,body,Case(owner_id=user.id))

@app.put("/api/cases/{id}")
def edit_case(id:int,body:CaseInput,user=Depends(current_user),db: DBSession=Depends(get_db)):
    return save_case(db,user,body,owned(db,Case,id,user))

@app.post("/api/cases/{id}/reports",status_code=202)
def create_report(id:int,user=Depends(current_user),db: DBSession=Depends(get_db)):
    c=owned(db,Case,id,user)
    report=prepare_report(db,c,user.id)
    db.commit()
    return {"job_id":report.id,"status":report.status,"report_id":report.report_id,"notice":"Relatório enfileirado; acompanhe em Relatórios"}

@app.get("/api/reports")
def reports(user=Depends(current_user),db: DBSession=Depends(get_db)):
    rows=db.execute(select(Report,Complaint).join(Case).join(Complaint,Complaint.report_id==Report.id).where(Case.owner_id==user.id).order_by(Report.id.desc())).all()
    return [{"id":r.id,"case_id":r.case_id,"created":r.created,"sha256":r.sha256,"status":c.status,"protocol":c.protocol,"confirmation":c.confirmation} for r,c in rows]

@app.get("/api/reports/{id}/pdf")
def download(id:int,user=Depends(current_user),db: DBSession=Depends(get_db)):
    report=db.get(Report,id)
    if not report: raise HTTPException(404,"Relatório não encontrado")
    owned(db,Case,report.case_id,user)
    if report.archived:raise HTTPException(410,'PDF arquivado pela política de retenção; metadados e evidências preservados')
    return Response(report.content,media_type="application/pdf",headers={"Content-Disposition":f'attachment; filename="bethunter-{id}.pdf"'})

class Confirmation(BaseModel):
    protocol:str=Field(min_length=3,max_length=200)
    confirmation:str=Field(min_length=10,max_length=5000)

@app.post("/api/reports/{id}/confirmation")
def confirm(id:int,body:Confirmation,user=Depends(current_user),db: DBSession=Depends(get_db)):
    report=db.get(Report,id)
    if not report: raise HTTPException(404,"Relatório não encontrado")
    owned(db,Case,report.case_id,user)
    c=db.scalar(select(Complaint).where(Complaint.report_id==id))
    c.status="confirmed_by_analyst"; c.protocol=body.protocol; c.confirmation=body.confirmation
    audit(db,user,"complaint.confirmed_by_analyst",{"report":id,"protocol":body.protocol,"confirmation":body.confirmation}); db.commit()
    return {"status":c.status,"notice":"Informado pelo analista; sem validação automática junto ao serviço oficial"}

class CSVInput(BaseModel):
    csv:str=Field(max_length=250000)
    auto_analyze:bool=False

@app.post("/api/discovery/import")
def import_csv(body:CSVInput,user=Depends(current_user),db: DBSession=Depends(get_db)):
    reader=csv.DictReader(io.StringIO(body.csv))
    if not reader.fieldnames or "domain" not in reader.fieldnames: raise HTTPException(422,"CSV requer coluna domain")
    added,duplicates,errors,queued=0,0,[],0
    for i,row in enumerate(reader,2):
        if i>1001: raise HTTPException(422,"Máximo de 1000 linhas")
        try: name=normalize(row.get("domain") or "")
        except ValueError as exc:
            errors.append({"line":i,"error":str(exc)}); continue
        existing=db.scalar(select(Domain).where(Domain.owner_id==user.id,Domain.name==name))
        if existing:
            duplicates+=1
            if body.auto_analyze and enqueue(db,existing):queued+=1
            continue
        domain=Domain(owner_id=user.id,name=name,origin="csv")
        db.add(domain);db.flush();added+=1
        if body.auto_analyze and enqueue(db,domain):queued+=1
    audit(db,user,"discovery.csv",{"added":added,"duplicates":duplicates,"errors":errors,"queued":queued}); db.commit()
    return {"added":added,"duplicates":duplicates,"errors":errors,"queued":queued}

@app.get("/api/intelligence/graph")
def graph(user=Depends(current_user),db: DBSession=Depends(get_db)):
    rows=db.execute(select(Domain,Indicator,Analysis).join(Analysis,Analysis.domain_id==Domain.id).join(Indicator,Indicator.analysis_id==Analysis.id).where(Domain.owner_id==user.id).order_by(Analysis.id.desc()).limit(2000)).all()
    nodes,edges={},{}
    for d,i,a in rows:
        nodes[f"d{d.id}"]={"id":f"d{d.id}","label":d.name,"kind":"domain"}
        nodes[i.value]={"id":i.value,"label":i.value,"kind":i.kind}
        edges.setdefault((d.id,i.value),{"source":f"d{d.id}","target":i.value,"observed":a.created.isoformat()})
    return {"nodes":list(nodes.values()),"edges":list(edges.values()),"limitation":"IP compartilhado não comprova controle ou operador comum. Histórico restrito às coletas do BetHunter."}

class BlockInput(BaseModel):
    domain_ids:list[int]=Field(min_length=1,max_length=1000)
    format:Literal["hosts","adblock","domains"]="domains"

@app.post("/api/blocklists")
def blocklist(body:BlockInput,user=Depends(current_user),db: DBSession=Depends(get_db)):
    names=[owned(db,Domain,id,user).name for id in sorted(set(body.domain_ids))]
    lines=[("0.0.0.0 "+d if body.format=="hosts" else "||"+d+"^" if body.format=="adblock" else d) for d in names]
    audit(db,user,"blocklist.export",{"domains":names,"format":body.format}); db.commit()
    return Response("\n".join(lines)+"\n",media_type="text/plain",headers={"Content-Disposition":'attachment; filename="bethunter-blocklist.txt"'})

@app.get("/api/sources")
def sources(user=Depends(current_user),db: DBSession=Depends(get_db)):
    return [{"id":s.id,"url":s.url,"consulted":s.consulted,"document_updated":s.document_updated,"status":s.status,"error":s.error,"sha256":s.digest,"entries":s.entries} for s in db.scalars(select(OfficialSource).order_by(OfficialSource.id.desc()).limit(30))]

@app.post("/api/sources/sync")
async def sources_sync(user=Depends(admin),db: DBSession=Depends(get_db)):
    limit(("source",user.id),2,60)
    s=await sync_source(db); audit(db,user,"source.sync",{"id":s.id,"status":s.status}); db.commit()
    return {"id":s.id,"status":s.status,"error":s.error}

class RuleInput(BaseModel):
    version:str=Field(min_length=1,max_length=80)
    effective_from:datetime
    effective_until:datetime|None=None
    weights:dict[str,int]
    rationale:str=Field(min_length=10,max_length=5000)
    @field_validator("weights")
    @classmethod
    def weights_check(cls,v):
        if not set(v).issubset(DEFAULT_WEIGHTS) or not {"betting_content","cross_domain_redirect"}.issubset(v) or any(x<0 or x>100 for x in v.values()): raise ValueError("Pesos inválidos")
        return v

@app.get("/api/rules")
def rules(user=Depends(current_user),db: DBSession=Depends(get_db)):
    return [{"version":r.version,"effective_from":r.effective_from,"effective_until":r.effective_until,"config":r.config} for r in db.scalars(select(Rule).order_by(Rule.effective_from.desc()))]

@app.post("/api/rules",status_code=201)
def add_rule(body:RuleInput,user=Depends(admin),db: DBSession=Depends(get_db)):
    if body.effective_from.tzinfo is None or (body.effective_until and (body.effective_until.tzinfo is None or body.effective_until<=body.effective_from)):
        raise HTTPException(422,"Datas com fuso horário e intervalo válido são obrigatórios")
    rule=Rule(version=body.version,effective_from=body.effective_from,effective_until=body.effective_until,config={"weights":body.weights,"rationale":body.rationale})
    db.add(rule); audit(db,user,"rule.create",body.model_dump(mode="json"))
    try: db.commit()
    except IntegrityError:
        db.rollback(); raise HTTPException(409,"Versão já existe")
    return {"version":rule.version}

@app.get("/api/audit")
def audits(user=Depends(current_user),db: DBSession=Depends(get_db)):
    return [{"id":a.id,"created":a.created,"action":a.action,"details":a.details} for a in db.scalars(select(Audit).where(Audit.user_id==user.id).order_by(Audit.id.desc()).limit(500))]


class ScheduleInput(BaseModel):
    domain_id:int
    interval_hours:int=Field(default=24,ge=1,le=8760)
    enabled:bool=True

@app.get("/api/schedules")
def schedules(user=Depends(current_user),db: DBSession=Depends(get_db)):
    rows=db.execute(select(Schedule,Domain).join(Domain).where(Domain.owner_id==user.id)).all()
    return [{"id":s.id,"domain_id":d.id,"domain":d.name,"interval_hours":s.interval_hours,"enabled":s.enabled,"next_run":s.next_run,"last_run":s.last_run,"last_error":s.last_error} for s,d in rows]

@app.post("/api/schedules")
def save_schedule(body:ScheduleInput,user=Depends(current_user),db: DBSession=Depends(get_db)):
    d=owned(db,Domain,body.domain_id,user)
    s=db.scalar(select(Schedule).where(Schedule.domain_id==d.id))
    if not s:
        s=Schedule(domain_id=d.id,next_run=now());db.add(s)
    s.interval_hours=body.interval_hours;s.enabled=body.enabled
    audit(db,user,"schedule.save",body.model_dump());db.commit()
    return {"id":s.id,"enabled":s.enabled}

# Discovery configuration is owned by each analyst; operator controls egress hosts.

class FeedInput(BaseModel):
    name: str = Field(min_length=3,max_length=150)
    url: str = Field(max_length=2048)
    format: Literal['csv','json','domains','hosts']
    permission_reference: str = Field(min_length=15,max_length=2000)
    interval_hours: int = Field(default=24,ge=1,le=8760)
    batch_size: int = Field(default=50,ge=1,le=100)
    auto_analyze: bool = True
    enabled: bool = True
    @field_validator('url')
    @classmethod
    def url_check(cls,value):
        return validate_feed_url(value)

@app.get('/api/discovery/catalog')
def discovery_catalog(user=Depends(current_user)):
    return {'sources':CATALOG,'allowed_hosts':sorted(allowed_hosts()),
            'daily_limit':settings().auto_analyses_per_day,'delay_seconds':settings().auto_analysis_delay_seconds,
            'queue_limit':settings().auto_queue_limit}

@app.get('/api/discovery/feeds')
def discovery_feeds(user=Depends(current_user),db: DBSession=Depends(get_db)):
    return [{'id':f.id,'name':f.name,'url':f.url,'format':f.format,'permission_reference':f.permission_reference,
             'enabled':f.enabled,'auto_analyze':f.auto_analyze,'interval_hours':f.interval_hours,
             'batch_size':f.batch_size,'next_run':f.next_run,'last_error':f.last_error}
            for f in db.scalars(select(DiscoveryFeed).where(DiscoveryFeed.owner_id==user.id).order_by(DiscoveryFeed.id.desc()))]

@app.post('/api/discovery/feeds',status_code=201)
def discovery_add_feed(body:FeedInput,user=Depends(current_user),db: DBSession=Depends(get_db)):
    limit(('discovery.configure',user.id),5,60)
    if db.scalar(select(func.count()).select_from(DiscoveryFeed).where(DiscoveryFeed.owner_id==user.id))>=10:
        raise HTTPException(422,'Limite de 10 fontes por usuário')
    feed=DiscoveryFeed(owner_id=user.id,**body.model_dump())
    db.add(feed)
    try:
        db.flush()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'Fonte já cadastrada')
    audit(db,user,'discovery.feed.create',{'id':feed.id,**body.model_dump()});db.commit()
    return {'id':feed.id,'enabled':feed.enabled}

class FeedState(BaseModel):
    enabled: bool

@app.patch('/api/discovery/feeds/{id}/state')
def discovery_feed_state(id:int,body:FeedState,user=Depends(current_user),db: DBSession=Depends(get_db)):
    feed=owned(db,DiscoveryFeed,id,user)
    feed.enabled=body.enabled
    audit(db,user,'discovery.feed.state',{'id':id,'enabled':body.enabled});db.commit()
    return {'id':id,'enabled':feed.enabled,'notice':'Pausar fonte interrompe novas importações. Pause a fila separadamente para interromper os candidatos já importados.'}

@app.get('/api/discovery/runs')
def discovery_runs(user=Depends(current_user),db: DBSession=Depends(get_db)):
    rows=db.execute(select(DiscoveryRun,DiscoveryFeed.name).join(DiscoveryFeed).where(DiscoveryFeed.owner_id==user.id).order_by(DiscoveryRun.id.desc()).limit(50)).all()
    return [{'id':r.id,'feed_id':r.feed_id,'feed':name,'created':r.created,'status':r.status,'sha256':r.sha256,'counts':r.counts,'error':r.error} for r,name in rows]

@app.get('/api/discovery/jobs')
def discovery_jobs(user=Depends(current_user),db: DBSession=Depends(get_db)):
    rows=db.execute(select(AnalysisJob,Domain.name).join(Domain).where(Domain.owner_id==user.id).order_by(AnalysisJob.id.desc()).limit(100)).all()
    grouped=db.execute(select(AnalysisJob.status,func.count()).join(Domain).where(Domain.owner_id==user.id).group_by(AnalysisJob.status)).all()
    quota=db.get(AutoQuota,user.id)
    return {'counts':dict(grouped),'used_today':quota.used if quota and quota.day==now().date().isoformat() else 0,
        'daily_limit':settings().auto_analyses_per_day,
        'jobs':[{'id':j.id,'domain':name,'domain_id':j.domain_id,'status':j.status,'attempts':j.attempts,'created':j.created,'finished':j.finished,'error':j.error,'analysis_id':j.analysis_id} for j,name in rows]}

@app.post('/api/discovery/queue')
def discovery_enqueue_pending(user=Depends(current_user),db: DBSession=Depends(get_db)):
    limit(('discovery.queue',user.id),2,60)
    candidates=db.scalars(select(Domain).where(Domain.owner_id==user.id,
        ~select(Analysis.id).where(Analysis.domain_id==Domain.id).exists(),
        ~select(AnalysisJob.id).where(AnalysisJob.domain_id==Domain.id).exists()).order_by(Domain.id).limit(100)).all()
    queued=sum(enqueue(db,d) for d in candidates)
    audit(db,user,'discovery.queue.pending',{'queued':queued});db.commit()
    return {'queued':queued}

class JobAction(BaseModel):
    action: Literal['pause','resume','retry']

@app.post('/api/discovery/jobs/{id}/action')
def discovery_job_action(id:int,body:JobAction,user=Depends(current_user),db: DBSession=Depends(get_db)):
    job=db.scalar(select(AnalysisJob).where(AnalysisJob.id==id).with_for_update())
    if not job:raise HTTPException(404,'Tarefa não encontrada')
    owned(db,Domain,job.domain_id,user)
    previous=job.status
    transitions={('queued','pause'):'paused',('paused','resume'):'queued',('failed','retry'):'queued'}
    target=transitions.get((previous,body.action))
    if not target:raise HTTPException(409,'Ação incompatível com o estado atual')
    if body.action=='retry':
        count=db.scalar(select(func.count()).select_from(AnalysisJob).join(Domain).where(Domain.owner_id==user.id,AnalysisJob.status.in_(['queued','paused'])))
        if count>=settings().auto_queue_limit:raise HTTPException(422,'Fila cheia')
    job.status=target
    if target=='queued':job.finished=None
    audit(db,user,'discovery.job.action',{'id':id,'before':previous,'after':target});db.commit()
    return {'id':id,'status':target}

@app.post('/api/discovery/queue/pause')
def discovery_pause_queue(user=Depends(current_user),db: DBSession=Depends(get_db)):
    count=0
    for job in db.scalars(select(AnalysisJob).join(Domain).where(Domain.owner_id==user.id,AnalysisJob.status=='queued').with_for_update(skip_locked=True,of=AnalysisJob)):
        job.status='paused';count+=1
    audit(db,user,'discovery.queue.pause',{'count':count});db.commit()
    return {'paused':count}


@app.post('/api/discovery/queue/resume')
def discovery_resume_queue(user=Depends(current_user),db: DBSession=Depends(get_db)):
    count=0
    for job in db.scalars(select(AnalysisJob).join(Domain).where(Domain.owner_id==user.id,AnalysisJob.status=='paused').with_for_update(skip_locked=True,of=AnalysisJob)):
        job.status='queued';count+=1
    audit(db,user,'discovery.queue.resume',{'count':count});db.commit()
    return {'resumed':count}


class WorkflowInput(BaseModel):
    enabled:bool=True
    recurring_hours:int=Field(default=24,ge=1,le=8760)
    create_cases:bool=True
    prepare_reports:bool=True
    minimum_score:int=Field(default=25,ge=0,le=100)

def workflow_dict(policy):
    return {'enabled':policy.enabled,'recurring_hours':policy.recurring_hours,'create_cases':policy.create_cases,'prepare_reports':policy.prepare_reports,'minimum_score':policy.minimum_score}

@app.get('/api/automation/workflow')
def workflow_settings(user=Depends(current_user),db:DBSession=Depends(get_db)):
    policy=db.get(WorkflowPolicy,user.id)
    return workflow_dict(policy) if policy else WorkflowInput().model_dump()

@app.put('/api/automation/workflow')
def workflow_save(body:WorkflowInput,user=Depends(current_user),db:DBSession=Depends(get_db)):
    if body.prepare_reports and not body.create_cases:raise HTTPException(422,'Relatórios automáticos exigem criação de casos habilitada')
    policy=db.get(WorkflowPolicy,user.id)
    if not policy:policy=WorkflowPolicy(owner_id=user.id);db.add(policy)
    for key,value in body.model_dump().items():setattr(policy,key,value)
    audit(db,user,'workflow.configure',body.model_dump());db.commit()
    return workflow_dict(policy)

@app.get('/api/automation/history')
def workflow_history(user=Depends(current_user),db:DBSession=Depends(get_db)):
    rows=db.execute(select(WorkflowRun,Domain.name).join(Analysis,WorkflowRun.analysis_id==Analysis.id).join(Domain,Analysis.domain_id==Domain.id).where(Domain.owner_id==user.id).order_by(WorkflowRun.analysis_id.desc()).limit(50)).all()
    return [{'analysis_id':r.analysis_id,'domain':name,'case_id':r.case_id,'report_id':r.report_id,'created':r.created,'details':r.details} for r,name in rows]

@app.get('/api/regulatory/context')
def regulatory_state(user=Depends(current_user),db:DBSession=Depends(get_db)):
    return regulatory_context(db)

@app.post('/api/regulatory/sync')
async def regulatory_refresh(user=Depends(admin),db:DBSession=Depends(get_db)):
    limit(('normative',user.id),2,60)
    notice=await sync_notice(db)
    audit(db,user,'regulation.sync',{'id':notice.id,'status':notice.status});db.commit()
    return regulatory_context(db)

@app.get('/api/automation/status')
def autopilot_status(user=Depends(current_user),db:DBSession=Depends(get_db)):
    state=db.get(SystemSchedule,'autopilot:'+str(user.id))
    policy=db.get(WorkflowPolicy,user.id)
    return {'automatic_setup':settings().auto_setup,'enabled':policy.enabled if policy else True,
            'last_reconciliation':state.details if state else None,
            'next_reconciliation':state.next_run if state else None,
            'daily_limit':settings().auto_analyses_per_day,'delay_seconds':settings().auto_analysis_delay_seconds}
