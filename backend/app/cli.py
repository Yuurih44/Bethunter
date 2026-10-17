"""Offline operator actions; no public privilege escalation or invitation bootstrap."""
import argparse
import getpass
import secrets
from datetime import timedelta
from sqlalchemy import select,delete
from .db import SessionLocal
from .models import User,Audit,Invitation,MfaRecovery,MfaEnrollment
from .security import hash_password,hasher,password_policy,token_hash,revoke_sessions
from .accounts import normalize_email

parser=argparse.ArgumentParser()
parser.add_argument('email')
parser.add_argument('--invite',action='store_true',help='Emitir convite para este email usando administrador existente')
parser.add_argument('--reset-mfa',action='store_true',help='Recuperação offline: remover MFA e revogar sessões')
parser.add_argument('--disable',action='store_true',help='Desativar conta e revogar sessões')
args=parser.parse_args()
email=normalize_email(args.email)
with SessionLocal() as db:
    if args.invite:
        issuer=db.scalar(select(User).where(User.role=='admin',User.active.is_(True)).order_by(User.id).limit(1))
        if not issuer:raise SystemExit('Configure primeiro um administrador com ./iniciar.sh admin EMAIL')
        if db.scalar(select(User.id).where(User.email==email)):raise SystemExit('Conta já cadastrada')
        token=secrets.token_urlsafe(32)
        from .models import now
        invitation=Invitation(token_hash=token_hash(token),email=email,role='analyst',issuer_id=issuer.id,expires=now()+timedelta(hours=24))
        db.add(invitation);db.flush()
        db.add(Audit(user_id=issuer.id,action='invitation.issue.offline_operator',details={'id':invitation.id,'email':email}))
        db.commit()
        print('Convite de uso único, válido por 24h. Compartilhe por canal privado:')
        print(token)
    else:
        user=db.scalar(select(User).where(User.email==email))
        if args.reset_mfa or args.disable:
            if not user:raise SystemExit('Conta inexistente')
            revoke_sessions(db,user.id)
            if args.disable:user.active=False
            if args.reset_mfa:
                user.mfa_enabled=False;user.mfa_secret=None;user.mfa_last_counter=-1
                db.execute(delete(MfaRecovery).where(MfaRecovery.user_id==user.id))
                db.execute(delete(MfaEnrollment).where(MfaEnrollment.user_id==user.id))
            db.add(Audit(user_id=user.id,action='account.recovery.offline_operator',details={'disable':args.disable,'reset_mfa':args.reset_mfa}))
            db.commit();print('Conta atualizada; sessões revogadas.')
        else:
            if not user:
                password=getpass.getpass('Senha exclusiva do administrador (15+ caracteres): ')
                try:password_policy(password,email)
                except ValueError as exc:raise SystemExit(str(exc))
                if password!=getpass.getpass('Confirme a senha: '):raise SystemExit('Senhas diferentes')
                user=User(email=email,password=hash_password(password),role='admin');db.add(user);db.flush()
            user.role='admin'
            db.add(Audit(user_id=user.id,action='admin.provision.offline_operator',details={'email':email}))
            db.commit();print('Administrador configurado. Acesse Segurança para ativar MFA antes das ações administrativas.')
