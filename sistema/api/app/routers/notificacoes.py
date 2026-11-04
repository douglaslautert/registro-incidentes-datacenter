"""Router de notificações e ACK de plantão (Sprint 4)."""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.acionamento import Acionamento
from app.services.escalonamento import registrar_acionamento, confirmar_ack
from app.services.notificacao import notificar_plantao
from app.services.seguranca import Usuario, exigir, ATENDER, LER
import logging

router = APIRouter(prefix="/api/v1/notificacoes", tags=["notificações"])
log = logging.getLogger("router.notificacoes")


class AckPayload(BaseModel):
    usuario_id: str | None = None


@router.post("/acionamentos/{incidente_id}")
async def acionar_plantao(incidente_id: str, prioridade: str, titulo: str, ativo: str,
                          db: AsyncSession = Depends(get_db), u: Usuario = Depends(exigir(ATENDER))):
    """Aciona o plantão manualmente para um incidente."""
    await registrar_acionamento(db, incidente_id, prioridade, titulo, ativo)
    feito = await notificar_plantao(incidente_id, prioridade, titulo, ativo)
    return {"msg": "Plantão acionado", "incidente_id": incidente_id, "canais": feito}


@router.post("/acionamentos/{incidente_id}/ack")
async def registrar_ack(incidente_id: str, payload: AckPayload, db: AsyncSession = Depends(get_db),
                        u: Usuario = Depends(exigir(ATENDER))):
    """Plantonista confirma o ACK do incidente (o primeiro vale)."""
    quem = u.id if u.id != "anonimo" else (payload.usuario_id or "anonimo")
    if not await confirmar_ack(db, incidente_id, quem):
        raise HTTPException(404, "Incidente não encontrado")
    return {"msg": "ACK confirmado", "incidente_id": incidente_id, "por": quem}


@router.get("/pendentes")
async def pendentes(db: AsyncSession = Depends(get_db), u: Usuario = Depends(exigir(LER))):
    """Acionamentos ainda sem ACK, com o prazo de cada um."""
    acs = (await db.execute(select(Acionamento).where(Acionamento.ack_em.is_(None),
                                                      Acionamento.escalado.is_(False))
                            .order_by(Acionamento.prazo_em))).scalars().all()
    return [{"incidente_id": a.incidente_id, "prioridade": a.prioridade, "nivel": a.nivel,
             "acionado_em": a.acionado_em, "prazo_em": a.prazo_em} for a in acs]
