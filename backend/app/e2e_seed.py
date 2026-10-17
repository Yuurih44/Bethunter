"""Explicit synthetic data for a disposable CI deployment only. Never public API."""
import os
from sqlalchemy import select
from .config import settings
from .db import SessionLocal
from .models import User,Domain,Analysis
from .security import hash_password
if os.getenv('BETHUNTER_E2E')!='1' or settings().app_env=='production' or settings().auto_setup or settings().auto_official_sync:
    raise SystemExit('Seed E2E requer ambiente descartável explícito, sem automação/coleta externa')
password=os.environ.get('E2E_PASSWORD','')
if len(password)<15:raise SystemExit('Defina E2E_PASSWORD de teste com 15+ caracteres')
with SessionLocal() as db:
    if db.scalar(select(User.id)):raise SystemExit('Seed recusado: banco já contém usuários')
    user=User(email='e2e@example.org',password=hash_password(password),role='admin');db.add(user);db.flush()
    for i in range(55):
        domain=Domain(owner_id=user.id,name=f'fixture-{i:04}.example.org',origin='DEMONSTRAÇÃO E2E');db.add(domain);db.flush()
        db.add(Analysis(domain_id=domain.id,score=0,classification='DEMONSTRAÇÃO E2E — dado sintético',result={'technical':{},'factors':[],'regulation':{'status':'not_verified','reason':'Fixture E2E'},'errors':[],'limitations':['DEMONSTRAÇÃO E2E, não representa investigação real'],'rule_version':'fixture-only','raw_document_ids':[]}))
    db.commit();print('Fixtures sintéticas E2E criadas no banco descartável.')
