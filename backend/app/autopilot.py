"""Default-on, bounded orchestration. Explicit pauses and permissions always win."""
from datetime import timedelta,timezone
from sqlalchemy import select,exists,or_,String,func
from sqlalchemy.exc import IntegrityError
from .config import settings
from .db import SessionLocal
from .models import (User,Domain,Analysis,AnalysisJob,DiscoveryFeed,WorkflowPolicy,
                     SystemSchedule,Schedule,Audit,now)
from .automation import CATALOG,validate_feed_url,enqueue


def enabled(db,owner_id):
    policy=db.get(WorkflowPolicy,owner_id)
    return policy is None or policy.enabled


async def tick_autopilot():
    if not settings().auto_setup:return False
    worked=False
    with SessionLocal() as db:
        # Bounded rotating owner batches; state persists through process restarts.
        owners=db.scalars(select(User).outerjoin(SystemSchedule,SystemSchedule.key=='autopilot:'+User.id.cast(String)).where(
            User.active.is_(True),User.role.in_(['admin','analyst']),
            or_(SystemSchedule.key.is_(None),SystemSchedule.next_run<=now())
        ).order_by(SystemSchedule.next_run.asc().nullsfirst(),User.id).limit(20)).all()
        for owner in owners:
            owner=db.scalar(select(User).where(User.id==owner.id).with_for_update(skip_locked=True))
            if owner is None:continue
            key='autopilot:'+str(owner.id)
            state=db.get(SystemSchedule,key)
            if state and state.next_run.replace(tzinfo=timezone.utc)>now():continue
            if not state:
                state=SystemSchedule(key=key,details={});db.add(state)
            state.next_run=now()+timedelta(minutes=1)
            if not enabled(db,owner.id):
                state.details={'status':'paused','checked':now().isoformat()};continue
            if not db.get(WorkflowPolicy,owner.id):
                db.add(WorkflowPolicy(owner_id=owner.id));db.flush()
            created=0
            for source in CATALOG:
                # Do not broaden an operator's network allowlist or undo a feed pause.
                try:validate_feed_url(source['url'])
                except ValueError:continue
                if db.scalar(select(func.count()).select_from(DiscoveryFeed).where(DiscoveryFeed.owner_id==owner.id))>=10:break
                if not db.scalar(select(DiscoveryFeed.id).where(DiscoveryFeed.owner_id==owner.id,DiscoveryFeed.url==source['url'])):
                    feed=DiscoveryFeed(owner_id=owner.id,name=source['name'],url=source['url'],format=source['format'],
                        permission_reference=source['permission_reference'],enabled=True,auto_analyze=True,interval_hours=1,batch_size=100)
                    try:
                        with db.begin_nested():db.add(feed);db.flush()
                        created+=1
                    except IntegrityError:pass
            candidates=db.scalars(select(Domain).where(Domain.owner_id==owner.id,
                ~exists().where(Analysis.domain_id==Domain.id),
                ~exists().where(AnalysisJob.domain_id==Domain.id)).order_by(Domain.id).limit(100)).all()
            queued=sum(enqueue(db,d) for d in candidates)
            # Existing analyses get a fresh recurring collection rather than a stale verdict.
            historical=db.scalars(select(Domain).where(Domain.owner_id==owner.id,
                exists().where(Analysis.domain_id==Domain.id),
                ~exists().where(Schedule.domain_id==Domain.id)).order_by(Domain.id).limit(100)).all()
            policy=db.get(WorkflowPolicy,owner.id)
            for domain in historical:
                db.add(Schedule(domain_id=domain.id,interval_hours=policy.recurring_hours,enabled=True,automatic=True,next_run=now()))
            retried=0
            jobs=db.scalars(select(AnalysisJob).join(Domain).where(Domain.owner_id==owner.id,
                AnalysisJob.status=='failed',AnalysisJob.attempts<3,AnalysisJob.finished.is_not(None)).order_by(AnalysisJob.finished).limit(100)).all()
            pending=db.scalar(select(func.count()).select_from(AnalysisJob).join(Domain).where(Domain.owner_id==owner.id,AnalysisJob.status.in_(['queued','paused'])))
            for job in jobs:
                if pending>=settings().auto_queue_limit:break
                delay=timedelta(minutes=5*(2**max(0,job.attempts-1)))
                if job.finished.replace(tzinfo=timezone.utc)+delay<=now():
                    job.status='queued';retried+=1;pending+=1
            state.details={'status':'active','checked':now().isoformat(),'feeds_created':created,
                           'queued':queued,'monitoring_added':len(historical),'retried':retried}
            if created or queued or historical or retried:
                db.add(Audit(user_id=owner.id,action='autopilot.reconcile',details=state.details));worked=True
        db.commit()
    return worked
