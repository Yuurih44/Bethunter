import hashlib
import secrets
import time
from threading import Lock, BoundedSemaphore
from collections import defaultdict, deque
from datetime import timedelta, timezone
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from cryptography.fernet import Fernet, InvalidToken
import pyotp
from argon2 import PasswordHasher, Type
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session as DBSession
from .db import get_db
from .models import User, Session, AuthThrottle, MfaRecovery, Audit, now
from .config import settings

hasher = PasswordHasher(type=Type.ID)
DUMMY_HASH = hasher.hash("bethunter-dummy-password")
buckets = defaultdict(deque)
bucket_lock = Lock()
password_slots=BoundedSemaphore(2)

def hash_password(password):
    if not password_slots.acquire(blocking=False):raise HTTPException(429,"Autenticação ocupada; tente novamente")
    try:return hasher.hash(password)
    finally:password_slots.release()

def limit(key, count=30, seconds=60):
    with bucket_lock:
        t = time.monotonic()
        # Bound memory; expiry is independent of user supplied keys.
        for k in list(buckets):
            if not buckets[k] or buckets[k][-1] < t - 3600:
                del buckets[k]
        q = buckets[key]
        while q and q[0] <= t - seconds:
            q.popleft()
        if len(q) >= count:
            raise HTTPException(429, "Limite de requisições; tente novamente mais tarde")
        q.append(t)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()

csrf_scheme = APIKeyHeader(name="X-CSRF-Token", auto_error=False, description="Token csrf retornado pelo login; cookie de sessão também é obrigatório.")

def current_user(request: Request, db: DBSession = Depends(get_db), csrf_header: str | None = Security(csrf_scheme)):
    token = request.cookies.get("bh_session", "")
    session = db.get(Session, token_hash(token))
    if not session or session.expires.replace(tzinfo=timezone.utc) <= now() or session.last_seen.replace(tzinfo=timezone.utc) < now()-timedelta(minutes=settings().session_idle_minutes):
        raise HTTPException(401, "Sessão expirada")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if request.headers.get("origin") != settings().origin or not secrets.compare_digest(request.headers.get("x-csrf-token", "").encode(), session.csrf.encode()):
            raise HTTPException(403, "Validação CSRF falhou")
    user = db.get(User, session.user_id)
    if not user or not user.active or (user.mfa_enabled and not session.mfa_verified):
        raise HTTPException(401,'Autenticação necessária')
    if settings().require_email_verification and (not user.email_verified or (settings().smtp_mode=='smtp' and user.email_verified_mode!='smtp')) and not request.url.path.startswith('/api/auth/'):
        raise HTTPException(403,'Confirme seu email em Segurança antes de utilizar a plataforma')
    if request.method not in ('GET','HEAD','OPTIONS') and session.last_seen.replace(tzinfo=timezone.utc) < now()-timedelta(seconds=60):
        session.last_seen=now()
        db.commit()
    if request.method not in ("GET","HEAD","OPTIONS") and user.role == "viewer" and not request.url.path.startswith("/api/auth/"):
        raise HTTPException(403, "Perfil somente leitura")
    request.state.session = session
    return user

