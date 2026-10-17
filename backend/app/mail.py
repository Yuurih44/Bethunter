"""Expiring email-bound tokens, encrypted mail queue and TLS SMTP transport."""
import asyncio,json,secrets,smtplib,ssl
from email.message import EmailMessage
from datetime import timedelta
from sqlalchemy import select,delete
from .models import EmailToken,MailJob,User,Audit,now
from .security import token_hash,encryption
from .config import settings
from .db import SessionLocal
from fastapi import HTTPException


def queue_token(db,user,purpose):
    cfg=settings()
    if cfg.smtp_mode=='disabled':raise HTTPException(503,'Email desabilitado. Configure o servidor local ou SMTP real.')
    # Only one usable token per purpose/account. Plaintext appears only inside encrypted mail.
    db.execute(delete(EmailToken).where(EmailToken.user_id==user.id,EmailToken.purpose==purpose))
    token=secrets.token_urlsafe(32)
    db.add(EmailToken(token_hash=token_hash(token),user_id=user.id,purpose=purpose,delivery_mode=cfg.smtp_mode,expires=now()+timedelta(minutes=30)))
    action='verify-email' if purpose=='verify' else 'reset-password'
    link=cfg.origin+'/account#'+action+'='+token
    message={'mode':cfg.smtp_mode,'to':user.email,'subject':'Confirmação de email BetHunter' if purpose=='verify' else 'Recuperação de senha BetHunter',
             'body':('MODO LOCAL DE TESTE — sem entrega para a internet.\n\n' if cfg.smtp_mode=='local' else '')+
              'Use o link em até 30 minutos. Ele funciona uma vez:\n'+link+'\nSe não solicitou, ignore. Nunca compartilhe este link.'}
    db.add(MailJob(user_id=user.id,encrypted_message=encryption().encrypt(json.dumps(message).encode()).decode()))
    db.add(Audit(user_id=user.id,action='email.request.'+purpose,details={'delivery_mode':cfg.smtp_mode}))


def send(message):
    cfg=settings();mail=EmailMessage();mail['From']=cfg.smtp_from;mail['To']=message['to'];mail['Subject']=message['subject'];mail.set_content(message['body'])
    with smtplib.SMTP(cfg.smtp_host,cfg.smtp_port,timeout=15) as smtp:
        smtp.ehlo()
        if cfg.smtp_mode=='smtp':smtp.starttls(context=ssl.create_default_context());smtp.ehlo()
        if cfg.smtp_username:smtp.login(cfg.smtp_username,cfg.smtp_password)
        smtp.send_message(mail)


async def tick_mail():
    if settings().smtp_mode=='disabled':return False
    with SessionLocal() as db:
        job=db.scalar(select(MailJob).where(MailJob.status=='queued',MailJob.next_run<=now()).order_by(MailJob.id).with_for_update(skip_locked=True).limit(1))
        if not job:return False
        job.attempts+=1
        if job.created.replace(tzinfo=now().tzinfo)<now()-timedelta(minutes=25):
            job.status='failed';job.error='Janela de entrega expirada';job.encrypted_message=''
        else:
            try:
                payload=json.loads(encryption().decrypt(job.encrypted_message.encode()))
                if payload.get('mode')!=settings().smtp_mode:raise ValueError('Modo de entrega alterado')
                await asyncio.to_thread(send,payload)
                job.status='captured_local' if settings().smtp_mode=='local' else 'accepted_by_smtp'
                job.encrypted_message='';job.error=''
            except Exception as exc:
                job.error=type(exc).__name__ # SMTP exceptions can include recipient/token details.
                job.next_run=now()+timedelta(minutes=2**job.attempts)
                if job.attempts>=3:job.status='failed';job.encrypted_message=''
        db.commit();return True
