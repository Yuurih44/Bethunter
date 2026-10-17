"""Single scheduler worker; PostgreSQL row locks prevent duplicate simultaneous claims."""
import asyncio
import json
import logging
from datetime import timedelta
from sqlalchemy import select,or_
from .db import SessionLocal
from .models import Schedule, Domain, User, AutoQuota, WorkflowPolicy, now
from .automation import ensure_quota
from .intelligence import analyze
from .collection import persist_analysis
from .automation import tick_feeds, tick_jobs
from .autopilot import tick_autopilot
from .regulation import tick_regulation
from .config import settings
from .report_queue import tick_reports
from .mail import tick_mail
from .maintenance import tick_maintenance
from .backups import tick_backup
from .models import SystemSchedule

log=logging.getLogger("bethunter.worker")

async def tick():
    with SessionLocal() as db:
        today=now().date().isoformat()
        schedule=db.scalar(select(Schedule).join(Domain).outerjoin(AutoQuota,AutoQuota.owner_id==Domain.owner_id).outerjoin(WorkflowPolicy,WorkflowPolicy.owner_id==Domain.owner_id).where(
            Schedule.enabled.is_(True),Schedule.next_run<=now(),
            or_(WorkflowPolicy.owner_id.is_(None),WorkflowPolicy.enabled.is_(True)),
            or_(AutoQuota.owner_id.is_(None),AutoQuota.next_allowed<=now()),
            or_(AutoQuota.owner_id.is_(None),AutoQuota.day!=today,AutoQuota.used<settings().auto_analyses_per_day)
        ).order_by(Schedule.next_run).with_for_update(skip_locked=True,of=Schedule).limit(1))
        if not schedule:
            return False
        d=db.get(Domain,schedule.domain_id)
        owner=db.get(User,d.owner_id)
        schedule.last_run=now()
        if not owner.active or owner.role not in ("admin","analyst"):
            schedule.enabled=False
            schedule.last_error="Usuário sem permissão de coleta"
        else:
            ensure_quota(db,owner.id)
            quota=db.scalar(select(AutoQuota).where(AutoQuota.owner_id==owner.id).with_for_update(skip_locked=True))
            if not quota:return False
            if quota.day!=today:quota.day,quota.used=today,0
            if quota.used>=settings().auto_analyses_per_day or quota.next_allowed.replace(tzinfo=now().tzinfo)>now():return False
            quota.used+=1
            try:
                result=await asyncio.wait_for(analyze(db,d.name),60)
                with db.begin_nested():
                    persist_analysis(db,d,result,owner.id,scheduled=True)
                schedule.last_error="; ".join(result.get("errors",[]))[:2000]
            except Exception as exc:
                schedule.last_error=f"{type(exc).__name__}: {str(exc)[:500]}"
            quota.next_allowed=now()+timedelta(seconds=settings().auto_analysis_delay_seconds)
        schedule.next_run=now()+timedelta(hours=schedule.interval_hours)
        db.commit()
        log.info(json.dumps({"event":"schedule.executed","schedule_id":schedule.id,"error":schedule.last_error}))
        return True

async def run_cycle(prefer_jobs=False):
    worked=False
    collection=(tick_jobs,tick) if prefer_jobs else (tick,tick_jobs)
    for operation in (tick_mail,tick_reports,tick_autopilot,tick_regulation,tick_feeds,*collection,tick_maintenance,tick_backup):
        with SessionLocal() as db:
            pulse=db.get(SystemSchedule,'worker_heartbeat')
            if not pulse:pulse=SystemSchedule(key='worker_heartbeat');db.add(pulse)
            pulse.next_run=now()+timedelta(minutes=5);pulse.details={'checked':now().isoformat(),'stage':operation.__name__};db.commit()
        try:
            worked=(await operation()) or worked
        except Exception:
            log.exception("worker_tick_failed: %s",operation.__name__)
    return worked


async def main():
    prefer_jobs=False
    while True:
        try:
            worked=await run_cycle(prefer_jobs)
        except Exception:
            log.exception("worker_cycle_failed; retry in 30 seconds")
            worked=False
        prefer_jobs=not prefer_jobs
        if not worked:
            await asyncio.sleep(30)

if __name__=="__main__":
    logging.basicConfig(level=logging.INFO,format="%(message)s")
    asyncio.run(main())
