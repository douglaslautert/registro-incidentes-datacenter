from fastapi import APIRouter, Request, BackgroundTasks
from app.schemas.evento import EventoCreate
from app.routers.incidentes import registrar_evento
import logging

router = APIRouter(tags=["webhook"])
log = logging.getLogger("webhook.zabbix")

SEVERITY_MAP = {
    "not classified": 0.4, "information": 0.5, "warning": 0.6,
    "average": 0.7, "high": 0.85, "disaster": 1.0,
}

@router.post("/webhook/zabbix")
async def receber_webhook_zabbix(request: Request, bg: BackgroundTasks):
    """Recebe alertas do Zabbix e converte para EventoCanônico."""
    body = await request.json()
    log.info(f"Webhook Zabbix: {body}")

    severity = body.get("severity", "average").lower()
    confianca = SEVERITY_MAP.get(severity, 0.7)
    host   = body.get("host", "desconhecido")
    trigger = body.get("trigger", "alerta_zabbix")
    status  = body.get("status", "PROBLEM")

    if status.upper() == "RECOVERY":
        return {"msg": "Recovery ignorado", "eventid": body.get("eventid")}

    evento = EventoCreate(
        fonte="zabbix",
        ativo_id=host,
        local={"sala": "datacenter"},
        sintoma=trigger,
        confianca=confianca,
        seguranca_pessoas="power" in trigger.lower() or "ups" in trigger.lower(),
    )
    resultado = await registrar_evento(evento, bg)
    log.info(f"Incidente: {resultado.get('incidente_id')} P={resultado.get('prioridade')}")
    return {"msg": "ok", "incidente_id": resultado.get("incidente_id"),
            "prioridade": resultado.get("prioridade")}
