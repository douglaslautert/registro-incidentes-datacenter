"""Router de incidentes. A lógica de registro e correlação fica em services/registro.py,
compartilhada com o webhook do Zabbix, a ingestão de e-mail e a reconciliação do worker."""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from sqlalchemy import select, update, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from app.database import get_db
from app.models.incidente import Incidente, Evento
from app.models.acionamento import Acionamento, AnaliseMidia
from app.schemas.evento import EventoCreate, EventoResponse, IncidenteResponse
from app.services import registro
from app.services.escalonamento import confirmar_ack, atualizar_metricas
from app.services.notificacao import disparar
from app.services.s3_client import normalizar_url
from app.services.seguranca import Usuario, exigir, REGISTRAR, LER, ATENDER
import logging

router = APIRouter(tags=["incidentes"])
log = logging.getLogger("router.incidentes")

ORDEM_PRIORIDADE = registro.ORDEM
ABERTOS = registro.ABERTOS


async def _buscar(db: AsyncSession, incidente_id: str) -> Incidente | None:
    """Por id — a PK é composta (id, aberto_em) por causa do particionamento."""
    return (await db.execute(select(Incidente).where(Incidente.id == incidente_id))).scalars().first()


@router.post("/incidentes", response_model=EventoResponse, status_code=201)
async def registrar_evento(payload: EventoCreate, bg: BackgroundTasks,
                           db: AsyncSession = Depends(get_db),
                           u: Usuario = Depends(exigir(REGISTRAR))) -> dict:
    res = await registro.registrar(db, payload, criado_por=u.id)
    if res["notificar"]:
        bg.add_task(disparar, res["notificar"])
    return res


@router.get("/incidentes", response_model=list[IncidenteResponse])
async def listar_incidentes(status: str = "aberto,em_atendimento",
                            db: AsyncSession = Depends(get_db),
                            u: Usuario = Depends(exigir(LER))):
    filtro = None if status == "todos" else {s.strip() for s in status.split(",")}
    try:
        n_eventos = (select(Evento.incidente_id, func.count().label("n"))
                     .group_by(Evento.incidente_id).subquery())
        q = select(Incidente, n_eventos.c.n).outerjoin(n_eventos, n_eventos.c.incidente_id == Incidente.id)
        if filtro:
            q = q.where(Incidente.status.in_(filtro))
        linhas = (await db.execute(q)).all()
        itens = [IncidenteResponse(id=i.id, titulo=i.titulo, prioridade=i.prioridade, status=i.status,
                                   ativo_id=i.ativo_id, aberto_em=i.aberto_em, total_eventos=n or 0,
                                   sugestao_correlacao=i.sugestao_correlacao) for i, n in linhas]
    except SQLAlchemyError as e:
        log.warning(f"Listagem no banco falhou, usando memória: {e}")
        itens = [IncidenteResponse(**{k: i[k] for k in ("id", "titulo", "prioridade", "status",
                                                         "ativo_id", "aberto_em")},
                                   total_eventos=sum(1 for e in registro.memoria_eventos
                                                     if e["incidente_id"] == i["id"]))
                 for i in registro.memoria_incidentes.values() if not filtro or i["status"] in filtro]
    return sorted(itens, key=lambda x: (ORDEM_PRIORIDADE.get(x.prioridade, 9), x.aberto_em))


@router.get("/incidentes/{incidente_id}")
async def buscar_incidente(incidente_id: str, db: AsyncSession = Depends(get_db),
                           u: Usuario = Depends(exigir(LER))):
    try:
        inc = await _buscar(db, incidente_id)
    except SQLAlchemyError:
        inc = None
    if inc is None:
        m = registro.memoria_incidentes.get(incidente_id)
        if not m:
            raise HTTPException(404, "Incidente não encontrado")
        evs = [e for e in registro.memoria_eventos if e["incidente_id"] == incidente_id]
        return {**m, "evidencias": [normalizar_url(x) for e in evs for x in e["evidencias"]],
                "eventos": evs, "analises": [], "acionamentos": []}

    eventos = (await db.execute(select(Evento).where(Evento.incidente_id == incidente_id)
                                .order_by(Evento.recebido_em))).scalars().all()
    analises = (await db.execute(select(AnaliseMidia).where(AnaliseMidia.incidente_id == incidente_id)
                                 .order_by(AnaliseMidia.criado_em))).scalars().all()
    acs = (await db.execute(select(Acionamento).where(Acionamento.incidente_id == incidente_id)
                            .order_by(Acionamento.acionado_em))).scalars().all()
    return {
        "id": inc.id, "titulo": inc.titulo, "prioridade": inc.prioridade, "status": inc.status,
        "ativo_id": inc.ativo_id, "aberto_em": inc.aberto_em, "fechado_em": inc.fechado_em,
        "causa_raiz": inc.causa_raiz, "local": inc.local, "criado_por": inc.criado_por,
        "sugestao_correlacao": inc.sugestao_correlacao, "mesclado_em": inc.mesclado_em,
        "evidencias": [normalizar_url(x) for e in eventos for x in (e.evidencias or [])],
        "eventos": [{"id": e.id, "fonte": e.fonte, "sintoma": e.sintoma, "confianca": e.confianca,
                     "recebido_em": e.recebido_em, "status_origem": e.status_origem,
                     "zabbix_eventid": e.zabbix_eventid} for e in eventos],
        "analises": [{"url": a.url, "tipo": a.tipo, "modelo": a.modelo, "descricao": a.descricao,
                      "dados": a.dados, "criado_em": a.criado_em} for a in analises],
        "acionamentos": [{"nivel": a.nivel, "prioridade": a.prioridade, "acionado_em": a.acionado_em,
                          "prazo_em": a.prazo_em, "ack_em": a.ack_em, "ack_por": a.ack_por,
                          "escalado": a.escalado} for a in acs],
    }


