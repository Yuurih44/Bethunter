from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://bethunter_runtime@db:5432/bethunter"
    origin: str = "http://localhost:8080"
    cookie_secure: bool = True
    registration_enabled: bool = True
    registration_mode: Literal['invite','open','closed'] = 'invite'
    auth_encryption_key: str = ''
    require_mfa_admin: bool = True
    session_hours: int = Field(default=8, ge=1, le=24)
    session_idle_minutes: int = Field(default=30, ge=5, le=120)
    app_env: Literal['development','production'] = 'development'
    smtp_mode: Literal['disabled','local','smtp']='disabled'
    mail_capture_dir: str='mail-capture'
    smtp_host: str='127.0.0.1'
    smtp_port: int=Field(default=1025,ge=1,le=65535)
    smtp_username: str=''
    smtp_password: str=''
    smtp_from: str='BetHunter <no-reply@bethunter.local>'
    smtp_starttls: bool=True
    require_email_verification: bool=False
    raw_document_storage_limit_mb: int=Field(default=100,ge=1,le=10000)
    report_max_snapshot_bytes: int=Field(default=2_000_000,ge=10000,le=10_000_000)
    report_max_pdf_bytes: int=Field(default=5_000_000,ge=10000,le=20_000_000)
    report_storage_limit_mb: int=Field(default=100,ge=1,le=10000)
    report_max_history: int=Field(default=50,ge=1,le=500)
    report_retention_days: int=Field(default=90,ge=7,le=3650)
    report_minimum_keep: int=Field(default=3,ge=1,le=100)
    report_retention_enabled: bool=False
    backup_enabled: bool=True
    backup_dir: str='backups'
    backup_encryption_key: str=''
    backup_interval_hours: int=Field(default=24,ge=1,le=168)
    backup_keep: int=Field(default=7,ge=2,le=100)
    backup_max_bytes: int=Field(default=256_000_000,ge=1000000,le=1_000_000_000)
    backlog_alert_hours: int=Field(default=48,ge=1,le=720)
    trusted_proxy_ips: str=''
    auto_setup: bool = True
    auto_official_sync: bool = True
    official_sync_hours: int = Field(default=6, ge=1, le=24)
    regulatory_notice_max_hours: int = Field(default=24, ge=1, le=168)
    regulatory_require_context: bool = True
    source_max_age_days: int = 7
    enrich_asn: bool = False
    discovery_allowed_hosts: str = 'raw.githubusercontent.com'
    auto_analyses_per_day: int = Field(default=100, ge=1, le=1000)
    auto_analysis_delay_seconds: int = Field(default=30, ge=10, le=3600)
    auto_queue_limit: int = Field(default=1000, ge=1, le=5000)
    official_source_url: str = "https://www.gov.br/fazenda/pt-br/composicao/orgaos/secretaria-de-premios-e-apostas/transparencia-ativa-processos-de-autorizacao-de-apostas-de-quota-fixa/empresas-autorizadas"
    @model_validator(mode='after')
    def deployment_security(self):
        origin=urlsplit(self.origin)
        if origin.scheme not in ('http','https') or not origin.hostname or origin.path or origin.query or origin.fragment or origin.username or origin.password:
            raise ValueError('ORIGIN deve ser uma origem HTTP(S) sem caminho')
        if origin.hostname not in ('localhost','127.0.0.1','::1') and (origin.scheme!='https' or not self.cookie_secure):
            raise ValueError('Acesso externo exige HTTPS e COOKIE_SECURE=true')
        if self.app_env=='production' and (origin.scheme!='https' or not self.cookie_secure or not self.auth_encryption_key or self.registration_mode=='open'):
            raise ValueError('Produção exige HTTPS, cookie seguro, chave de MFA e cadastro por convite ou fechado')
        if self.smtp_mode=='local' and self.app_env=='production':
            raise ValueError('SMTP local é somente para desenvolvimento')
        if self.smtp_mode=='smtp' and not self.smtp_starttls:
            raise ValueError('SMTP externo exige STARTTLS')
        if self.app_env=='production' and (self.smtp_mode!='smtp' or not self.require_email_verification):
            raise ValueError('Produção exige SMTP real e confirmação de email')
        if self.backup_encryption_key:
            from cryptography.fernet import Fernet
            try:Fernet(self.backup_encryption_key.encode())
            except (ValueError,TypeError):raise ValueError('Chave de backup inválida')
        if self.auth_encryption_key:
            from cryptography.fernet import Fernet
            try:Fernet(self.auth_encryption_key.encode())
            except (ValueError,TypeError):raise ValueError("AUTH_ENCRYPTION_KEY deve ser uma chave Fernet válida")
        return self
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

@lru_cache
def settings():
    return Settings()
