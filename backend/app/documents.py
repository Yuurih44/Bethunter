import hashlib
from sqlalchemy import select,func
from .models import RawDocument
from .config import settings

def preserve_official(db,url,content,media_type='text/html'):
    digest=hashlib.sha256(content).hexdigest()
    existing=db.scalar(select(RawDocument).where(RawDocument.owner_id.is_(None),RawDocument.sha256==digest,RawDocument.url==url))
    if existing:return existing.id
    used=db.scalar(select(func.coalesce(func.sum(func.length(RawDocument.content)),0)).where(RawDocument.owner_id.is_(None)))
    if used+len(content)>settings().raw_document_storage_limit_mb*1_000_000:return None
    doc=RawDocument(owner_id=None,url=url,sha256=digest,content=content,media_type=media_type[:150]);db.add(doc);db.flush();return doc.id
