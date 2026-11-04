"""Tarefas do Celery: reconciliação com o Zabbix (S1), reescalonamento do plantão (S4)
e análise de fotos e vídeos pelo modelo de visão (S5).

Cada tarefa abre a própria sessão (sessao_isolada): roda num asyncio.run() novo e não pode
reaproveitar conexões do pool global, presas ao loop de outra execução.
"""
import asyncio, logging
from celery import Celery
from app.core.config import settings

log = logging.getLogger("tasks")

celery_app = Celery("cesup", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery_app.conf.task_routes = {
    "app.workers.tasks.enviar_notificacao_email": {"queue": "notifications"},
    "app.workers.tasks.enviar_notificacao_gsm":   {"queue": "notifications"},
}
celery_app.conf.task_default_queue = "default"
celery_app.conf.beat_schedule = {
    "reconciliar-zabbix-5min": {
        "task": "app.workers.tasks.reconciliar_zabbix",
        "schedule": 300.0,
    },
    "verificar-timeouts-60s": {
        "task": "app.workers.tasks.verificar_timeouts",
        "schedule": 60.0,
    },
}


async def _reconciliar() -> dict:
    """Problemas recentes do Zabbix que não chegaram pelo webhook entram pelo registro comum."""
    from app.database import sessao_isolada
    from app.services import registro, inventario
    from app.services.normalizacao import de_problema_zabbix
    from app.services.notificacao import disparar
    from app.services.zabbix_client import zabbix
    try:
        problemas = await zabbix.alertas_recentes(minutos=6)
    except Exception as e:
        log.warning(f"Zabbix indisponível: {e}")
        return {"erro": str(e)}
    novos, notificar = 0, []
    async with sessao_isolada() as db:
        await inventario.recarregar(db)
        for p in problemas:
            ev, eventid = de_problema_zabbix(p)
            res = await registro.registrar(db, ev, zabbix_eventid=eventid, status_origem="PROBLEM",
                                           raw=p, criado_por="zabbix-reconciliacao")
            if res["decisao_correlacao"] != "duplicado":
                novos += 1
                notificar += res["notificar"]
    await disparar(notificar)
    if novos:
        log.info(f"Reconciliação: {novos} alerta(s) do Zabbix sem webhook registrado(s)")
    return {"problemas": len(problemas), "novos": novos}


@celery_app.task
def reconciliar_zabbix():
    return asyncio.run(_reconciliar())


async def _verificar_timeouts() -> int:
    from app.database import sessao_isolada
    from app.services.escalonamento import verificar_timeouts as vt
    from app.services.notificacao import disparar
    async with sessao_isolada() as db:
        notificar = await vt(db)
    await disparar(notificar)
    return len(notificar)


@celery_app.task
def verificar_timeouts():
    """A cada 60 s: acionamentos sem ACK no prazo sobem de nível."""
    return asyncio.run(_verificar_timeouts())


async def _analisar_midia(incidente_id: str, url: str) -> dict | None:
    from app.database import sessao_isolada
    from app.models.acionamento import AnaliseMidia
    from app.services import visao, registro
    from app.services.s3_client import baixar_evidencia, ROTA_ARQUIVO
    tipo = registro.tipo_midia(url)
    if not tipo or not visao.configurado():
        return None                                  # sem IA: segue sem análise
    key = url.split(ROTA_ARQUIVO, 1)[-1]
    obj = await asyncio.to_thread(baixar_evidencia, key)
    if obj is None:
        return None
    dados = await asyncio.to_thread(obj["Body"].read)
    res = await visao.analisar(dados, tipo, obj.get("ContentType") or "image/jpeg")
    if res is None:
        return None
    async with sessao_isolada() as db:
        db.add(AnaliseMidia(incidente_id=incidente_id, url=url, tipo=tipo, modelo=res["modelo"],
                            descricao=res["descricao"], dados=res["dados"]))
    log.info(f"Análise de {tipo} do incidente {incidente_id}: {res['descricao'][:80]}")
    return res


@celery_app.task(bind=True, max_retries=2)
def analisar_midia(self, incidente_id: str, url: str):
    """Sprint 5: LEDs, displays e etiquetas nas fotos; quadros-chave nos vídeos."""
    try:
        res = asyncio.run(_analisar_midia(incidente_id, url))
        return {"analisado": res is not None}
    except Exception as e:
        raise self.retry(exc=e, countdown=60)


@celery_app.task(bind=True, max_retries=3)
def enviar_notificacao_email(self, para: str, assunto: str, corpo: str):
    from app.services.notificacao import enviar_email
    try:
        asyncio.run(enviar_email(para, assunto, corpo))
    except Exception as e:
        raise self.retry(exc=e, countdown=60)


@celery_app.task(bind=True, max_retries=3)
def enviar_notificacao_gsm(self, numero: str, mensagem: str):
    from app.services.notificacao import enviar_sms
    if enviar_sms(numero, mensagem) == "falhou":
        raise self.retry(countdown=30)