async def _encerrar(db, incidente_id: str, status: str, causa: str) -> dict:
    agora = datetime.now(timezone.utc)
    try:
        res = await db.execute(update(Incidente).where(Incidente.id == incidente_id)
                               .values(status=status, causa_raiz=causa, fechado_em=agora))
        if res.rowcount:
            # Fechado não reescalona: os acionamentos pendentes param aqui
            await db.execute(update(Acionamento)
                             .where(Acionamento.incidente_id == incidente_id, Acionamento.ack_em.is_(None))
                             .values(escalado=True))
            await atualizar_metricas(db, incidente_id)
            return {"msg": "Incidente encerrado", "id": incidente_id, "status": status}
    except SQLAlchemyError as e:
        log.warning(f"Encerramento no banco falhou: {e}")
    m = registro.memoria_incidentes.get(incidente_id)
    if not m:
        raise HTTPException(404, "Incidente não encontrado")
    m.update(status=status, causa_raiz=causa, fechado_em=agora)
    return {"msg": "Incidente encerrado", "id": incidente_id, "status": status}


@router.patch("/incidentes/{incidente_id}/fechar")
async def fechar_incidente(incidente_id: str, causa_raiz: str = "",
                           db: AsyncSession = Depends(get_db), u: Usuario = Depends(exigir(ATENDER))):
    return await _encerrar(db, incidente_id, "resolvido", causa_raiz)


@router.patch("/incidentes/{incidente_id}/falso_positivo")
async def marcar_falso_positivo(incidente_id: str, motivo: str = "",
                                db: AsyncSession = Depends(get_db), u: Usuario = Depends(exigir(ATENDER))):
    return await _encerrar(db, incidente_id, "falso_positivo", motivo)


@router.patch("/incidentes/{incidente_id}/ack")
async def confirmar_ack_incidente(incidente_id: str, usuario_id: str | None = None,
                                  db: AsyncSession = Depends(get_db), u: Usuario = Depends(exigir(ATENDER))):
    quem = u.id if u.id != "anonimo" else (usuario_id or "anonimo")
    try:
        ok = await confirmar_ack(db, incidente_id, quem)
    except SQLAlchemyError as e:
        log.warning(f"ACK no banco falhou: {e}")
        ok = False
    if not ok:
        m = registro.memoria_incidentes.get(incidente_id)
        if not m:
            raise HTTPException(404, "Incidente não encontrado")
        m["status"] = "em_atendimento"
    return {"msg": "ACK registrado", "id": incidente_id, "por": quem}


@router.post("/incidentes/{incidente_id}/mesclar")
async def mesclar(incidente_id: str, destino: str, db: AsyncSession = Depends(get_db),
                  u: Usuario = Depends(exigir(ATENDER))):
    """Aceita a sugestão de correlação (Sprint 6): os eventos de `incidente_id` passam para
    `destino`, que fica com a prioridade mais grave; o de origem é encerrado como mesclado."""
    if incidente_id == destino:
        raise HTTPException(400, "Origem e destino são o mesmo incidente")
    origem, alvo = await _buscar(db, incidente_id), await _buscar(db, destino)
    if not origem or not alvo:
        raise HTTPException(404, "Incidente não encontrado")
    if alvo.status not in ABERTOS:
        raise HTTPException(409, "O incidente de destino já está encerrado")
    await db.execute(update(Evento).where(Evento.incidente_id == incidente_id).values(incidente_id=destino))
    if ORDEM_PRIORIDADE.get(origem.prioridade, 9) < ORDEM_PRIORIDADE.get(alvo.prioridade, 9):
        alvo.prioridade = origem.prioridade
    origem.mesclado_em = destino
    origem.sugestao_correlacao = None
    await db.flush()
    await _encerrar(db, incidente_id, "resolvido", f"Mesclado em {destino} por {u.id}")
    return {"msg": "Incidentes mesclados", "origem": incidente_id, "destino": destino,
            "prioridade": alvo.prioridade}
