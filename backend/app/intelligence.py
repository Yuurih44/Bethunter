import asyncio
import hashlib
import json
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup
from sqlalchemy import select
from . import network
from .models import OfficialSource, Rule, now
from .config import settings
from .providers import RIPEstatProvider
from .regulation import context,verdict

OFFICIAL_URL = "https://www.gov.br/fazenda/pt-br/composicao/orgaos/secretaria-de-premios-e-apostas/lista-de-empresas/empresas-autorizadas-1/empresas-autorizadas"
DEFAULT_WEIGHTS = {"betting_content":25, "betting_mentions":10, "cross_domain_redirect":15}
LABELS = ["Sem indicadores relevantes", "Requer investigação", "Suspeito", "Evidências relevantes de possível irregularidade", "Situação regulatória não verificada"]

def score(factors, weights):
    return min(100, sum(weights.get(f["key"], 0) for f in factors))

def parse_source(data):
    soup = BeautifulSoup(data, "html.parser")
    entries = []
    for row in soup.select("table tr"):
        cells = [c.get_text(" ", strip=True) for c in row.select("td")]
        if len(cells) < 5:
            continue
        domains = re.findall(r"(?<![\w.-])(?:[a-z0-9-]+\.)+bet\.br(?![\w.-])", " ".join(cells).lower())
        for domain in domains:
            entries.append({"domain":domain,"company":cells[1],"cnpj":cells[2],"act":" ".join(cells[5:]),"status":"listed_in_document"})
    updated = None
    stamp = soup.select_one(".documentModified .value")
    if stamp:
        match = re.search(r"(\d{2}/\d{2}/\d{4})",stamp.get_text())
        if match:
            updated = datetime.strptime(match[1], "%d/%m/%Y").replace(tzinfo=timezone.utc)
    if not entries:
        raise ValueError("Formato oficial não reconhecido; nenhuma empresa importada")
    return entries, updated

async def sync_source(db,commit=True):
    source = OfficialSource(url=settings().official_source_url, status="failed", entries=[])
    try:
        if network.normalize(source.url) not in ("www.gov.br", "gov.br"):
            raise ValueError("Fonte deve pertencer ao portal oficial gov.br")
        async with network.semaphore:
            data, hops, headers = await asyncio.wait_for(network.fetch(source.url,allowed_hosts={"www.gov.br","gov.br"},https_only=True),30)
        if any(network.normalize(h["url"]) not in ("www.gov.br", "gov.br") for h in hops):
            raise ValueError("Fonte redirecionou para fora do portal oficial")
        from .documents import preserve_official
        document_id=preserve_official(db,source.url,data)
        entries, updated = parse_source(data)
        for entry in entries:entry['document_id']=document_id
        source.entries, source.document_updated = entries, updated
        source.digest = hashlib.sha256(data).hexdigest()
        source.status = "imported" if updated else "undated"
    except Exception as exc:
        source.error = f"{type(exc).__name__}: {str(exc)[:300]}"
    db.add(source)
    if commit:db.commit();db.refresh(source)
    else:db.flush()
    return source

def regulatory(db, domain):
    source = db.scalar(select(OfficialSource).order_by(OfficialSource.id.desc()).limit(1))
    result = {"status":"not_verified", "reason":"Nenhuma consulta oficial disponível", "source_id":source.id if source else None}
    ctx=context(db)
    result['normative_context']=ctx
    if ctx.get('verified'):
        result.update(status='restricted_framework',reason='A SPA informa restrição geral. Eventual presença em lista histórica não confirma autorização atual.')
        if source:
            result['historical_entry']=next((e for e in source.entries if e.get('domain')==domain),None)
        return result
    if settings().regulatory_require_context:
        result['reason']=ctx['reason']
        return result
    if not source:
        return result
    result.update(url=source.url, consulted=source.consulted.isoformat(), document_sha256=source.digest, document_updated=source.document_updated.isoformat() if source.document_updated else None)
    cutoff = now() - timedelta(days=settings().source_max_age_days)
    if source.status != "imported" or not source.document_updated or source.document_updated.replace(tzinfo=timezone.utc) < cutoff or source.consulted.replace(tzinfo=timezone.utc) < cutoff or source.document_updated.replace(tzinfo=timezone.utc) > now():
        result["reason"] = "Fonte indisponível, sem data verificável ou desatualizada"
        return result
    match = next((e for e in source.entries if e["domain"] == domain), None)
    result.update(status="listed" if match else "not_found", entry=match, reason="Correspondência exata em documento recente; requer revisão de vigência e escopo" if match else "Domínio não localizado nesta fonte federal; ausência não comprova irregularidade")
    return result

