"""Webhook do Zabbix (Sprints 1 e 3): PROBLEM abre ou anexa; RECOVERY registra a recuperação
e fecha o incidente que só tinha alertas do Zabbix. Reenvio do mesmo eventid não duplica."""
from fastapi import APIRouter, Request, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.services import registro
from app.services.normalizacao import de_zabbix
from app.services.notificacao import disparar
from app.services.seguranca import Usuario, exigir, INTEGRAR
import logging

router = APIRouter(tags=["webhook"])
log = logging.getLogger("webhook.zabbix")


@router.post("/webhook/zabbix")
async def receber_webhook_zabbix(request: Request, bg: BackgroundTasks,
                                 db: AsyncSession = Depends(get_db),
                                 u: Usuario = Depends(exigir(INTEGRAR))):
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(400, "Corpo não é JSON")
    log.info(f"Webhook Zabbix: {body}")
    evento, eventid, status = de_zabbix(body)

    if status == "RECOVERY":
        if not eventid:
            return {"msg": "Recuperação sem eventid ignorada"}
        return await registro.recuperar_zabbix(db, eventid, raw=body)

    res = await registro.registrar(db, evento, zabbix_eventid=eventid or None,
                                   status_origem="PROBLEM", raw=body, criado_por="zabbix")
    if res["notificar"]:
        bg.add_task(disparar, res["notificar"])
    log.info(f"Incidente: {res['incidente_id']} P={res['prioridade']} ({res['decisao_correlacao']})")
    return {"msg": "ok", "incidente_id": res["incidente_id"], "prioridade": res["prioridade"],
            "decisao_correlacao": res["decisao_correlacao"]}
