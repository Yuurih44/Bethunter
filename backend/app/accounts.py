from .security import hash_password
from datetime import timedelta, timezone
from typing import Literal
import secrets
from cryptography.fernet import InvalidToken
from email_validator import validate_email,EmailNotValidError
from fastapi import APIRouter,Depends,HTTPException,Request,Response
from pydantic import BaseModel,Field,field_validator
from sqlalchemy import select,delete
from sqlalchemy.orm import Session as DBSession
from .db import get_db
from .models import User,Session,Invitation,MfaEnrollment,MfaRecovery,Audit,now
from .config import settings
from .security import (current_user,admin,limit,token_hash,password_policy,encryption,pyotp,
                       reauthenticate,new_recovery_codes,revoke_sessions,issue_session,hasher)

router=APIRouter(prefix='/api')

def normalize_email(value):
    try:return validate_email(value,check_deliverability=False).normalized.lower()
    except EmailNotValidError:raise ValueError('Email inválido')

class Proof(BaseModel):
    password:str=Field(min_length=1,max_length=128)
    otp_code:str|None=Field(default=None,pattern=r'^\d{6}$')
    recovery_code:str|None=Field(default=None,max_length=100)
    @field_validator('otp_code','recovery_code',mode='before')
    @classmethod
    def empty(cls,value):return value or None

class PasswordChange(Proof):
    new_password:str=Field(min_length=15,max_length=128)
    @field_validator('new_password')
    @classmethod
    def strong(cls,value):return password_policy(value)

class InviteInput(Proof):
    email:str=Field(max_length=254)
    role:Literal['analyst','viewer']='analyst'
    hours:int=Field(default=24,ge=1,le=72)
    @field_validator('email')
    @classmethod
    def email_check(cls,value):return normalize_email(value)

@router.get('/auth/policy')
def policy():
    cfg=settings()
    return {'registration_mode':cfg.registration_mode if cfg.registration_enabled else 'closed',
        'minimum_password_length':15,'mfa_available':bool(cfg.auth_encryption_key),
        'session_idle_minutes':cfg.session_idle_minutes,'email_verification':'not_configured; invitation is email-bound but does not verify mailbox ownership'}

@router.get('/auth/security')
def security_state(request:Request,user=Depends(current_user)):
    return {'mfa_enabled':user.mfa_enabled,'mfa_available':bool(settings().auth_encryption_key),
        'admin_mfa_required':settings().require_mfa_admin,'role':user.role,'email_verified':user.email_verified and (settings().smtp_mode!='smtp' or user.email_verified_mode=='smtp'),'smtp_mode':settings().smtp_mode,'session_idle_minutes':settings().session_idle_minutes}

@router.post('/auth/mfa/setup')
def mfa_setup(body:Proof,user=Depends(current_user),db:DBSession=Depends(get_db)):
    limit(('mfa.setup',user.id),5,60)
    user=reauthenticate(db,user,body.password,body.otp_code,body.recovery_code)
    if user.mfa_enabled:raise HTTPException(409,'MFA já está ativo')
    secret=pyotp.random_base32()
    encoded=encryption().encrypt(secret.encode()).decode()
    enrollment=db.get(MfaEnrollment,user.id)
    if not enrollment:
        enrollment=MfaEnrollment(user_id=user.id);db.add(enrollment)
    enrollment.encrypted_secret=encoded;enrollment.expires=now()+timedelta(minutes=10)
    db.add(Audit(user_id=user.id,action='auth.mfa.setup',details={}))
    db.commit()
    return {'secret':secret,'uri':pyotp.TOTP(secret).provisioning_uri(user.email,issuer_name='BetHunter'),'expires_in_seconds':600}

class ConfirmMfa(BaseModel):
    code:str=Field(pattern=r'^\d{6}$')

@router.post('/auth/mfa/confirm')
def mfa_confirm(body:ConfirmMfa,response:Response,user=Depends(current_user),db:DBSession=Depends(get_db)):
    limit(('mfa.confirm',user.id),5,60)
    enrollment=db.scalar(select(MfaEnrollment).where(MfaEnrollment.user_id==user.id).with_for_update())
    if not enrollment or enrollment.expires.replace(tzinfo=timezone.utc)<=now() or user.mfa_enabled:
        raise HTTPException(409,'Inicie uma configuração MFA válida')
    try:secret=encryption().decrypt(enrollment.encrypted_secret.encode()).decode()
    except InvalidToken:raise HTTPException(503,"Chave de MFA incompatível; reinicie a configuração")
    totp=pyotp.TOTP(secret)
    current=int(now().timestamp())//30
    matched=next((c for c in (current-1,current,current+1) if secrets.compare_digest(totp.at(c*30),body.code)),None)
    if matched is None:raise HTTPException(400,'Código inválido')
    user.mfa_secret=enrollment.encrypted_secret;user.mfa_enabled=True;user.mfa_last_counter=matched
    db.delete(enrollment)
    codes=new_recovery_codes(db,user)
    revoke_sessions(db,user.id)
    db.add(Audit(user_id=user.id,action='auth.mfa.enabled',details={'sessions_revoked':True}))
    session=issue_session(db,user,response,mfa_verified=True)
    return {'user':session,'recovery_codes':codes,'notice':'Guarde os códigos em local seguro. Eles são exibidos apenas agora e cada um funciona uma vez.'}

