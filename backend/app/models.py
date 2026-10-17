from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, JSON, UniqueConstraint, CheckConstraint, LargeBinary, Boolean, text, func, Index
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def now():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default="analyst")
    email_verified_mode: Mapped[str] = mapped_column(String(20),default='',server_default=text("''"))
    email_verified: Mapped[bool] = mapped_column(Boolean,default=False,server_default=text('false'))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text('true'))
    mfa_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text('false'))
    mfa_last_counter: Mapped[int] = mapped_column(Integer, default=-1, server_default=text('-1'))
    __table_args__ = (CheckConstraint("role IN ('analyst','admin','viewer')"),)

class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    csrf: Mapped[str] = mapped_column(String(64))
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True),index=True)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, server_default=func.now())
    mfa_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text('false'))

class Domain(Base):
    __tablename__ = "domains"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(253), index=True)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    origin: Mapped[str] = mapped_column(String(50), default="manual")
    __table_args__ = (UniqueConstraint("owner_id", "name"),)

class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[int] = mapped_column(primary_key=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey("domains.id"), index=True)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    score: Mapped[int] = mapped_column(Integer)
    classification: Mapped[str] = mapped_column(String(100))
    result: Mapped[dict] = mapped_column(JSON)
    review: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (CheckConstraint("score >= 0 AND score <= 100"),Index("ix_analyses_domain_latest","domain_id","id"))

class Indicator(Base):
    __tablename__ = "indicators"
    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"), index=True)
    kind: Mapped[str] = mapped_column(String(50))
    value: Mapped[str] = mapped_column(Text)

class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"), index=True)
    collected: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    sha256: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)

class OfficialSource(Base):
    __tablename__ = "official_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    consulted: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    document_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30))
    error: Mapped[str] = mapped_column(Text, default="")
    digest: Mapped[str] = mapped_column(String(64), default="")
    entries: Mapped[list] = mapped_column(JSON, default=list)

class Rule(Base):
    __tablename__ = "regulatory_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(String(80), unique=True)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    config: Mapped[dict] = mapped_column(JSON)

class Case(Base):
    __tablename__ = "cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    priority: Mapped[str] = mapped_column(String(20), default="normal")
    status: Mapped[str] = mapped_column(String(20), default="open")
    notes: Mapped[str] = mapped_column(Text, default="")
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (CheckConstraint("status IN ('open','investigating','closed')"), CheckConstraint("priority IN ('low','normal','high')"))

class CaseDomain(Base):
    __tablename__ = "case_domains"
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), primary_key=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey("domains.id"), primary_key=True)

class Report(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    archived: Mapped[bool] = mapped_column(Boolean,default=False,server_default=text('false'))
    sha256: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict] = mapped_column(JSON)
    content: Mapped[bytes] = mapped_column(LargeBinary)

class Complaint(Base):
    __tablename__ = "complaints"
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="prepared")
    protocol: Mapped[str] = mapped_column(String(200), default="")
    confirmation: Mapped[str] = mapped_column(Text, default="")

class Audit(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    action: Mapped[str] = mapped_column(String(100))
    details: Mapped[dict] = mapped_column(JSON)


class Schedule(Base):
    __tablename__ = "schedules"
    id: Mapped[int] = mapped_column(primary_key=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey("domains.id"), unique=True)
    interval_hours: Mapped[int] = mapped_column(Integer, default=24)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    last_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    automatic: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text('false'))
    last_error: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (CheckConstraint("interval_hours >= 1 AND interval_hours <= 8760"),)

class DiscoveryFeed(Base):
    __tablename__ = 'discovery_feeds'
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    name: Mapped[str] = mapped_column(String(150))
    url: Mapped[str] = mapped_column(String(2048))
    format: Mapped[str] = mapped_column(String(20))
    permission_reference: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_analyze: Mapped[bool] = mapped_column(Boolean, default=True)
    interval_hours: Mapped[int] = mapped_column(Integer, default=24)
    batch_size: Mapped[int] = mapped_column(Integer, default=50)
    cursor: Mapped[int] = mapped_column(Integer, default=0)
    next_run: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    last_error: Mapped[str] = mapped_column(Text, default='')
    __table_args__ = (UniqueConstraint('owner_id','url'), CheckConstraint("format IN ('csv','json','domains','hosts')"), CheckConstraint('interval_hours >= 1 AND interval_hours <= 8760'), CheckConstraint('batch_size >= 1 AND batch_size <= 100'))

class DiscoveryRun(Base):
    __tablename__ = 'discovery_runs'
    id: Mapped[int] = mapped_column(primary_key=True)
    feed_id: Mapped[int] = mapped_column(ForeignKey('discovery_feeds.id'), index=True)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    status: Mapped[str] = mapped_column(String(20))
    sha256: Mapped[str] = mapped_column(String(64), default='')
    counts: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default='')

class DiscoveryCandidate(Base):
    __tablename__ = 'discovery_candidates'
    feed_id: Mapped[int] = mapped_column(ForeignKey('discovery_feeds.id'), primary_key=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey('domains.id'), primary_key=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    run_id: Mapped[int] = mapped_column(ForeignKey('discovery_runs.id'))

class AutoQuota(Base):
    __tablename__ = 'automation_quotas'
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    day: Mapped[str] = mapped_column(String(10))
    used: Mapped[int] = mapped_column(Integer, default=0)
    next_allowed: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class AnalysisJob(Base):
    __tablename__ = 'analysis_jobs'
    id: Mapped[int] = mapped_column(primary_key=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey('domains.id'), unique=True)
    feed_id: Mapped[int | None] = mapped_column(ForeignKey('discovery_feeds.id'), nullable=True)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='queued', index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default='')
    analysis_id: Mapped[int | None] = mapped_column(ForeignKey('analyses.id'), nullable=True)
    __table_args__ = (CheckConstraint("status IN ('queued','paused','done','failed')"),)

