"""Métricas MTTA/MTTR (Sprints 4 e 6).

MTTA: do primeiro acionamento do plantão ao primeiro ACK. MTTR: da abertura ao fechamento
(resolvido). Antes o MTTA usava o fechamento, que é o MTTR.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.services import registro
from app.services.seguranca import Usuario, exigir, METRICAS
import logging

router = APIRouter(prefix="/api/v1/metricas", tags=["métricas"])
log = logging.getLogger("router.metricas")


@router.get("/resumo")
async def resumo(dias: int = 90, db: AsyncSession = Depends(get_db),
                 u: Usuario = Depends(exigir(METRICAS))):
    """MTTA, MTTR e distribuição por prioridade nos últimos `dias`."""
    try:
        p = {"dias": dias}
        por_prio = {r.prioridade: r.n for r in (await db.execute(text(
            "SELECT prioridade, count(*) AS n FROM incidentes "
            "WHERE aberto_em >= now() - make_interval(days => :dias) GROUP BY prioridade"), p))}
        abertos = (await db.execute(text(
            "SELECT count(*) FROM incidentes WHERE status IN ('aberto','em_atendimento')"))).scalar() or 0
        mtta = (await db.execute(text("""
            SELECT avg(EXTRACT(EPOCH FROM (t.ack - t.acionado)) / 60) FROM (
                SELECT a.incidente_id, min(a.acionado_em) AS acionado, min(a.ack_em) AS ack
                  FROM acionamentos a JOIN incidentes i ON i.id = a.incidente_id
                 WHERE i.aberto_em >= now() - make_interval(days => :dias)
                 GROUP BY a.incidente_id HAVING min(a.ack_em) IS NOT NULL) t"""), p)).scalar()
        mttr = (await db.execute(text("""
            SELECT avg(EXTRACT(EPOCH FROM (fechado_em - aberto_em)) / 3600) FROM incidentes
             WHERE status = 'resolvido' AND fechado_em IS NOT NULL AND mesclado_em IS NULL
               AND aberto_em >= now() - make_interval(days => :dias)"""), p)).scalar()
        fp = (await db.execute(text(
            "SELECT count(*) FROM incidentes WHERE status = 'falso_positivo' "
            "AND aberto_em >= now() - make_interval(days => :dias)"), p)).scalar() or 0
        total_eventos = (await db.execute(text(
            "SELECT count(*) FROM eventos WHERE recebido_em >= now() - make_interval(days => :dias)"), p)).scalar() or 0
        return {
            "periodo_dias": dias, "total_incidentes": sum(por_prio.values()), "abertos": abertos,
            "por_prioridade": por_prio, "total_eventos": total_eventos, "falsos_positivos": fp,
            "mtta_minutos": round(float(mtta), 1) if mtta is not None else None,
            "mttr_horas":   round(float(mttr), 2) if mttr is not None else None,
            "fonte": "banco",
        }
    except Exception as e:
        log.warning(f"Métricas no banco falharam: {e}")

    incs = registro.memoria_incidentes.values()
    por_prio: dict[str, int] = {}
    for i in incs:
        por_prio[i["prioridade"]] = por_prio.get(i["prioridade"], 0) + 1
    return {"periodo_dias": dias, "total_incidentes": len(registro.memoria_incidentes),
            "abertos": sum(1 for i in incs if i["status"] in registro.ABERTOS),
            "por_prioridade": por_prio, "total_eventos": len(registro.memoria_eventos),
            "falsos_positivos": 0, "mtta_minutos": None, "mttr_horas": None, "fonte": "memória"}
