"""Bounded discovery from licensed feeds, provenance, durable queue and UTC quotas."""
import asyncio
import csv
import hashlib
import io
import json
from datetime import timedelta, timezone
from urllib.parse import urlsplit
from sqlalchemy import select, func, or_
from sqlalchemy.exc import IntegrityError
from . import network
from .config import settings
from .db import SessionLocal
from .models import (DiscoveryFeed, DiscoveryRun, DiscoveryCandidate, AnalysisJob,
                     AutoQuota, Domain, Analysis, Audit, User, WorkflowPolicy, now)
from .intelligence import analyze
from .collection import persist_analysis

CATALOG = [{
    'name': 'StevenBlack — Gambling only (comunitária, internacional)',
    'url': 'https://raw.githubusercontent.com/StevenBlack/hosts/master/alternates/gambling-only/hosts',
    'format': 'hosts',
    'permission_reference': 'MIT; StevenBlack/hosts e fontes gambling MIT documentadas em https://github.com/StevenBlack/hosts/blob/master/alternates/gambling-only/readme.md ; licença https://github.com/StevenBlack/hosts/blob/master/license.txt',
    'homepage': 'https://github.com/StevenBlack/hosts/tree/master/alternates/gambling-only',
    'limitation': 'Lista comunitária internacional de conteúdo de apostas; não comprova operação no Brasil, autorização ou irregularidade. Inclui fontes voltadas a outros países.',
}]


def allowed_hosts():
    return {h.strip().lower() for h in settings().discovery_allowed_hosts.split(',') if h.strip()}


def validate_feed_url(url):
    host = network.normalize(url)
    parts = urlsplit(url)
    if parts.scheme != 'https' or parts.fragment or host not in allowed_hosts():
        raise ValueError('Fonte exige HTTPS e host permitido em DISCOVERY_ALLOWED_HOSTS, sem fragmento')
    return url


def parse_feed(raw, format):
    text = raw.decode('utf-8-sig', errors='strict')
    if format == 'csv':
        rows = csv.DictReader(io.StringIO(text))
        if not rows.fieldnames or 'domain' not in rows.fieldnames:
            raise ValueError('CSV requer coluna domain')
        values = [row.get('domain') for row in rows]
    elif format == 'json':
        values = json.loads(text)
        if not isinstance(values, list):
            raise ValueError('JSON requer array de strings ou objetos com domain')
        values = [v.get('domain') if isinstance(v, dict) else v for v in values]
    elif format in ('domains', 'hosts'):
        values = []
        for line in text.splitlines():
            line = line.split('#', 1)[0].strip()
            if not line:
                continue
            if format == 'hosts':
                fields = line.split()
                # These are dataset addresses, not listener bindings.
                if len(fields) < 2 or fields[0] not in ('0.0.0.0', '127.0.0.1', '::'):  # nosec B104
                    raise ValueError('Formato hosts não reconhecido')
                values.extend(fields[1:])
            else:
                values.append(line)
    else:
        raise ValueError('Formato desconhecido')
    if len(values) > 100000:
        raise ValueError('Fonte excede 100.000 registros')
    names, errors, seen = [], 0, set()
    for value in values:
        try:
            if not isinstance(value, str):
                raise ValueError('Domínio não textual')
            name = network.normalize(value)
            if name not in seen:
                names.append(name)
                seen.add(name)
        except (ValueError, UnicodeError):
            errors += 1
    if not names:
        raise ValueError('Fonte sem domínios válidos; formato pode ter mudado')
    return names, errors


def ensure_quota(db, owner_id):
    if db.get(AutoQuota, owner_id) is None:
        try:
            with db.begin_nested():
                db.add(AutoQuota(owner_id=owner_id, day=now().date().isoformat(), used=0, next_allowed=now()))
                db.flush()
        except IntegrityError:
            pass  # Another transaction created the per-owner quota.