class Invitation(Base):
    __tablename__ = 'invitations'
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    email: Mapped[str] = mapped_column(String(254), index=True)
    role: Mapped[str] = mapped_column(String(20), default='analyst')
    issuer_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (CheckConstraint("role IN ('analyst','viewer')"),)

class AuthThrottle(Base):
    __tablename__ = 'auth_throttles'
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class MfaEnrollment(Base):
    __tablename__ = 'mfa_enrollments'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    encrypted_secret: Mapped[str] = mapped_column(Text)
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class MfaRecovery(Base):
    __tablename__ = 'mfa_recovery_codes'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class RegulatoryNotice(Base):
    __tablename__ = 'regulatory_notices'
    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(Text)
    consulted: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    status: Mapped[str] = mapped_column(String(40))
    version: Mapped[str] = mapped_column(String(80), default='unrecognized')
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), default='')
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default='')

class SystemSchedule(Base):
    __tablename__ = 'system_schedules'
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    next_run: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    details: Mapped[dict] = mapped_column(JSON, default=dict)

class WorkflowPolicy(Base):
    __tablename__ = 'workflow_policies'
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    recurring_hours: Mapped[int] = mapped_column(Integer, default=24)
    create_cases: Mapped[bool] = mapped_column(Boolean, default=True)
    prepare_reports: Mapped[bool] = mapped_column(Boolean, default=True)
    minimum_score: Mapped[int] = mapped_column(Integer, default=25)
    __table_args__ = (CheckConstraint('recurring_hours >= 1 AND recurring_hours <= 8760'),CheckConstraint('minimum_score >= 0 AND minimum_score <= 100'))

class WorkflowRun(Base):
    __tablename__ = 'workflow_runs'
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    analysis_id: Mapped[int] = mapped_column(ForeignKey('analyses.id'), primary_key=True)
    case_id: Mapped[int | None] = mapped_column(ForeignKey('cases.id'), nullable=True)
    report_id: Mapped[int | None] = mapped_column(ForeignKey('reports.id'), nullable=True)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class EmailToken(Base):
    __tablename__='email_tokens'
    token_hash: Mapped[str]=mapped_column(String(64),primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    purpose: Mapped[str]=mapped_column(String(20))
    delivery_mode: Mapped[str]=mapped_column(String(20),default='')
    expires: Mapped[datetime]=mapped_column(DateTime(timezone=True),index=True)
    used_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    __table_args__=(CheckConstraint("purpose IN ('verify','reset')"),)

class MailJob(Base):
    __tablename__='mail_jobs'
    id: Mapped[int]=mapped_column(primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    created: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    encrypted_message: Mapped[str]=mapped_column(Text)
    status: Mapped[str]=mapped_column(String(20),default='queued',index=True)
    attempts: Mapped[int]=mapped_column(Integer,default=0)
    error: Mapped[str]=mapped_column(Text,default='')
    next_run: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class ReportJob(Base):
    __tablename__='report_jobs'
    automatic: Mapped[bool]=mapped_column(Boolean,default=False,server_default=text('false'))
    id: Mapped[int]=mapped_column(primary_key=True)
    owner_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    case_id: Mapped[int]=mapped_column(ForeignKey('cases.id'),index=True)
    analysis_id: Mapped[int|None]=mapped_column(ForeignKey('analyses.id'),nullable=True)
    report_id: Mapped[int|None]=mapped_column(ForeignKey('reports.id'),nullable=True)
    fingerprint: Mapped[str]=mapped_column(String(64))
    snapshot: Mapped[dict]=mapped_column(JSON)
    status: Mapped[str]=mapped_column(String(20),default='queued',index=True)
    created: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    finished: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    error: Mapped[str]=mapped_column(Text,default='')
    __table_args__=(UniqueConstraint('case_id','fingerprint'),CheckConstraint("status IN ('queued','done','failed')"))

class RawDocument(Base):
    __tablename__='raw_documents'
    id: Mapped[int]=mapped_column(primary_key=True)
    owner_id: Mapped[int|None]=mapped_column(ForeignKey('users.id'),nullable=True,index=True)
    analysis_id: Mapped[int|None]=mapped_column(ForeignKey('analyses.id'),nullable=True,index=True)
    collected: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    url: Mapped[str]=mapped_column(Text)
    sha256: Mapped[str]=mapped_column(String(64),index=True)
    content: Mapped[bytes]=mapped_column(LargeBinary)
    media_type: Mapped[str]=mapped_column(String(150),default='application/octet-stream')

class SecurityEvent(Base):
    __tablename__='security_events'
    id: Mapped[int]=mapped_column(primary_key=True)
    created: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,index=True)
    user_id: Mapped[int|None]=mapped_column(ForeignKey('users.id'),nullable=True,index=True)
    identity_hash: Mapped[str]=mapped_column(String(64),index=True)
    peer: Mapped[str]=mapped_column(String(64),default='')
    action: Mapped[str]=mapped_column(String(80))
