BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE official_sources (
    id SERIAL NOT NULL, 
    consulted TIMESTAMP WITH TIME ZONE NOT NULL, 
    document_updated TIMESTAMP WITH TIME ZONE, 
    url TEXT NOT NULL, 
    status VARCHAR(30) NOT NULL, 
    error TEXT NOT NULL, 
    digest VARCHAR(64) NOT NULL, 
    entries JSON NOT NULL, 
    PRIMARY KEY (id)
);

CREATE TABLE regulatory_rules (
    id SERIAL NOT NULL, 
    version VARCHAR(80) NOT NULL, 
    effective_from TIMESTAMP WITH TIME ZONE NOT NULL, 
    effective_until TIMESTAMP WITH TIME ZONE, 
    config JSON NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (version)
);

CREATE TABLE users (
    id SERIAL NOT NULL, 
    email VARCHAR(254) NOT NULL, 
    password TEXT NOT NULL, 
    role VARCHAR(20) NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (role IN ('analyst','admin','viewer')), 
    UNIQUE (email)
);

CREATE TABLE audit_logs (
    id SERIAL NOT NULL, 
    user_id INTEGER NOT NULL, 
    created TIMESTAMP WITH TIME ZONE NOT NULL, 
    action VARCHAR(100) NOT NULL, 
    details JSON NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_audit_logs_user_id ON audit_logs (user_id);

CREATE TABLE cases (
    id SERIAL NOT NULL, 
    owner_id INTEGER NOT NULL, 
    title VARCHAR(200) NOT NULL, 
    priority VARCHAR(20) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    notes TEXT NOT NULL, 
    created TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (priority IN ('low','normal','high')), 
    CHECK (status IN ('open','investigating','closed')), 
    FOREIGN KEY(owner_id) REFERENCES users (id)
);

CREATE INDEX ix_cases_owner_id ON cases (owner_id);

CREATE TABLE domains (
    id SERIAL NOT NULL, 
    owner_id INTEGER NOT NULL, 
    name VARCHAR(253) NOT NULL, 
    created TIMESTAMP WITH TIME ZONE NOT NULL, 
    origin VARCHAR(50) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(owner_id) REFERENCES users (id), 
    UNIQUE (owner_id, name)
);

CREATE INDEX ix_domains_name ON domains (name);

CREATE INDEX ix_domains_owner_id ON domains (owner_id);

CREATE TABLE sessions (
    id VARCHAR(64) NOT NULL, 
    user_id INTEGER NOT NULL, 
    csrf VARCHAR(64) NOT NULL, 
    expires TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_sessions_user_id ON sessions (user_id);

CREATE TABLE analyses (
    id SERIAL NOT NULL, 
    domain_id INTEGER NOT NULL, 
    created TIMESTAMP WITH TIME ZONE NOT NULL, 
    score INTEGER NOT NULL, 
    classification VARCHAR(100) NOT NULL, 
    result JSON NOT NULL, 
    review TEXT NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (score >= 0 AND score <= 100), 
    FOREIGN KEY(domain_id) REFERENCES domains (id)
);

CREATE INDEX ix_analyses_created ON analyses (created);

CREATE INDEX ix_analyses_domain_id ON analyses (domain_id);

CREATE TABLE case_domains (
    case_id INTEGER NOT NULL, 
    domain_id INTEGER NOT NULL, 
    PRIMARY KEY (case_id, domain_id), 
    FOREIGN KEY(case_id) REFERENCES cases (id), 
    FOREIGN KEY(domain_id) REFERENCES domains (id)
);

CREATE TABLE reports (
    id SERIAL NOT NULL, 
    case_id INTEGER NOT NULL, 
    created TIMESTAMP WITH TIME ZONE NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    snapshot JSON NOT NULL, 
    content BYTEA NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(case_id) REFERENCES cases (id)
);

CREATE INDEX ix_reports_case_id ON reports (case_id);

CREATE TABLE complaints (
    id SERIAL NOT NULL, 
    report_id INTEGER NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    protocol VARCHAR(200) NOT NULL, 
    confirmation TEXT NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(report_id) REFERENCES reports (id), 
    UNIQUE (report_id)
);

CREATE TABLE evidence (
    id SERIAL NOT NULL, 
    analysis_id INTEGER NOT NULL, 
    collected TIMESTAMP WITH TIME ZONE NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    payload JSON NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(analysis_id) REFERENCES analyses (id)
);

CREATE INDEX ix_evidence_analysis_id ON evidence (analysis_id);

CREATE TABLE indicators (
    id SERIAL NOT NULL, 
    analysis_id INTEGER NOT NULL, 
    kind VARCHAR(50) NOT NULL, 
    value TEXT NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(analysis_id) REFERENCES analyses (id)
);

CREATE INDEX ix_indicators_analysis_id ON indicators (analysis_id);

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

-- Running upgrade 0001 -> 0002

CREATE TABLE schedules (
    id SERIAL NOT NULL, 
    domain_id INTEGER NOT NULL, 
    interval_hours INTEGER NOT NULL, 
    enabled BOOLEAN NOT NULL, 
    next_run TIMESTAMP WITH TIME ZONE NOT NULL, 
    last_run TIMESTAMP WITH TIME ZONE, 
    last_error TEXT NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (interval_hours >= 1 AND interval_hours <= 8760), 
    FOREIGN KEY(domain_id) REFERENCES domains (id), 
    UNIQUE (domain_id)
);

CREATE INDEX ix_schedules_next_run ON schedules (next_run);

UPDATE alembic_version SET version_num='0002' WHERE alembic_version.version_num = '0001';

-- Running upgrade 0002 -> 0003

CREATE TABLE automation_quotas (
    owner_id INTEGER NOT NULL, 
    day VARCHAR(10) NOT NULL, 
    used INTEGER NOT NULL, 
    next_allowed TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (owner_id), 
    FOREIGN KEY(owner_id) REFERENCES users (id)
);

CREATE TABLE discovery_feeds (
    id SERIAL NOT NULL, 
    owner_id INTEGER NOT NULL, 
    name VARCHAR(150) NOT NULL, 
    url VARCHAR(2048) NOT NULL, 
    format VARCHAR(20) NOT NULL, 
    permission_reference TEXT NOT NULL, 
    enabled BOOLEAN NOT NULL, 
    auto_analyze BOOLEAN NOT NULL, 
    interval_hours INTEGER NOT NULL, 
    batch_size INTEGER NOT NULL, 
    cursor INTEGER NOT NULL, 
    next_run TIMESTAMP WITH TIME ZONE NOT NULL, 
    last_error TEXT NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (format IN ('csv','json','domains','hosts')), 
    CHECK (batch_size >= 1 AND batch_size <= 100), 
    CHECK (interval_hours >= 1 AND interval_hours <= 8760), 
    FOREIGN KEY(owner_id) REFERENCES users (id), 
    UNIQUE (owner_id, url)
);

CREATE INDEX ix_discovery_feeds_next_run ON discovery_feeds (next_run);

CREATE INDEX ix_discovery_feeds_owner_id ON discovery_feeds (owner_id);

CREATE TABLE discovery_runs (
    id SERIAL NOT NULL, 
    feed_id INTEGER NOT NULL, 
    created TIMESTAMP WITH TIME ZONE NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    counts JSON NOT NULL, 
    error TEXT NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(feed_id) REFERENCES discovery_feeds (id)
);

CREATE INDEX ix_discovery_runs_feed_id ON discovery_runs (feed_id);

CREATE TABLE analysis_jobs (
    id SERIAL NOT NULL, 
    domain_id INTEGER NOT NULL, 
    feed_id INTEGER, 
    created TIMESTAMP WITH TIME ZONE NOT NULL, 
    finished TIMESTAMP WITH TIME ZONE, 
    status VARCHAR(20) NOT NULL, 
    attempts INTEGER NOT NULL, 
    error TEXT NOT NULL, 
    analysis_id INTEGER, 
    PRIMARY KEY (id), 
    CHECK (status IN ('queued','paused','done','failed')), 
    FOREIGN KEY(analysis_id) REFERENCES analyses (id), 
    FOREIGN KEY(domain_id) REFERENCES domains (id), 
    FOREIGN KEY(feed_id) REFERENCES discovery_feeds (id), 
    UNIQUE (domain_id)
);

CREATE INDEX ix_analysis_jobs_status ON analysis_jobs (status);

CREATE TABLE discovery_candidates (
    feed_id INTEGER NOT NULL, 
    domain_id INTEGER NOT NULL, 
    first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
    last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
    run_id INTEGER NOT NULL, 
    PRIMARY KEY (feed_id, domain_id), 
    FOREIGN KEY(domain_id) REFERENCES domains (id), 
    FOREIGN KEY(feed_id) REFERENCES discovery_feeds (id), 
    FOREIGN KEY(run_id) REFERENCES discovery_runs (id)
);

UPDATE alembic_version SET version_num='0003' WHERE alembic_version.version_num = '0002';

-- Running upgrade 0003 -> 0004

CREATE TABLE auth_throttles (
    key VARCHAR(64) NOT NULL, 
    failures INTEGER NOT NULL, 
    window_start TIMESTAMP WITH TIME ZONE NOT NULL, 
    blocked_until TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (key)
);

CREATE TABLE regulatory_notices (
    id SERIAL NOT NULL, 
    url TEXT NOT NULL, 
    consulted TIMESTAMP WITH TIME ZONE NOT NULL, 
    status VARCHAR(40) NOT NULL, 
    version VARCHAR(80) NOT NULL, 
    effective_from TIMESTAMP WITH TIME ZONE, 
    sha256 VARCHAR(64) NOT NULL, 
    details JSON NOT NULL, 
    error TEXT NOT NULL, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_regulatory_notices_consulted ON regulatory_notices (consulted);

CREATE TABLE system_schedules (
    key VARCHAR(60) NOT NULL, 
    next_run TIMESTAMP WITH TIME ZONE NOT NULL, 
    details JSON NOT NULL, 
    PRIMARY KEY (key)
);

CREATE TABLE invitations (
    id SERIAL NOT NULL, 
    token_hash VARCHAR(64) NOT NULL, 
    email VARCHAR(254) NOT NULL, 
    role VARCHAR(20) NOT NULL, 
    issuer_id INTEGER NOT NULL, 
    expires TIMESTAMP WITH TIME ZONE NOT NULL, 
    used_at TIMESTAMP WITH TIME ZONE, 
    revoked BOOLEAN NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (role IN ('analyst','viewer')), 
    FOREIGN KEY(issuer_id) REFERENCES users (id), 
    UNIQUE (token_hash)
);

CREATE INDEX ix_invitations_email ON invitations (email);

CREATE TABLE mfa_enrollments (
    user_id INTEGER NOT NULL, 
    encrypted_secret TEXT NOT NULL, 
    expires TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (user_id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE mfa_recovery_codes (
    token_hash VARCHAR(64) NOT NULL, 
    user_id INTEGER NOT NULL, 
    used_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (token_hash), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_mfa_recovery_codes_user_id ON mfa_recovery_codes (user_id);

CREATE TABLE workflow_policies (
    owner_id INTEGER NOT NULL, 
    enabled BOOLEAN NOT NULL, 
    recurring_hours INTEGER NOT NULL, 
    create_cases BOOLEAN NOT NULL, 
    prepare_reports BOOLEAN NOT NULL, 
    minimum_score INTEGER NOT NULL, 
    PRIMARY KEY (owner_id), 
    CHECK (minimum_score >= 0 AND minimum_score <= 100), 
    CHECK (recurring_hours >= 1 AND recurring_hours <= 8760), 
    FOREIGN KEY(owner_id) REFERENCES users (id)
);

CREATE TABLE workflow_runs (
    details JSON NOT NULL, 
    analysis_id INTEGER NOT NULL, 
    case_id INTEGER, 
    report_id INTEGER, 
    created TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (analysis_id), 
    FOREIGN KEY(analysis_id) REFERENCES analyses (id), 
    FOREIGN KEY(case_id) REFERENCES cases (id), 
    FOREIGN KEY(report_id) REFERENCES reports (id)
);

ALTER TABLE schedules ADD COLUMN automatic BOOLEAN DEFAULT false NOT NULL;

ALTER TABLE sessions ADD COLUMN created TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL;

ALTER TABLE sessions ADD COLUMN last_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL;

ALTER TABLE sessions ADD COLUMN mfa_verified BOOLEAN DEFAULT false NOT NULL;

ALTER TABLE users ADD COLUMN active BOOLEAN DEFAULT true NOT NULL;

ALTER TABLE users ADD COLUMN mfa_secret TEXT;

ALTER TABLE users ADD COLUMN mfa_enabled BOOLEAN DEFAULT false NOT NULL;

ALTER TABLE users ADD COLUMN mfa_last_counter INTEGER DEFAULT -1 NOT NULL;

UPDATE alembic_version SET version_num='0004' WHERE alembic_version.version_num = '0003';

-- Running upgrade 0004 -> 0005

CREATE INDEX ix_sessions_expires ON sessions (expires);

CREATE INDEX ix_analyses_domain_latest ON analyses (domain_id, id);

CREATE TABLE email_tokens (
    token_hash VARCHAR(64) NOT NULL, 
    user_id INTEGER NOT NULL, 
    purpose VARCHAR(20) NOT NULL, 
    delivery_mode VARCHAR(20) NOT NULL, 
    expires TIMESTAMP WITH TIME ZONE NOT NULL, 
    used_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (token_hash), 
    CHECK (purpose IN ('verify','reset')), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_email_tokens_expires ON email_tokens (expires);

CREATE INDEX ix_email_tokens_user_id ON email_tokens (user_id);

CREATE TABLE mail_jobs (
    id SERIAL NOT NULL, 
    user_id INTEGER NOT NULL, 
    created TIMESTAMP WITH TIME ZONE NOT NULL, 
    encrypted_message TEXT NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    attempts INTEGER NOT NULL, 
    error TEXT NOT NULL, 
    next_run TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_mail_jobs_status ON mail_jobs (status);

CREATE INDEX ix_mail_jobs_user_id ON mail_jobs (user_id);

CREATE TABLE security_events (
    id SERIAL NOT NULL, 
    created TIMESTAMP WITH TIME ZONE NOT NULL, 
    user_id INTEGER, 
    identity_hash VARCHAR(64) NOT NULL, 
    peer VARCHAR(64) NOT NULL, 
    action VARCHAR(80) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_security_events_created ON security_events (created);

CREATE INDEX ix_security_events_identity_hash ON security_events (identity_hash);

CREATE INDEX ix_security_events_user_id ON security_events (user_id);

CREATE TABLE raw_documents (
    id SERIAL NOT NULL, 
    owner_id INTEGER, 
    analysis_id INTEGER, 
    collected TIMESTAMP WITH TIME ZONE NOT NULL, 
    url TEXT NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    content BYTEA NOT NULL, 
    media_type VARCHAR(150) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(analysis_id) REFERENCES analyses (id), 
    FOREIGN KEY(owner_id) REFERENCES users (id)
);

CREATE INDEX ix_raw_documents_analysis_id ON raw_documents (analysis_id);

CREATE INDEX ix_raw_documents_owner_id ON raw_documents (owner_id);

CREATE INDEX ix_raw_documents_sha256 ON raw_documents (sha256);

CREATE TABLE report_jobs (
    automatic BOOLEAN DEFAULT false NOT NULL, 
    id SERIAL NOT NULL, 
    owner_id INTEGER NOT NULL, 
    case_id INTEGER NOT NULL, 
    analysis_id INTEGER, 
    report_id INTEGER, 
    fingerprint VARCHAR(64) NOT NULL, 
    snapshot JSON NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    created TIMESTAMP WITH TIME ZONE NOT NULL, 
    finished TIMESTAMP WITH TIME ZONE, 
    error TEXT NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (status IN ('queued','done','failed')), 
    FOREIGN KEY(analysis_id) REFERENCES analyses (id), 
    FOREIGN KEY(case_id) REFERENCES cases (id), 
    FOREIGN KEY(owner_id) REFERENCES users (id), 
    FOREIGN KEY(report_id) REFERENCES reports (id), 
    UNIQUE (case_id, fingerprint)
);

CREATE INDEX ix_report_jobs_case_id ON report_jobs (case_id);

CREATE INDEX ix_report_jobs_owner_id ON report_jobs (owner_id);

CREATE INDEX ix_report_jobs_status ON report_jobs (status);

ALTER TABLE reports ADD COLUMN archived BOOLEAN DEFAULT false NOT NULL;

ALTER TABLE users ADD COLUMN email_verified_mode VARCHAR(20) DEFAULT '' NOT NULL;

ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT false NOT NULL;

UPDATE alembic_version SET version_num='0005' WHERE alembic_version.version_num = '0004';

COMMIT;