def enqueue(db, domain, feed_id=None):
    if db.scalar(select(Analysis.id).where(Analysis.domain_id == domain.id).limit(1)):
        return False
    if db.scalar(select(AnalysisJob.id).where(AnalysisJob.domain_id == domain.id)):
        return False
    ensure_quota(db, domain.owner_id)
    db.scalar(select(AutoQuota).where(AutoQuota.owner_id == domain.owner_id).with_for_update())
    pending = db.scalar(select(func.count()).select_from(AnalysisJob).join(Domain).where(
        Domain.owner_id == domain.owner_id, AnalysisJob.status.in_(['queued', 'paused'])))
    if pending >= settings().auto_queue_limit:
        return False
    try:
        with db.begin_nested():
            db.add(AnalysisJob(domain_id=domain.id, feed_id=feed_id))
            db.flush()
    except IntegrityError:
        return False
    return True


def ingest(db, feed, names, invalid, digest):
    run = DiscoveryRun(feed_id=feed.id, status='success', sha256=digest, counts={})
    db.add(run)
    db.flush()
    # Cursor rotates bounded batches instead of permanently inspecting only the first rows.
    offset = feed.cursor % len(names)
    batch = (names[offset:] + names[:offset])[:feed.batch_size]
    added = duplicates = queued = 0
    for name in batch:
        domain = db.scalar(select(Domain).where(Domain.owner_id == feed.owner_id, Domain.name == name))
        if not domain:
            try:
                with db.begin_nested():
                    domain = Domain(owner_id=feed.owner_id, name=name, origin=f'feed:{feed.id}')
                    db.add(domain)
                    db.flush()
                added += 1
            except IntegrityError:
                domain = db.scalar(select(Domain).where(Domain.owner_id == feed.owner_id, Domain.name == name))
                duplicates += 1
        else:
            duplicates += 1
        candidate = db.get(DiscoveryCandidate, (feed.id, domain.id))
        if candidate:
            candidate.last_seen = now()
            candidate.run_id = run.id
        else:
            db.add(DiscoveryCandidate(feed_id=feed.id, domain_id=domain.id, run_id=run.id))
        if feed.auto_analyze and enqueue(db, domain, feed.id):
            queued += 1
    feed.cursor = (offset + len(batch)) % len(names)
    run.counts = {'available':len(names), 'processed':len(batch), 'added':added,
                  'duplicates':duplicates, 'queued':queued, 'invalid':invalid}
    return run


async def tick_feeds():
    with SessionLocal() as db:
        feed = db.scalar(select(DiscoveryFeed).outerjoin(WorkflowPolicy,WorkflowPolicy.owner_id==DiscoveryFeed.owner_id).where(
            or_(WorkflowPolicy.owner_id.is_(None),WorkflowPolicy.enabled.is_(True)),DiscoveryFeed.enabled.is_(True),
            DiscoveryFeed.next_run <= now()).order_by(DiscoveryFeed.next_run).with_for_update(skip_locked=True,of=DiscoveryFeed).limit(1))
        if not feed:
            return False
        owner = db.get(User, feed.owner_id)
        try:
            if not owner.active or owner.role not in ('analyst', 'admin'):
                feed.enabled = False
                raise ValueError('Usuário sem permissão de descoberta')
            validate_feed_url(feed.url)  # Revalidate after deployment allowlist changes.
            async with network.semaphore:
                raw, hops, headers = await asyncio.wait_for(network.fetch(feed.url,
                    max_bytes=2_000_000, allowed_hosts=allowed_hosts(), https_only=True), 30)
            names, invalid = parse_feed(raw, feed.format)
            with db.begin_nested():
                run = ingest(db, feed, names, invalid, hashlib.sha256(raw).hexdigest())
            feed.last_error = ''
            db.add(Audit(user_id=feed.owner_id, action='discovery.feed', details={'feed_id':feed.id, 'run_id':run.id, **run.counts}))
        except Exception as exc:
            feed.last_error = f'{type(exc).__name__}: {str(exc)[:400]}'
            db.add(DiscoveryRun(feed_id=feed.id, status='failed', error=feed.last_error, counts={}))
            db.add(Audit(user_id=feed.owner_id, action='discovery.feed.failed', details={'feed_id':feed.id, 'error':feed.last_error}))
        feed.next_run = now() + timedelta(hours=feed.interval_hours)
        db.commit()
        return True


