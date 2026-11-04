"""Registro de eventos em incidentes — o mesmo caminho para todas as fontes.

  1. Normaliza para o evento canônico (ativo, local, risco, fingerprint)        — Sprint 6
  2. Alerta repetido do Zabbix (mesmo eventid) não gera nada novo               — Sprint 3
  3. Mesmo fingerprint num incidente aberto → deduplica (anexa)                 — Sprint 3
  4. Senão, correlaciona: S = topologia + tempo + local + semântica             — Sprint 6
       S ≥ 0,75 anexa · 0,45 ≤ S < 0,75 abre e sugere · S < 0,45 abre novo
  5. Anexou um evento mais grave → recalcula a prioridade e reaciona o plantão  — Sprint 4
  6. Incidente novo → acionamento com prazo de ACK                              — Sprint 4
Com o banco fora do ar, cai para um modo em memória simplificado (só deduplicação).
"""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.models.incidente import Incidente, Evento
from app.models.acionamento import Acionamento
from app.schemas.evento import EventoCreate
from app.services import embedding, topologia, tarefas
from app.services.normalizacao import normalizar
from app.services.prioridade import calcular_prioridade, inferir_impacto_urgencia
from app.services.correlacao import calcular_score, score_tempo, score_local, decisao
from app.services.escalonamento import registrar_acionamento, atualizar_metricas
import logging, ulid

log = logging.getLogger("registro")

ORDEM = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}
ABERTOS = ("aberto", "em_atendimento")
EXT_MIDIA = {"jpg": "imagem", "jpeg": "imagem", "png": "imagem", "webp": "imagem",
             "mp4": "video", "mov": "video", "webm": "video"}

# Modo memória (banco indisponível)
memoria_incidentes: dict[str, dict] = {}
memoria_eventos: list[dict] = []


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def prioridade_de(ev: EventoCreate) -> str:
    i, u = inferir_impacto_urgencia(ev.sintoma, ev.fonte)
    return calcular_prioridade(ev.seguranca_pessoas, i, u, ev.confianca)


def _titulo(prioridade: str, ev: EventoCreate) -> str:
    sintoma = ev.sintoma if len(ev.sintoma) <= 120 else ev.sintoma[:117] + "…"
    return f"[{prioridade}] {sintoma} — {ev.ativo_id}"


