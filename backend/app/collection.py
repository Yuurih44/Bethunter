import hashlib
import json
import logging
from .models import Analysis, Indicator, Evidence, Audit,RawDocument
from sqlalchemy import select,func
from .config import settings

def persist_analysis(db, domain, result, actor_id, scheduled=False):
    result=dict(result)
    documents=result.pop('_raw_documents',[])
    a=Analysis(domain_id=domain.id,score=result["score"],classification=result["classification"],result=result)
    db.add(a); db.flush()
    for ip in result["technical"].get("ips",[]):
        db.add(Indicator(analysis_id=a.id,kind="ip",value=ip))
    for asn in result['technical'].get('infrastructure',{}).get('asns',[]):
        db.add(Indicator(analysis_id=a.id,kind='asn',value='AS'+str(asn)))
    document_ids=[]
    used=db.scalar(select(func.coalesce(func.sum(func.length(RawDocument.content)),0)).where(RawDocument.owner_id==domain.owner_id))
    for document in documents:
        content=document['content']
        digest=hashlib.sha256(content).hexdigest()
        existing=db.scalar(select(RawDocument).where(RawDocument.owner_id==domain.owner_id,RawDocument.url==document['url'],RawDocument.sha256==digest))
        if existing:document_ids.append(existing.id);continue
        if used+len(content)>settings().raw_document_storage_limit_mb*1_000_000:
            result.setdefault('errors',[]).append('Documento bruto não preservado: cota de armazenamento excedida');continue
        row=RawDocument(owner_id=domain.owner_id,analysis_id=a.id,url=document['url'],content=content,
            sha256=hashlib.sha256(content).hexdigest(),media_type=document.get('media_type','application/octet-stream')[:150])
        db.add(row);db.flush();document_ids.append(row.id);used+=len(content)
    result['raw_document_ids']=document_ids;a.result=dict(result)
    payload={"domain":domain.name,"analysis":result,"collected":a.created.isoformat()}
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    db.add(Evidence(analysis_id=a.id,sha256=digest,payload=payload))
    db.add(Audit(user_id=actor_id,action="analysis.scheduled" if scheduled else "analysis.collect",details={"domain_id":domain.id,"analysis_id":a.id,"sha256":digest}))
    from .workflow import apply_workflow
    from .models import WorkflowRun
    try:
        with db.begin_nested():
            apply_workflow(db,domain,a,actor_id)
    except Exception as exc:
        logging.getLogger('bethunter').exception('workflow_failed')
        db.add(WorkflowRun(analysis_id=a.id,details={'status':'failed','error':f'{type(exc).__name__}: {str(exc)[:300]}'}))
        db.add(Audit(user_id=actor_id,action='workflow.failed',details={'analysis_id':a.id,'error':type(exc).__name__}))
    return a