async def tick_jobs():
    with SessionLocal() as db:
        today = now().date().isoformat()
        row = db.execute(select(AnalysisJob, Domain).join(Domain).join(AutoQuota, AutoQuota.owner_id == Domain.owner_id).outerjoin(WorkflowPolicy,WorkflowPolicy.owner_id==Domain.owner_id).where(
            or_(WorkflowPolicy.owner_id.is_(None),WorkflowPolicy.enabled.is_(True)),AnalysisJob.status == 'queued', AutoQuota.next_allowed <= now(),
            or_(AutoQuota.day != today, AutoQuota.used < settings().auto_analyses_per_day)
        ).order_by(AnalysisJob.id).with_for_update(skip_locked=True, of=AnalysisJob).limit(1)).first()
        if not row:
            return False
        job, domain = row
        quota = db.scalar(select(AutoQuota).where(AutoQuota.owner_id == domain.owner_id).with_for_update(skip_locked=True))
        if quota is None:
            return False
        if quota.day != today:
            quota.day, quota.used = today, 0
        # Recheck under quota lock to prevent simultaneous workers exceeding the limit.
        if quota.used >= settings().auto_analyses_per_day or quota.next_allowed.replace(tzinfo=timezone.utc) > now():
            return False
        owner = db.get(User, domain.owner_id)
        if not owner.active or owner.role not in ('analyst','admin'):
            job.status, job.error = 'paused', 'Permissão de coleta revogada'
            db.commit()
            return True
        job.attempts += 1
        quota.used += 1
        try:
            if job.attempts == 1 and db.scalar(select(Analysis.id).where(Analysis.domain_id == domain.id).limit(1)):
                job.status, job.error = 'done', 'Domínio já analisado; coleta duplicada evitada'
            else:
                result = await asyncio.wait_for(analyze(db, domain.name),60)
                if job.feed_id:
                    feed=db.get(DiscoveryFeed,job.feed_id)
                    candidate=db.get(DiscoveryCandidate,(job.feed_id,domain.id))
                    observed=db.get(DiscoveryRun,candidate.run_id) if candidate else None
                    result['discovery']={
                        'method':'public_feed','feed_id':feed.id,'name':feed.name,'source_url':feed.url,
                        'permission_reference':feed.permission_reference,
                        'first_seen':candidate.first_seen.isoformat() if candidate else None,
                        'last_seen':candidate.last_seen.isoformat() if candidate else None,
                        'observed_run_id':observed.id if observed else None,
                        'document_sha256':observed.sha256 if observed else None,
                        'limitation':'Fonte de candidatos, sem comprovação de operação no Brasil, autorização ou irregularidade.'}
                else:
                    result['discovery']={'method':'inventory_queue','origin':domain.origin,
                        'limitation':'Domínio enfileirado a partir do inventário do analista; origem não pontua risco.'}
                with db.begin_nested():
                    analysis = persist_analysis(db, domain, result, owner.id)
                job.analysis_id = analysis.id
                job.error = '; '.join(result.get('errors',[]))[:2000]
                job.status = 'failed' if result.get('errors') and not result.get('technical',{}).get('ips') else 'done'
        except Exception as exc:
            job.status, job.error = 'failed', f'{type(exc).__name__}: {str(exc)[:400]}'
        job.finished = now()
        quota.next_allowed = now() + timedelta(seconds=settings().auto_analysis_delay_seconds)
        db.add(Audit(user_id=owner.id,action='discovery.job',details={'job_id':job.id,'status':job.status,'analysis_id':job.analysis_id,'error':job.error}))
        db.commit()
        return True
