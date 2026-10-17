from datetime import timezone
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from pathlib import Path
from fastapi import APIRouter,Depends,HTTPException,Request
from pydantic import BaseModel,Field,field_validator
from sqlalchemy import select,delete
from .accounts import normalize_email,Proof
from .models import User,EmailToken,Audit,now
from .db import get_db
from .security import current_user,limit,token_hash,hash_password,password_policy,verify_second_factor,revoke_sessions,throttle_row,authentication_failure
from .mail import queue_token
from .config import settings

router=APIRouter(prefix='/api/auth')
class EmailInput(BaseModel):
    email:str=Field(max_length=254)
    @field_validator('email')
    @classmethod
    def valid(cls,v):return normalize_email(v)
class TokenInput(BaseModel):
    token:str=Field(min_length=20,max_length=200)
class Reset(TokenInput):
    new_password:str=Field(min_length=15,max_length=128)
    otp_code:str|None=Field(default=None,pattern=r'^\d{6}$')
    recovery_code:str|None=Field(default=None,max_length=100)
    @field_validator('otp_code','recovery_code',mode='before')
    @classmethod
    def empty(cls,v):return v or None
    @field_validator('new_password')
    @classmethod
    def strong(cls,v):return password_policy(v)

def consume(db,token,purpose):
    row=db.scalar(select(EmailToken).where(EmailToken.token_hash==token_hash(token),EmailToken.purpose==purpose).with_for_update())
    if not row or row.delivery_mode!=settings().smtp_mode or row.used_at or row.expires.replace(tzinfo=timezone.utc)<=now():raise HTTPException(400,'Link inválido, utilizado ou expirado')
    user=db.scalar(select(User).where(User.id==row.user_id).with_for_update().execution_options(populate_existing=True))
    if not user or not user.active:raise HTTPException(400,'Link inválido, utilizado ou expirado')
    return row,user

@router.post('/email/request')
def request_verification(user=Depends(current_user),db=Depends(get_db)):
    limit(('verify_email',user.id),3,3600)
    if not user.email_verified or (settings().smtp_mode=='smtp' and user.email_verified_mode!='smtp'):queue_token(db,user,'verify');db.commit()
    return {'notice':'Se necessário, uma mensagem foi colocada na fila. Entrega depende do servidor configurado.','mode':settings().smtp_mode}

@router.post('/email/confirm')
def confirm_email(body:TokenInput,request:Request,db=Depends(get_db)):
    limit(('email_confirm',request.client.host),10,60)
    row,user=consume(db,body.token,'verify');row.used_at=now();user.email_verified=True;user.email_verified_mode=row.delivery_mode
    db.add(Audit(user_id=user.id,action='email.verified.local_test' if settings().smtp_mode=='local' else 'email.verified',details={'mode':settings().smtp_mode}));db.commit()
    return {'ok':True,'local_test':settings().smtp_mode=='local','notice':'Email confirmado no modo local de teste.' if settings().smtp_mode=='local' else 'Email confirmado.'}

@router.post('/password/request-reset')
def request_reset(body:EmailInput,request:Request,db=Depends(get_db)):
    limit(('reset_ip',request.client.host),5,3600);limit(('reset_email',token_hash(body.email)),3,3600)
    if settings().smtp_mode=='disabled':raise HTTPException(503,'Email desabilitado no servidor')
    user=db.scalar(select(User).where(User.email==body.email,User.active.is_(True)))
    if user:queue_token(db,user,'reset');db.commit()
    return {'notice':'Se a conta existir, uma mensagem foi colocada na fila.','mode':settings().smtp_mode}

@router.post('/password/reset')
def reset_password(body:Reset,request:Request,db=Depends(get_db)):
    limit(('reset_confirm',request.client.host),10,60)
    row,user=consume(db,body.token,'reset')
    throttle=throttle_row(db,'reset:'+str(user.id))
    if not verify_second_factor(db,user,body.otp_code,body.recovery_code):authentication_failure(db,throttle)
    try:password_policy(body.new_password,user.email)
    except ValueError as exc:raise HTTPException(422,str(exc))
    user.password=hash_password(body.new_password);row.used_at=now();revoke_sessions(db,user.id)
    db.execute(delete(EmailToken).where(EmailToken.user_id==user.id,EmailToken.purpose=='reset',EmailToken.token_hash!=row.token_hash))
    db.add(Audit(user_id=user.id,action='auth.password.reset',details={'mfa_preserved':user.mfa_enabled}));db.commit()
    return {'ok':True,'notice':'Senha atualizada; entre novamente. MFA permanece ativo.'}

@router.get('/email/local-inbox')
def local_inbox(user=Depends(current_user)):
    cfg=settings()
    if cfg.smtp_mode!='local' or cfg.app_env=='production':raise HTTPException(404,'Disponível apenas no modo local de teste')
    path=Path(cfg.mail_capture_dir)
    items=[]
    if path.exists():
        for file in sorted(path.glob('*.eml'),key=lambda f:f.stat().st_mtime,reverse=True)[:200]:
            if file.stat().st_size>1_000_000:continue
            message=BytesParser(policy=policy.default).parsebytes(file.read_bytes())
            recipients=[address.lower() for _,address in getaddresses(message.get_all('To',[]))]
            if user.email not in recipients:continue
            body=message.get_body(preferencelist=('plain',))
            items.append({'id':file.stem,'subject':str(message['Subject'] or ''),'body':body.get_content() if body else '', 'mode':'local_capture_not_internet'})
            if len(items)>=10:break
    return {'notice':'Caixa LOCAL DE TESTE; mensagens não foram entregues pela internet.','items':items}