def admin(user=Depends(current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Requer administrador")
    if settings().require_mfa_admin and not user.mfa_enabled:
        raise HTTPException(403,'Ative a autenticação em duas etapas em Segurança antes de administrar a instalação')
    return user

def issue_session(db, user, response, mfa_verified=False):
    token, csrf = secrets.token_urlsafe(32), secrets.token_hex(32)
    db.add(Session(id=token_hash(token), user_id=user.id, csrf=csrf, expires=now()+timedelta(hours=settings().session_hours), mfa_verified=mfa_verified))
    db.commit()
    response.set_cookie("bh_session", token, httponly=True, secure=settings().cookie_secure, samesite="strict", max_age=settings().session_hours*3600, path="/api")
    return {"id": user.id, "email": user.email, "role": user.role, "csrf": csrf, "mfa_enabled": user.mfa_enabled,"email_verified":user.email_verified}


def password_policy(value,email=''):
    simple=value.casefold()
    common={'password1234567','123456789012345','1234567890123456','qwerty1234567890','senha1234567890','passwordpassword','bethunter123456'}
    if len(value)<15 or len(value)>128 or simple in common or len(set(simple))<5 or (email and simple==email.casefold()):
        raise ValueError('Use uma senha exclusiva de 15 a 128 caracteres; frases longas são aceitas')
    return value


def encryption():
    try:
        return Fernet(settings().auth_encryption_key.encode())
    except (ValueError,TypeError):
        raise HTTPException(503,'MFA indisponível: configure AUTH_ENCRYPTION_KEY no servidor')


def throttle_row(db,identity):
    key=token_hash(identity)
    if db.get(AuthThrottle,key) is None:
        try:
            with db.begin_nested():
                db.add(AuthThrottle(key=key,failures=0,window_start=now()))
                db.flush()
        except IntegrityError:
            pass
    row=db.scalar(select(AuthThrottle).where(AuthThrottle.key==key).with_for_update().execution_options(populate_existing=True))
    if row.blocked_until and row.blocked_until.replace(tzinfo=timezone.utc)>now():
        raise HTTPException(429,'Tentativas temporariamente limitadas; aguarde 15 minutos',headers={'Retry-After':'900'})
    if row.window_start.replace(tzinfo=timezone.utc)<now()-timedelta(minutes=15):
        row.failures=0;row.blocked_until=None;row.window_start=now()
    return row


def authentication_failure(db,throttle,peer='',user_id=None):
    throttle.failures+=1
    if throttle.failures>=5:
        throttle.blocked_until=now()+timedelta(minutes=15)
    from .models import SecurityEvent
    db.add(SecurityEvent(identity_hash=throttle.key,action='authentication.failed',peer=peer,user_id=user_id))
    db.commit()
    raise HTTPException(401,'Credenciais ou código inválidos')


def verify_password(user,password):
    if not password_slots.acquire(blocking=False):raise HTTPException(429,"Autenticação ocupada; tente novamente")
    try:
        return bool(hasher.verify(user.password if user else DUMMY_HASH,password))
    except (VerifyMismatchError,VerificationError):
        return False
    finally:password_slots.release()


def verify_second_factor(db,user,otp_code=None,recovery_code=None):
    if not user.mfa_enabled:
        return True
    if recovery_code:
        code=db.scalar(select(MfaRecovery).where(MfaRecovery.token_hash==token_hash(recovery_code),MfaRecovery.user_id==user.id).with_for_update())
        if code and code.used_at is None:
            code.used_at=now()
            db.add(Audit(user_id=user.id,action='auth.recovery.used',details={}))
            return True
        return False
    if not otp_code or not user.mfa_secret:
        return False
    try:
        secret=encryption().decrypt(user.mfa_secret.encode()).decode()
    except InvalidToken:
        raise HTTPException(503,'Chave de MFA incompatível; contate o administrador')
    totp=pyotp.TOTP(secret)
    current=int(now().timestamp())//totp.interval
    for counter in (current-1,current,current+1):
        if counter>user.mfa_last_counter and secrets.compare_digest(totp.at(counter*totp.interval),otp_code):
            user.mfa_last_counter=counter
            return True
    return False


def reauthenticate(db,user,password,otp_code=None,recovery_code=None):
    throttle=throttle_row(db,'reauth:'+str(user.id))
    user=db.scalar(select(User).where(User.id==user.id).with_for_update().execution_options(populate_existing=True))
    if not verify_password(user,password) or not verify_second_factor(db,user,otp_code,recovery_code):
        authentication_failure(db,throttle)
    throttle.failures=0;throttle.blocked_until=None
    return user


def new_recovery_codes(db,user):
    db.execute(delete(MfaRecovery).where(MfaRecovery.user_id==user.id))
    codes=[secrets.token_urlsafe(12) for _ in range(8)]
    for code in codes:
        db.add(MfaRecovery(token_hash=token_hash(code),user_id=user.id))
    return codes


def revoke_sessions(db,user_id):
    db.execute(delete(Session).where(Session.user_id==user_id))
