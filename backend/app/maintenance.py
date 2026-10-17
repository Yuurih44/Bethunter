"""Expire credentials and optionally archive superseded UNCONFIRMED report bytes."""
from datetime import timedelta
from pathlib import Path
from sqlalchemy import select,delete
from .models import (Session,EmailToken,MfaEnrollment,AuthThrottle,SecurityEvent,Report,Complaint,Case,SystemSchedule,Audit,now)
from .db import SessionLocal
from .config import settings

async def tick_maintenance():
    cfg=settings()
    with SessionLocal() as db:
        job=db.get(SystemSchedule,'maintenance')
        if not job:job=SystemSchedule(key='maintenance',next_run=now(),details={});db.add(job);db.flush()
        job=db.scalar(select(SystemSchedule).where(SystemSchedule.key=='maintenance',SystemSchedule.next_run<=now()).with_for_update(skip_locked=True))
        if not job:return False
        db.execute(delete(Session).where(Session.expires<now()))
        db.execute(delete(MfaEnrollment).where(MfaEnrollment.expires<now()))
        db.execute(delete(EmailToken).where(EmailToken.expires<now()-timedelta(days=1)))
        db.execute(delete(AuthThrottle).where(AuthThrottle.window_start<now()-timedelta(days=30)))
        db.execute(delete(SecurityEvent).where(SecurityEvent.created<now()-timedelta(days=90)))
        if cfg.smtp_mode=='local':
            for file in Path(cfg.mail_capture_dir).glob('*.eml'):
                if file.stat().st_mtime<now().timestamp()-7*86400:file.unlink()
        archived=0;backup=db.get(SystemSchedule,'backup')
        from .backups import recent_backup_usable
        recent_backup=bool(backup and recent_backup_usable(backup.details,verify_contents=True)) if cfg.report_retention_enabled else False
        if cfg.report_retention_enabled and recent_backup:
            for case in db.scalars(select(Case)):
                retained=list(db.scalars(select(Report).where(Report.case_id==case.id).order_by(Report.created.desc()).limit(cfg.report_minimum_keep)))
                keep=[r.id for r in retained]
                reports=db.scalars(select(Report).join(Complaint).where(Report.case_id==case.id,Report.id.not_in(keep),Report.archived.is_(False),
                    Report.created<now()-timedelta(days=cfg.report_retention_days),Complaint.status=='prepared')).all()
                for report in reports:
                    report.archived=True;report.content=b'';archived+=1
                    db.add(Audit(user_id=case.owner_id,action='report.archive',details={'report_id':report.id,'sha256':report.sha256,'reason':'retention_with_recent_backup'}))
        job.details={'checked':now().isoformat(),'archived':archived,'backup_required_for_archiving':True}
        job.next_run=now()+timedelta(hours=6);db.commit();return True