def _vetor_sql(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def tipo_midia(url: str) -> str | None:
    return EXT_MIDIA.get(url.rsplit(".", 1)[-1].lower()) if "." in url else None


def score_correlacao(topo: float, delta: timedelta, local_a: dict, local_b: dict,
                     semantica: float | None) -> float:
    """Com semântica: 0,30·topo + 0,20·tempo + 0,20·local + 0,30·sem. Sem: pesos do MVP."""
    if semantica is None:
        return calcular_score(topo, delta, local_a, local_b)
    return 0.30 * topo + 0.20 * score_tempo(delta) + 0.20 * score_local(local_a, local_b) + 0.30 * semantica


async def _melhor_candidato(db, ev, vetor, modelo, candidatos) -> tuple[Incidente | None, float]:
    if not candidatos:
        return None, 0.0
    g = await topologia.grafo(db)
    linhas = (await db.execute(text("""
        SELECT incidente_id, max(recebido_em) AS ultimo,
               max(CASE WHEN embedding_modelo = :m AND embedding IS NOT NULL
                        THEN 1 - (embedding <=> CAST(:v AS vector)) END) AS sim
          FROM eventos WHERE incidente_id = ANY(:ids) GROUP BY incidente_id
    """), {"m": modelo, "v": _vetor_sql(vetor), "ids": [c.id for c in candidatos]})).mappings().all()
    por_inc = {l["incidente_id"]: l for l in linhas}
    agora, local = _agora(), ev.local.model_dump()
    melhor, melhor_s = None, 0.0
    for c in candidatos:
        l = por_inc.get(c.id, {})
        ultimo = l.get("ultimo") or c.aberto_em
        sim = l.get("sim")
        s = score_correlacao(topologia.score(g, ev.ativo_id, c.ativo_id or ""),
                             agora - ultimo, local, c.local or {},
                             max(0.0, float(sim)) if sim is not None else None)
        if s > melhor_s:
            melhor, melhor_s = c, s
    return melhor, melhor_s


async def registrar(db: AsyncSession, ev: EventoCreate, *, zabbix_eventid: str | None = None,
                    status_origem: str | None = None, raw: dict | None = None,
                    criado_por: str | None = None) -> dict:
    """Registra o evento e devolve a decisão. Em `notificar` vêm os acionamentos a disparar."""
    canon, fp = normalizar(ev)
    try:
        return await _registrar_banco(db, canon, fp, zabbix_eventid, status_origem, raw, criado_por)
    except (SQLAlchemyError, OSError) as e:
        log.warning(f"Banco indisponível, registrando em memória: {e}")
        try:
            await db.rollback()
        except Exception:
            pass
        return _registrar_memoria(canon, fp)


async def _registrar_banco(db, ev, fp, zabbix_eventid, status_origem, raw, criado_por) -> dict:
    agora = _agora()
    if zabbix_eventid:
        dup = (await db.execute(select(Evento).where(
            Evento.zabbix_eventid == zabbix_eventid,
            (Evento.status_origem.is_(None)) | (Evento.status_origem == "PROBLEM"),
        ).limit(1))).scalars().first()
        if dup:
            inc = (await db.execute(select(Incidente).where(Incidente.id == dup.incidente_id))).scalars().first()
            return _resposta(dup.id, ev, dup.incidente_id, inc.prioridade if inc else None,
                             "duplicado", None, [])

    prioridade = prioridade_de(ev)
    vetor, modelo = await embedding.gerar(ev.sintoma)
    janela = max(settings.DEDUP_JANELA_HORAS, settings.CORRELACAO_JANELA_HORAS)
    abertos = (await db.execute(select(Incidente).where(
        Incidente.status.in_(ABERTOS), Incidente.aberto_em >= agora - timedelta(hours=janela),
    ))).scalars().all()

    notificar: list[dict] = []
    sugestao = None
    alvo = next((i for i in abertos if i.fingerprint == fp
                 and i.aberto_em >= agora - timedelta(hours=settings.DEDUP_JANELA_HORAS)), None)
    if alvo:
        dec = "deduplicado"
    else:
        candidatos = [i for i in abertos
                      if i.aberto_em >= agora - timedelta(hours=settings.CORRELACAO_JANELA_HORAS)]
        melhor, s = await _melhor_candidato(db, ev, vetor, modelo, candidatos)
        d = decisao(s) if melhor else "novo"
        if d == "anexa":
            alvo, dec = melhor, "anexado"
        else:
            dec = "sugerido" if d == "sugere" else "novo"
            sugestao = melhor.id if d == "sugere" else None
        log.info(f"Correlação: melhor={getattr(melhor, 'id', None)} score={s:.3f} → {dec}")

    if alvo:
        incidente_id = alvo.id
        if ORDEM.get(prioridade, 9) < ORDEM.get(alvo.prioridade, 9):
            log.info(f"Prioridade recalculada: {incidente_id} {alvo.prioridade}→{prioridade}")
            alvo.prioridade = prioridade
            titulo = f"[ESCALADO] {alvo.titulo}"
            await registrar_acionamento(db, incidente_id, prioridade, titulo, ev.ativo_id)
            notificar.append({"incidente_id": incidente_id, "prioridade": prioridade,
                              "titulo": titulo, "ativo": ev.ativo_id, "nivel": 1})
        prioridade_final = alvo.prioridade
    else:
        incidente_id = str(ulid.new())
        titulo = _titulo(prioridade, ev)
        db.add(Incidente(id=incidente_id, titulo=titulo, prioridade=prioridade, status="aberto",
                         ativo_id=ev.ativo_id, aberto_em=agora, local=ev.local.model_dump(),
                         fingerprint=fp, sugestao_correlacao=sugestao, criado_por=criado_por))
        await db.flush()
        await registrar_acionamento(db, incidente_id, prioridade, titulo, ev.ativo_id)
        notificar.append({"incidente_id": incidente_id, "prioridade": prioridade,
                          "titulo": titulo, "ativo": ev.ativo_id, "nivel": 1})
        prioridade_final = prioridade

    evento_id = str(ulid.new())
    db.add(Evento(
        id=evento_id, incidente_id=incidente_id, fonte=ev.fonte, ativo_id=ev.ativo_id,
        sintoma=ev.sintoma, confianca=ev.confianca, seguranca=ev.seguranca_pessoas,
        local=ev.local.model_dump(), evidencias=list(ev.evidencias or []), recebido_em=agora,
        embedding=vetor, embedding_modelo=modelo, fingerprint=fp,
        zabbix_eventid=zabbix_eventid, status_origem=status_origem, raw_payload=raw,
    ))
    await db.flush()
    for url in ev.evidencias or []:
        if tipo_midia(url):
            tarefas.enfileirar("analisar_midia", incidente_id, url)
    log.info(f"Evento {evento_id} → {incidente_id} [{prioridade_final}] {dec}")
    return _resposta(evento_id, ev, incidente_id, prioridade_final, dec, sugestao, notificar)


def _resposta(evento_id, ev, incidente_id, prioridade, dec, sugestao, notificar) -> dict:
    return {
        "id": evento_id, "fonte": ev.fonte, "ativo_id": ev.ativo_id, "sintoma": ev.sintoma,
        "confianca": ev.confianca, "seguranca_pessoas": ev.seguranca_pessoas,
        "incidente_id": incidente_id, "prioridade": prioridade, "recebido_em": _agora(),
        "decisao_correlacao": dec, "sugestao_correlacao": sugestao, "notificar": notificar,
    }


def _registrar_memoria(ev: EventoCreate, fp: str) -> dict:
    prioridade = prioridade_de(ev)
    alvo = next((i for i in memoria_incidentes.values()
                 if i["fingerprint"] == fp and i["status"] in ABERTOS), None)
    notificar = []
    if alvo:
        incidente_id, dec = alvo["id"], "deduplicado"
        if ORDEM.get(prioridade, 9) < ORDEM.get(alvo["prioridade"], 9):
            alvo["prioridade"] = prioridade
        prioridade = alvo["prioridade"]
    else:
        incidente_id, dec = str(ulid.new()), "novo"
        titulo = _titulo(prioridade, ev)
        memoria_incidentes[incidente_id] = {
            "id": incidente_id, "titulo": titulo, "prioridade": prioridade, "status": "aberto",
            "ativo_id": ev.ativo_id, "aberto_em": _agora(), "fechado_em": None,
            "local": ev.local.model_dump(), "fingerprint": fp, "sugestao_correlacao": None,
        }
        notificar.append({"incidente_id": incidente_id, "prioridade": prioridade,
                          "titulo": titulo, "ativo": ev.ativo_id, "nivel": 1})
    evento_id = str(ulid.new())
    memoria_eventos.append({"id": evento_id, "incidente_id": incidente_id, "fonte": ev.fonte,
                            "ativo_id": ev.ativo_id, "sintoma": ev.sintoma,
                            "evidencias": list(ev.evidencias or []), "recebido_em": _agora()})
    return _resposta(evento_id, ev, incidente_id, prioridade, dec, None, notificar)


async def recuperar_zabbix(db: AsyncSession, eventid: str, raw: dict | None = None) -> dict:
    """RECOVERY do Zabbix (Sprint 1): registra a recuperação e, se o incidente só tem alertas
    do Zabbix e todos se recuperaram, fecha-o. Relato de pessoa mantém o incidente aberto."""
    problema = (await db.execute(select(Evento).where(
        Evento.zabbix_eventid == eventid,
        (Evento.status_origem.is_(None)) | (Evento.status_origem == "PROBLEM"),
    ).order_by(Evento.recebido_em).limit(1))).scalars().first()
    if problema is None:
        return {"msg": "Recuperação de um problema não registrado", "eventid": eventid, "fechado": False}
    ja = (await db.execute(select(Evento.id).where(
        Evento.zabbix_eventid == eventid, Evento.status_origem == "RECOVERY"))).first()
    if not ja:
        db.add(Evento(
            id=str(ulid.new()), incidente_id=problema.incidente_id, fonte="zabbix",
            ativo_id=problema.ativo_id, sintoma=f"RECUPERADO: {problema.sintoma}",
            confianca=problema.confianca, seguranca=False, local=problema.local,
            evidencias=[], recebido_em=_agora(), zabbix_eventid=eventid,
            status_origem="RECOVERY", raw_payload=raw, fingerprint=problema.fingerprint,
        ))
        await db.flush()

    iid = problema.incidente_id
    eventos = (await db.execute(select(Evento.fonte, Evento.zabbix_eventid, Evento.status_origem)
                                .where(Evento.incidente_id == iid))).all()
    inc = (await db.execute(select(Incidente).where(Incidente.id == iid))).scalars().first()
    so_zabbix = all(f == "zabbix" for f, _, _ in eventos)
    problemas = {z for f, z, s in eventos if f == "zabbix" and (s or "PROBLEM") == "PROBLEM"}
    recuperados = {z for f, z, s in eventos if s == "RECOVERY"}
    fechado = False
    if inc and inc.status in ABERTOS and so_zabbix and problemas <= recuperados:
        inc.status, inc.fechado_em = "resolvido", _agora()
        inc.causa_raiz = "Recuperação automática no Zabbix"
        # Recuperado não reescalona: os acionamentos pendentes param aqui
        await db.execute(update(Acionamento).where(Acionamento.incidente_id == iid,
                                                   Acionamento.ack_em.is_(None)).values(escalado=True))
        await db.flush()
        await atualizar_metricas(db, iid)
        fechado = True
        log.info(f"Incidente {iid} fechado pela recuperação do Zabbix")
    return {"msg": "Recuperação registrada", "eventid": eventid, "incidente_id": iid, "fechado": fechado}
