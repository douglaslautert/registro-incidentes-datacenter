"""Serviço de notificações: SMTP e GSM."""
import logging
from app.core.config import settings

log = logging.getLogger("notificacao")

async def enviar_email(para: str, assunto: str, corpo: str) -> bool:
    if not settings.SMTP_USER:
        log.warning("SMTP não configurado — e-mail não enviado")
        return False
    try:
        import aiosmtplib
        from email.mime.text import MIMEText
        msg = MIMEText(corpo, "plain", "utf-8")
        msg["Subject"] = assunto
        msg["From"]    = settings.SMTP_USER
        msg["To"]      = para
        await aiosmtplib.send(
            msg, hostname=settings.SMTP_HOST, port=settings.SMTP_PORT,
            username=settings.SMTP_USER, password=settings.SMTP_PASSWORD, start_tls=True,
        )
        log.info(f"E-mail enviado para {para}")
        return True
    except Exception as e:
        log.error(f"Erro SMTP: {e}")
        return False

def enviar_sms(numero: str, mensagem: str) -> bool:
    try:
        import gammu
        sm = gammu.StateMachine()
        sm.ReadConfig(Filename="/etc/gammu/gammurc")
        sm.Init()
        sm.SendSMS({"Text": mensagem[:160], "SMSC": {"Location": 1}, "Number": numero})
        log.info(f"SMS enviado para {numero}")
        return True
    except ImportError:
        log.warning("gammu não instalado — SMS simulado (ambiente de teste)")
        return True
    except Exception as e:
        log.error(f"Erro SMS: {e}")
        return False

async def notificar_plantao(
    incidente_id: str, prioridade: str, titulo: str, ativo: str
) -> None:
    if not settings.PLANTAO_PHONE:
        log.warning("PLANTAO_PHONE não configurado")
        return
    msg = (f"[CESUP {prioridade}] {titulo} | Ativo: {ativo} | "
           f"ID: {incidente_id} | {settings.PUBLIC_URL}")
    if prioridade in ("P1", "P2"):
        enviar_sms(settings.PLANTAO_PHONE, msg)
    await enviar_email(
        settings.SMTP_USER or "",
        f"[CESUP {prioridade}] {titulo}", msg,
    )