@router.post('/auth/mfa/disable')
def mfa_disable(body:Proof,response:Response,user=Depends(current_user),db:DBSession=Depends(get_db)):
    user=reauthenticate(db,user,body.password,body.otp_code,body.recovery_code)
    user.mfa_enabled=False;user.mfa_secret=None;user.mfa_last_counter=-1
    db.execute(delete(MfaRecovery).where(MfaRecovery.user_id==user.id))
    db.execute(delete(MfaEnrollment).where(MfaEnrollment.user_id==user.id))
    revoke_sessions(db,user.id)
    db.add(Audit(user_id=user.id,action='auth.mfa.disabled',details={}))
    db.commit();response.delete_cookie('bh_session',path='/api')
    return {'ok':True,'login_required':True}

@router.post('/auth/password')
def change_password(body:PasswordChange,response:Response,user=Depends(current_user),db:DBSession=Depends(get_db)):
    user=reauthenticate(db,user,body.password,body.otp_code,body.recovery_code)
    try:password_policy(body.new_password,user.email)
    except ValueError as exc:raise HTTPException(422,str(exc))
    user.password=hash_password(body.new_password)
    revoke_sessions(db,user.id)
    db.add(Audit(user_id=user.id,action='auth.password.changed',details={'sessions_revoked':True}))
    return issue_session(db,user,response,mfa_verified=user.mfa_enabled)

@router.get('/auth/sessions')
def sessions(request:Request,user=Depends(current_user),db:DBSession=Depends(get_db)):
    rows=db.scalars(select(Session).where(Session.user_id==user.id,Session.expires>now()).order_by(Session.created.desc())).all()
    return [{'id':s.id,'current':s.id==request.state.session.id,'created':s.created,'last_seen':s.last_seen,'expires':s.expires} for s in rows]

@router.post('/auth/sessions/revoke-others')
def revoke_other_sessions(request:Request,body:Proof,user=Depends(current_user),db:DBSession=Depends(get_db)):
    reauthenticate(db,user,body.password,body.otp_code,body.recovery_code)
    result=db.execute(delete(Session).where(Session.user_id==user.id,Session.id!=request.state.session.id))
    db.add(Audit(user_id=user.id,action='auth.sessions.revoke_others',details={'count':result.rowcount}));db.commit()
    return {'revoked':result.rowcount}

@router.post('/security/invitations',status_code=201)
def invite(body:InviteInput,user=Depends(admin),db:DBSession=Depends(get_db)):
    limit(('invitation',user.id),10,3600)
    reauthenticate(db,user,body.password,body.otp_code,body.recovery_code)
    if db.scalar(select(User.id).where(User.email==body.email)):
        raise HTTPException(409,'Conta já cadastrada')
    token=secrets.token_urlsafe(32)
    invitation=Invitation(token_hash=token_hash(token),email=body.email,role=body.role,issuer_id=user.id,expires=now()+timedelta(hours=body.hours))
    db.add(invitation);db.flush()
    db.add(Audit(user_id=user.id,action='invitation.issue',details={'id':invitation.id,'email':body.email,'role':body.role}));db.commit()
    return {'id':invitation.id,'token':token,'expires':invitation.expires,'notice':'Compartilhe o código por canal privado. Convite vinculado ao email, não é confirmação de posse da caixa postal.'}

@router.get('/security/invitations')
def invitations(user=Depends(admin),db:DBSession=Depends(get_db)):
    return [{'id':i.id,'email':i.email,'role':i.role,'expires':i.expires,'used_at':i.used_at,'revoked':i.revoked} for i in db.scalars(select(Invitation).order_by(Invitation.id.desc()).limit(100))]

@router.post('/security/invitations/{id}/revoke')
def revoke_invitation(id:int,body:Proof,user=Depends(admin),db:DBSession=Depends(get_db)):
    reauthenticate(db,user,body.password,body.otp_code,body.recovery_code)
    invitation=db.get(Invitation,id)
    if not invitation:raise HTTPException(404,'Convite não encontrado')
    invitation.revoked=True
    db.add(Audit(user_id=user.id,action='invitation.revoke',details={'id':id}));db.commit()
    return {'ok':True}

@router.post('/auth/activity')
def activity(user=Depends(current_user)):
    return {'ok':True}
