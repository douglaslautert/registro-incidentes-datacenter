"""Notificações do plantão (Sprint 4): e-mail institucional (SMTP), SMS e ligação pelo modem GSM.

Regras:
  P1 e P2 → SMS; P1 → também ligação (LIGACAO_P1); todas as prioridades → e-mail.
  Reescalonamento (nível 2 em diante) → inclui o 2º nível do plantão e liga também em P2.
Sem o python-gammu instalado (servidor sem modem), SMS e ligação ficam só no log.
"""
import asyncio, logging, re
from app.core.config import settings, lista

log = logging.getLogger("notificacao")


def contatos(nivel: int = 1) -> tuple[list[str], list[str]]:
    """(telefones, e-mails) do plantão para o nível de acionamento."""
    fones, emails = lista(settings.PLANTAO_PHONE), lista(settings.PLANTAO_EMAIL)
    if not emails and settings.SMTP_USER:
        emails = [settings.SMTP_USER]
    if nivel >= 2:
        fones += [f for f in lista(settings.PLANTAO_ESCALONAMENTO_PHONE) if f not in fones]
        emails += [e for e in lista(settings.PLANTAO_ESCALONAMENTO_EMAIL) if e not in emails]
    return fones, emails


def _modem():
    import gammu
    sm = gammu.StateMachine()
    sm.ReadConfig(Filename="/etc/gammu/gammurc")
    sm.Init()
    return sm


def enviar_sms(numero: str, mensagem: str) -> str:
    """'enviado', 'simulado' (sem modem) ou 'falhou'."""
    try:
        _modem().SendSMS({"Text": mensagem[:160], "SMSC": {"Location": 1}, "Number": numero})
        log.info(f"SMS enviado para {numero}")
        return "enviado"
    except ImportError:
        log.warning(f"gammu não instalado — SMS para {numero} simulado: {mensagem[:80]}")
        return "simulado"
    except Exception as e:
        log.error(f"Erro SMS para {numero}: {e}")
        return "falhou"


def ligar(numero: str) -> str:
    """Liga para o plantonista: o toque avisa mesmo com o celular no silencioso para SMS."""
    try:
        _modem().DialVoice(numero)
        log.info(f"Ligação para {numero}")
        return "enviado"
    except ImportError:
        log.warning(f"gammu não instalado — ligação para {numero} simulada")
        return "simulado"
    except Exception as e:
        log.error(f"Erro na ligação para {numero}: {e}")
        return "falhou"


async def enviar_email(para: str, assunto: str, corpo: str) -> bool:
    if not settings.SMTP_USER or not para:
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


async def disparar(acionamentos: list[dict]) -> None:
    """Notifica cada acionamento devolvido pelo registro ou pelo reescalonamento."""
    for a in acionamentos:
        await notificar_plantao(a["incidente_id"], a["prioridade"], a["titulo"], a["ativo"],
                                nivel=a.get("nivel", 1))


async def notificar_plantao(incidente_id: str, prioridade: str, titulo: str, ativo: str,
                            nivel: int = 1) -> dict:
    """Aciona o plantão. Retorna o que foi feito por canal (para log e testes)."""
    fones, emails = contatos(nivel)
    titulo = re.sub(r"\[P\d\]\s*", "", titulo)           # a prioridade já vai no prefixo
    msg = (f"[CESUP {prioridade}] {titulo} | Ativo: {ativo} | "
           f"ID: {incidente_id} | {settings.PUBLIC_URL}")
    feito: dict[str, list] = {"sms": [], "ligacao": [], "email": []}
    if not fones and not emails:
        log.warning("Plantão sem telefone nem e-mail configurado (PLANTAO_PHONE, PLANTAO_EMAIL)")
        return feito
    if prioridade in ("P1", "P2"):
        for f in fones:
            feito["sms"].append((f, await asyncio.to_thread(enviar_sms, f, msg)))
    if settings.LIGACAO_P1 and (prioridade == "P1" or (nivel >= 2 and prioridade == "P2")):
        for f in fones:
            feito["ligacao"].append((f, await asyncio.to_thread(ligar, f)))
    for e in emails:
        feito["email"].append((e, await enviar_email(e, f"[CESUP {prioridade}] {titulo}", msg)))
    return feito