def current_rule(db):
    rules = db.scalars(select(Rule).where(Rule.effective_from <= now()).order_by(Rule.effective_from.desc())).all()
    return next((r for r in rules if not r.effective_until or r.effective_until.replace(tzinfo=timezone.utc) > now()), None)

async def analyze(db, domain):
    factors, errors, technical = [], [], {}
    raw_documents=[]
    async with network.semaphore:
        try:
            ips = await network.resolve(domain)
            technical["ips"] = ips
        except Exception as exc:
            errors.append(f"DNS: {type(exc).__name__}: {str(exc)[:200]}")
            ips = []
        if ips:
            if settings().enrich_asn:
                try:
                    technical['infrastructure']=await RIPEstatProvider().lookup(ips[0])
                except Exception as exc:
                    errors.append(f"ASN: {type(exc).__name__}: {str(exc)[:200]}")
            else:
                technical['infrastructure']={'status':'disabled','reason':'Ative ENRICH_ASN para consultar a API pública RIPEstat'}
            try:
                technical["tls"] = await network.certificate(domain, ips[0])
            except Exception as exc:
                errors.append(f"TLS: {type(exc).__name__}")
            try:
                data, hops, headers = await asyncio.wait_for(network.fetch("https://"+domain),30)
                technical.update(hops=hops, content_sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
                soup=BeautifulSoup(data, "html.parser")
                text = soup.get_text(" ",strip=True).lower()
                raw_documents.append({'url':hops[-1]['url'] if hops else 'https://'+domain,'content':data,'media_type':headers.get('content-type','text/html')})
                actions=[phrase for phrase in ('depositar','faça sua aposta','apostar agora','realizar aposta','sacar saldo') if phrase in text]
                informational=bool(soup.find('article')) and not actions
                technical['activity_context']='operator_signals' if actions else 'informational' if informational else 'unconfirmed'
                technical['operator_signals']=actions
                terms = [x for x in ("cassino", "casino", "apostas", "sportsbook", "roleta") if re.search(r"\b"+x+r"\b", text)]
                technical["matched_terms"] = terms
                technical["text_excerpt"] = text[:8000]
                if terms:
                    factors.append({'key':'betting_content' if actions else 'betting_mentions',
                        'explanation':('Termos e ações de operação observados: ' if actions else 'Menções sem atividade operacional confirmada: ')+', '.join(terms)})
                if any(network.normalize(h["url"]) != domain for h in hops):
                    factors.append({"key":"cross_domain_redirect","explanation":"Redirecionamento para outro domínio; pode ser legítimo"})
            except Exception as exc:
                errors.append(f"HTTP: {type(exc).__name__}: {str(exc)[:200]}")
    technical["collection_status"]="complete" if "content_sha256" in technical else "incomplete"
    regulation = regulatory(db, domain)
    rule = current_rule(db)
    weights = {**DEFAULT_WEIGHTS,**rule.config.get("weights",{})} if rule else DEFAULT_WEIGHTS
    if technical.get("activity_context")=="informational":weights={**weights,"betting_mentions":0}
    total = score(factors, weights)
    classification = LABELS[4] if regulation["status"] == "not_verified" else LABELS[3 if total >= 75 else 2 if total >= 50 else 1 if total else 0]
    if technical["collection_status"]=="incomplete" and regulation["status"]!="not_verified":
        classification=LABELS[1] if total<50 else classification
    return {"_raw_documents":raw_documents,"score":total,"classification":classification,"factors":[dict(f,weight=weights.get(f["key"],0)) for f in factors],"technical":technical,"regulation":regulation,"verdict":verdict(regulation,technical),"errors":errors,"rule_version":rule.version if rule else "technical-v2", "weights":weights,"limitations":["Score indica prioridade de investigação, não probabilidade de crime.","Coleta pontual; conteúdo dinâmico, geolocalizado e histórico anterior não são cobertos.","Infraestrutura compartilhada não comprova operador comum.","Não há detecção automática de imitação de marca no MVP."]}
