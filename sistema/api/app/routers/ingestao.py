"""Ingestão de relatos por e-mail (Sprint 6: normalização de todas as fontes no evento canônico).

Quem lê a caixa de e-mail (script, fetchmail, regra do servidor de correio) envia aqui o
remetente, o assunto e o corpo, com o TOKEN_SERVICO. O texto é interpretado (ativo, sala,
risco) e segue o mesmo registro do PWA e do Zabbix, com confiança 0,6 por ser texto livre.
"""
from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.services import registro
from app.services.normalizacao import de_email
from app.services.notificacao import disparar
from app.services.seguranca import Usuario, exigir, INTEGRAR

router = APIRouter(prefix="/api/v1/ingestao", tags=["ingestão"])


class Email(BaseModel):
    remetente: str = Field(max_length=300)
    assunto: str = Field(default="", max_length=500)
    corpo: str = Field(default="", max_length=20000)


@router.post("/email", status_code=201)
async def receber_email(msg: Email, bg: BackgroundTasks, db: AsyncSession = Depends(get_db),
                        u: Usuario = Depends(exigir(INTEGRAR))):
    evento = de_email(msg.remetente, msg.assunto, msg.corpo)
    res = await registro.registrar(db, evento, raw=msg.model_dump(), criado_por=f"email:{msg.remetente}")
    if res["notificar"]:
        bg.add_task(disparar, res["notificar"])
    return {k: v for k, v in res.items() if k != "notificar"}
