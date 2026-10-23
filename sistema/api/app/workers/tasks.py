"""Tasks Celery — Sprint 4: notificações, escalonamento, reconciliação."""
from celery import Celery
from app.core.config import settings

celery_app = Celery("cesup", broker=settings.REDIS_URL, backend=settings.REDIS_URL)

celery_app.conf.task_routes = {
    "app.workers.tasks.processar_evento":          {"queue": "default"},
    "app.workers.tasks.enviar_notificacao_email":  {"queue": "notifications"},
    "app.workers.tasks.enviar_notificacao_gsm":    {"queue": "notifications"},
    "app.workers.tasks.reconciliar_zabbix":        {"queue": "default"},
    "app.workers.tasks.verificar_timeouts":        {"queue": "default"},
}

celery_app.conf.beat_schedule = {
    # T4: reconciliação Zabbix a cada 5 minutos
    "reconciliar-zabbix": {
        "task": "app.workers.tasks.reconciliar_zabbix",
        "schedule": 300.0,
    },
    # T6: verificar ACKs pendentes e reescalonar a cada 60s
    "verificar-timeouts-ack": {
        "task": "app.workers.tasks.verificar_timeouts",
        "schedule": 60.0,
    },
}


@celery_app.task(bind=True, max_retries=3)
def processar_evento(self, evento_id: str):
    """Normaliza evento: gera embedding e atualiza correlação no banco."""
    import asyncio
    from app.services.embedding import gerar_embedding

    async def _run():
        try:
            # Buscar evento no banco e gerar embedding
            from app.database import AsyncSessionLocal
            from app.models.incidente import Evento
            from sqlalchemy import select
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Evento).where(Evento.id == evento_id)
                )
                ev = result.scalar_one_or_none()
                if ev and ev.sintoma:
                    ev.embedding = gerar_embedding(ev.sintoma)
                    await db.commit()
        except Exception as e:
            import logging
            logging.getLogger("tasks").warning(f"processar_evento: {e}")

    try:
        asyncio.run(_run())
    except Exception as e:
        raise self.retry(exc=e, countdown=60)


@celery_app.task(bind=True, max_retries=3)
def enviar_notificacao_email(self, para: str, assunto: str, corpo: str):
    """T3: Envia e-mail SMTP institucional."""
    import asyncio
    from app.services.notificacao import enviar_email
    try:
        asyncio.run(enviar_email(para, assunto, corpo))
    except Exception as e:
        raise self.retry(exc=e, countdown=60)


@celery_app.task(bind=True, max_retries=3)
def enviar_notificacao_gsm(self, numero: str, mensagem: str):
    """T4: Envia SMS via modem Gammu."""
    from app.services.notificacao import enviar_sms
    if not enviar_sms(numero, mensagem):
        raise self.retry(countdown=30)


@celery_app.task
def gerar_embedding(evento_id: str, sintoma: str, descricao: str = ""):
    """M4: Gera embedding vetorial do evento para correlação semântica."""
    from app.services.embedding import gerar_embedding as _gerar
    vetor = _gerar(sintoma, descricao)
    # Sprint 6+: persistir no campo embedding da tabela eventos
    return {"evento_id": evento_id, "dim": len(vetor), "norma": round(sum(v*v for v in vetor)**0.5, 4)}


@celery_app.task
def reconciliar_zabbix():
    """T4: Poll periódico Zabbix — captura alertas que chegaram sem webhook."""
    import asyncio
    from app.services.zabbix_client import zabbix

    async def _run():
        try:
            alertas = await zabbix.alertas_recentes(minutos=6)
            for a in alertas:
                hosts = a.get("hosts", [{}])
                host  = hosts[0].get("host", "desconhecido") if hosts else "desconhecido"
                # Publicar na fila para processamento assíncrono
                processar_evento.delay(a["eventid"])
        except Exception as e:
            import logging
            logging.getLogger("tasks").warning(f"Zabbix indisponível: {e}")

    asyncio.run(_run())


@celery_app.task
def verificar_timeouts():
    """T6: Verifica acionamentos sem ACK e reescalona se timeout expirou."""
    import asyncio
    from app.services.escalonamento import verificar_timeouts as vt
    asyncio.run(vt())
