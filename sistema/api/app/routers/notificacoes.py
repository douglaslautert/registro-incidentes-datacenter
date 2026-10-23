"""Router de notificações e ACK de plantão."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.escalonamento import registrar_acionamento, confirmar_ack
import logging

router = APIRouter(prefix="/api/v1/notificacoes", tags=["notificações"])
log = logging.getLogger("router.notificacoes")

class AckPayload(BaseModel):
    usuario_id: str

@router.post("/acionamentos/{incidente_id}")
async def acionar_plantao(incidente_id: str, prioridade: str, titulo: str, ativo: str):
    """Registra acionamento de plantão para um incidente."""
    from app.services.notificacao import notificar_plantao
    registrar_acionamento(incidente_id, prioridade, titulo, ativo)
    await notificar_plantao(incidente_id, prioridade, titulo, ativo)
    return {"msg": "Plantão acionado", "incidente_id": incidente_id}

@router.post("/acionamentos/{incidente_id}/ack")
async def registrar_ack(incidente_id: str, payload: AckPayload):
    """Plantonista confirma ACK do incidente."""
    ok = confirmar_ack(incidente_id, payload.usuario_id)
    if not ok:
        raise HTTPException(404, "Acionamento não encontrado")
    return {"msg": "ACK confirmado", "incidente_id": incidente_id}
