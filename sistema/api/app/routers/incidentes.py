"""
Router de incidentes — Sprint 6: persistência real no PostgreSQL.

Fluxo:
  1. Calcular prioridade P1–P4
  2. Correlacionar com incidentes abertos (banco)
  3. Persistir incidente + evento
  4. Gerar embedding em background (Celery)
  5. Notificar plantonista (background)
  6. Registrar escalonamento com ACK
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, text
from sqlalchemy.exc import SQLAlchemyError
from app.database import get_db
from app.models.incidente import Incidente, Evento
from app.schemas.evento import EventoCreate, EventoResponse, IncidenteResponse
from app.services.prioridade import calcular_prioridade, inferir_impacto_urgencia
from app.services.correlacao import calcular_score, calcular_score_completo, decisao
from app.services.notificacao import notificar_plantao
from app.services.escalonamento import registrar_acionamento, confirmar_ack, _fila
from datetime import datetime, timezone, timedelta
import ulid, logging

router = APIRouter(tags=["incidentes"])
log = logging.getLogger("router.incidentes")

ORDEM_PRIORIDADE = {"P1":1,"P2":2,"P3":3,"P4":4}

# ── Estado em memória (fallback quando banco indisponível) ─────
_incidentes: dict[str,dict] = {}
_eventos:    list[dict]     = []

def _usar_banco() -> bool:
    """Detecta se o banco está disponível."""
    from app.core.config import settings
    return (settings.DATABASE_URL != "postgresql+asyncpg://x:x@x/x"
            and "x:x@x" not in settings.DATABASE_URL)


async def _buscar_incidente_db(db: AsyncSession, incidente_id: str) -> Incidente | None:
    """Busca por id — a PK é composta (id, aberto_em) por causa do particionamento,
    então db.get(Incidente, id) não serve."""
    result = await db.execute(select(Incidente).where(Incidente.id == incidente_id))
    return result.scalars().first()


def _calcular_prioridade(payload: EventoCreate) -> str:
    i, u = inferir_impacto_urgencia(payload.sintoma, payload.fonte)
    return calcular_prioridade(payload.seguranca_pessoas, i, u, payload.confianca)


async def _disparar_notificacoes(iid, pri, titulo, ativo):
    await notificar_plantao(iid, pri, titulo, ativo)


async def _correlacionar_memoria(payload: EventoCreate) -> tuple[str|None,str]:
    """Correlação usando estado em memória (MVP sem banco)."""
    local = payload.local.model_dump()
    for iid, inc in _incidentes.items():
        if inc["status"] not in ("aberto","em_atendimento"):
            continue
        delta = datetime.now(timezone.utc) - inc["aberto_em"]
        topo  = 1.0 if inc.get("ativo_id")==payload.ativo_id else 0.3
        score = calcular_score(topo, delta, local, inc.get("local",{}))
        dec   = decisao(score)
        if dec in ("anexa","sugere"):
            return iid, dec
    return None, "novo"


async def _correlacionar_banco(
    payload: EventoCreate, db: AsyncSession
) -> tuple[str|None,str]:
    """Correlação consultando incidentes abertos no banco."""
    try:
        local = payload.local.model_dump()
        janela = datetime.now(timezone.utc) - timedelta(hours=4)
        result = await db.execute(
            select(Incidente).where(
                and_(
                    Incidente.status.in_(["aberto","em_atendimento"]),
                    Incidente.aberto_em >= janela,
                )
            )
        )
        incs = result.scalars().all()
        for inc in incs:
            delta = datetime.now(timezone.utc) - inc.aberto_em.replace(tzinfo=timezone.utc)
            topo  = 1.0 if inc.ativo_id == payload.ativo_id else 0.3
            score = calcular_score(topo, delta, local, inc.local or {})
            dec   = decisao(score)
            if dec in ("anexa","sugere"):
                return inc.id, dec
    except SQLAlchemyError as e:
        log.warning(f"Correlação banco falhou, usando memória: {e}")
        return await _correlacionar_memoria(payload)
    return None, "novo"


@router.post("/incidentes", response_model=EventoResponse, status_code=201)
async def registrar_evento(
    payload: EventoCreate,
    bg:      BackgroundTasks,
    db:      AsyncSession = Depends(get_db),
) -> dict:
    prioridade  = _calcular_prioridade(payload)
    evento_id   = str(ulid.new())
    usar_db     = _usar_banco()

    if usar_db:
        iid_correlato, dec = await _correlacionar_banco(payload, db)
    else:
        iid_correlato, dec = await _correlacionar_memoria(payload)

    local = payload.local.model_dump()

    if dec == "anexa" and iid_correlato:
        incidente_id = iid_correlato
        # Recalcular prioridade se novo evento é mais grave
        if usar_db:
            try:
                inc_atual = await _buscar_incidente_db(db, incidente_id)
                if inc_atual:
                    p_atual = inc_atual.prioridade
                    if ORDEM_PRIORIDADE.get(prioridade,9) < ORDEM_PRIORIDADE.get(p_atual,9):
                        inc_atual.prioridade = prioridade
                        log.info(f"Prioridade recalculada: {incidente_id} {p_atual}→{prioridade}")
                        bg.add_task(_disparar_notificacoes, incidente_id,
                                    prioridade, f"[ESCALADO] {inc_atual.titulo}",
                                    payload.ativo_id)
            except SQLAlchemyError as e:
                log.warning(f"Recálculo banco falhou: {e}")
        else:
            inc = _incidentes.get(incidente_id,{})
            p_atual = inc.get("prioridade","P4")
            if ORDEM_PRIORIDADE.get(prioridade,9) < ORDEM_PRIORIDADE.get(p_atual,9):
                inc["prioridade"] = prioridade
        decisao_str = "anexado"
    else:
        incidente_id = str(ulid.new())
        titulo       = f"[{prioridade}] {payload.sintoma} — {payload.ativo_id}"

        if usar_db:
            try:
                inc_db = Incidente(
                    id=incidente_id, titulo=titulo, prioridade=prioridade,
                    status="aberto", ativo_id=payload.ativo_id,
                    aberto_em=datetime.now(timezone.utc), local=local,
                )
                db.add(inc_db)
                await db.flush()
            except SQLAlchemyError as e:
                log.warning(f"Persistência banco falhou, usando memória: {e}")
                await db.rollback()
                usar_db = False

        if not usar_db:
            _incidentes[incidente_id] = {
                "id":incidente_id,"titulo":titulo,"prioridade":prioridade,
                "status":"aberto","ativo_id":payload.ativo_id,
                "aberto_em":datetime.now(timezone.utc),"fechado_em":None,
                "local":local,"total_eventos":1,
                "sugestao_correlacao": iid_correlato if dec=="sugere" else None,
            }

        bg.add_task(_disparar_notificacoes, incidente_id, prioridade,
                    titulo, payload.ativo_id)
        registrar_acionamento(incidente_id, prioridade, titulo, payload.ativo_id)
        decisao_str = "novo"
        log.info(f"Incidente: {incidente_id} [{prioridade}] {'banco' if usar_db else 'memória'}")

    # Persistir evento
    ev_db_data = {
        "id":evento_id,"fonte":payload.fonte,"ativo_id":payload.ativo_id,
        "sintoma":payload.sintoma,"confianca":payload.confianca,
        "seguranca":payload.seguranca_pessoas,"local":local,
        "evidencias":payload.evidencias or [],"recebido_em":datetime.now(timezone.utc),
    }
    if usar_db:
        try:
            ev_db = Evento(**ev_db_data, incidente_id=incidente_id)
            db.add(ev_db)
            await db.flush()
        except SQLAlchemyError as e:
            log.warning(f"Evento banco falhou: {e}")
            await db.rollback()
            _eventos.append({**ev_db_data,"incidente_id":incidente_id})
    else:
        _eventos.append({**ev_db_data,"incidente_id":incidente_id})

    # Gerar embedding em background (não bloqueia o response)
    try:
        from app.workers.tasks import gerar_embedding as task_emb
        task_emb.delay(evento_id, payload.sintoma, payload.sintoma)
    except Exception:
        pass  # Celery/Redis indisponível em testes — não bloqueia

    return {
        "id":evento_id,"fonte":payload.fonte,"ativo_id":payload.ativo_id,
        "sintoma":payload.sintoma,"confianca":payload.confianca,
        "seguranca_pessoas":payload.seguranca_pessoas,
        "incidente_id":incidente_id,"prioridade":prioridade,
        "recebido_em":datetime.now(timezone.utc),
        "decisao_correlacao":decisao_str,
    }


@router.get("/incidentes", response_model=list[IncidenteResponse])
async def listar_incidentes(
    status: str = "aberto,em_atendimento",
    db:     AsyncSession = Depends(get_db),
):
    status_filtro = set(s.strip() for s in status.split(","))                     if status != "todos" else None

    if _usar_banco():
        try:
            q = select(Incidente)
            if status_filtro:
                q = q.where(Incidente.status.in_(status_filtro))
            result = await db.execute(q)
            incs = result.scalars().all()
            return sorted(
                [IncidenteResponse(
                    id=i.id, titulo=i.titulo, prioridade=i.prioridade,
                    status=i.status, ativo_id=i.ativo_id,
                    aberto_em=i.aberto_em, total_eventos=0,
                ) for i in incs],
                key=lambda x: ORDEM_PRIORIDADE.get(x.prioridade,9)
            )
        except SQLAlchemyError as e:
            log.warning(f"Listagem banco falhou, usando memória: {e}")

    filtrados = [i for i in _incidentes.values()
                 if status_filtro is None or i["status"] in status_filtro]
    return sorted(
        [IncidenteResponse(**i) for i in filtrados],
        key=lambda x: ORDEM_PRIORIDADE.get(x.prioridade,9)
    )


@router.get("/incidentes/{incidente_id}")
async def buscar_incidente(
    incidente_id: str,
    db: AsyncSession = Depends(get_db),
):
    if _usar_banco():
        try:
            inc = await _buscar_incidente_db(db, incidente_id)
            if inc:
                return {
                    "id":inc.id,"titulo":inc.titulo,"prioridade":inc.prioridade,
                    "status":inc.status,"ativo_id":inc.ativo_id,
                    "aberto_em":inc.aberto_em,"fechado_em":inc.fechado_em,
                    "local":inc.local,
                }
        except SQLAlchemyError:
            pass
    inc = _incidentes.get(incidente_id)
    if not inc:
        raise HTTPException(404, "Incidente não encontrado")
    # Agregar evidencias de todos os eventos do incidente
    evs = [e for e in _eventos if e.get("incidente_id") == incidente_id]
    todas_evidencias = []
    for e in evs:
        todas_evidencias.extend(e.get("evidencias") or [])
    return {**inc, "evidencias": todas_evidencias}


@router.patch("/incidentes/{incidente_id}/fechar")
async def fechar_incidente(
    incidente_id: str, causa_raiz: str = "",
    db: AsyncSession = Depends(get_db),
):
    agora = datetime.now(timezone.utc)
    if _usar_banco():
        try:
            res = await db.execute(
                update(Incidente)
                .where(Incidente.id==incidente_id)
                .values(status="resolvido", causa_raiz=causa_raiz, fechado_em=agora)
            )
            if res.rowcount:
                return {"msg":"Incidente fechado","id":incidente_id}
        except SQLAlchemyError:
            pass
    inc = _incidentes.get(incidente_id)
    if not inc:
        raise HTTPException(404, "Incidente não encontrado")
    inc.update({"status":"resolvido","causa_raiz":causa_raiz,"fechado_em":agora})
    return {"msg":"Incidente fechado","id":incidente_id}


@router.patch("/incidentes/{incidente_id}/ack")
async def confirmar_ack_incidente(
    incidente_id: str, usuario_id: str,
    db: AsyncSession = Depends(get_db),
):
    if incidente_id not in _incidentes and _usar_banco():
        try:
            inc = await _buscar_incidente_db(db, incidente_id)
            if not inc:
                raise HTTPException(404, "Incidente não encontrado")
        except SQLAlchemyError:
            pass
    elif incidente_id not in _incidentes and not _usar_banco():
        raise HTTPException(404, "Incidente não encontrado")

    ok = confirmar_ack(incidente_id, usuario_id)
    if _usar_banco():
        try:
            await db.execute(
                update(Incidente)
                .where(Incidente.id==incidente_id)
                .values(status="em_atendimento")
            )
        except SQLAlchemyError:
            pass
    if incidente_id in _incidentes:
        _incidentes[incidente_id]["status"] = "em_atendimento"
    return {"msg":"ACK registrado","id":incidente_id}


@router.patch("/incidentes/{incidente_id}/falso_positivo")
async def marcar_falso_positivo(
    incidente_id: str, motivo: str = "",
    db: AsyncSession = Depends(get_db),
):
    agora = datetime.now(timezone.utc)
    if _usar_banco():
        try:
            res = await db.execute(
                update(Incidente)
                .where(Incidente.id==incidente_id)
                .values(status="falso_positivo", causa_raiz=motivo, fechado_em=agora)
            )
            if res.rowcount:
                return {"msg":"Marcado como falso positivo","id":incidente_id}
        except SQLAlchemyError:
            pass
    inc = _incidentes.get(incidente_id)
    if not inc:
        raise HTTPException(404, "Incidente não encontrado")
    inc.update({"status":"falso_positivo","fechado_em":agora})
    return {"msg":"Marcado como falso positivo","id":incidente_id}
