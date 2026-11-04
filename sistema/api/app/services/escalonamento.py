"""Escalonamento do plantão com ACK e reescalonamento (Sprint 4).

Cada acionamento fica na tabela `acionamentos` com o prazo para o ACK (P1 10 min, P2 30,
P3 120, P4 sem prazo). O agendador chama verificar_timeouts() a cada 60 s no worker: o que
passou do prazo sem ACK sobe de nível (entra o 2º nível do plantão), até MAX_NIVEL.
Antes ficava num dicionário em memória da API, que o worker — outro processo — não via.
"""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, update, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.acionamento import Acionamento
from app.models.incidente import Incidente
import logging

log = logging.getLogger("escalonamento")

ACK_TIMEOUT = {"P1": 10, "P2": 30, "P3": 120, "P4": None}   # minutos
MAX_NIVEL = 3
STATUS_ABERTOS = ("aberto", "em_atendimento")


def _agora() -> datetime:
    return datetime.now(timezone.utc)


async def registrar_acionamento(db: AsyncSession, incidente_id: str, prioridade: str,
                                titulo: str, ativo: str, nivel: int = 1,
                                agora: datetime | None = None) -> Acionamento:
    timeout = ACK_TIMEOUT.get(prioridade)
    agora = agora or _agora()
    ac = Acionamento(
        incidente_id=incidente_id, usuario_id="plantao",
        canal="sms" if prioridade in ("P1", "P2") else "email",
        mensagem=titulo, prioridade=prioridade, ativo_id=ativo, nivel=nivel,
        acionado_em=agora, prazo_em=agora + timedelta(minutes=timeout) if timeout else None,
    )
    db.add(ac)
    await db.flush()
    log.info(f"Acionamento: {incidente_id} [{prioridade}] nível {nivel} prazo={timeout}min")
    return ac


async def confirmar_ack(db: AsyncSession, incidente_id: str, usuario_id: str) -> bool:
    """Registra o ACK. O primeiro vale; os seguintes não mudam nada. False se o incidente não existe."""
    inc = (await db.execute(select(Incidente).where(Incidente.id == incidente_id))).scalars().first()
    if inc is None:
        return False
    agora = _agora()
    r = await db.execute(
        update(Acionamento)
        .where(Acionamento.incidente_id == incidente_id, Acionamento.ack_em.is_(None))
        .values(ack_em=agora, ack_por=usuario_id)
    )
    if inc.status == "aberto":
        inc.status = "em_atendimento"
    await db.flush()
    await atualizar_metricas(db, incidente_id)
    log.info(f"ACK {incidente_id} por {usuario_id} ({r.rowcount} acionamento(s))")
    return True


async def verificar_timeouts(db: AsyncSession, agora: datetime | None = None) -> list[dict]:
    """Reescalona o que passou do prazo sem ACK. Retorna os acionamentos a notificar."""
    agora = agora or _agora()
    pendentes = (await db.execute(
        select(Acionamento, Incidente.titulo, Incidente.status)
        .join(Incidente, Incidente.id == Acionamento.incidente_id)
        .where(Acionamento.ack_em.is_(None), Acionamento.escalado.is_(False),
               Acionamento.prazo_em.is_not(None), Acionamento.prazo_em <= agora)
    )).all()
    notificar = []
    for ac, titulo, status in pendentes:
        ac.escalado = True
        if status not in STATUS_ABERTOS:
            continue                       # fechado ou recuperado antes do prazo
        log.warning(f"Sem ACK: {ac.incidente_id} [{ac.prioridade}] nível {ac.nivel} — reescalonando")
        if ac.nivel < MAX_NIVEL:
            novo = await registrar_acionamento(db, ac.incidente_id, ac.prioridade, titulo,
                                               ac.ativo_id, nivel=ac.nivel + 1, agora=agora)
            notificar.append({"incidente_id": ac.incidente_id, "prioridade": ac.prioridade,
                              "titulo": f"[REESCALONADO nível {novo.nivel}] {titulo}",
                              "ativo": ac.ativo_id, "nivel": novo.nivel})
    await db.flush()
    return notificar


async def atualizar_metricas(db: AsyncSession, incidente_id: str) -> None:
    """MTTA (1º acionamento → 1º ACK) e MTTR (abertura → fechamento) em metricas_incidente,
    que alimenta a view v_metricas_periodo e o Grafana."""
    await db.execute(text("""
        INSERT INTO metricas_incidente (incidente_id, mtta_segundos, mttr_segundos, falso_positivo, avaliado_em)
        SELECT i.id,
               (SELECT EXTRACT(EPOCH FROM (min(a.ack_em) - min(a.acionado_em)))
                  FROM acionamentos a WHERE a.incidente_id = i.id),
               CASE WHEN i.fechado_em IS NOT NULL THEN EXTRACT(EPOCH FROM (i.fechado_em - i.aberto_em)) END,
               i.status = 'falso_positivo', now()
          FROM incidentes i WHERE i.id = :iid
        ON CONFLICT (incidente_id) DO UPDATE SET
            mtta_segundos = EXCLUDED.mtta_segundos, mttr_segundos = EXCLUDED.mttr_segundos,
            falso_positivo = EXCLUDED.falso_positivo, avaliado_em = EXCLUDED.avaliado_em
    """), {"iid": incidente_id})
