"""Router de métricas MTTA/MTTR — Sprint 6: lê do banco quando disponível."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from app.database import get_db
from app.models.incidente import Incidente, Evento
import logging

router = APIRouter(prefix="/api/v1/metricas", tags=["métricas"])
log = logging.getLogger("router.metricas")


@router.get("/resumo")
async def resumo(db: AsyncSession = Depends(get_db)):
    """MTTA/MTTR e distribuição por prioridade."""
    from app.routers.incidentes import _incidentes, _eventos, _usar_banco

    if _usar_banco():
        try:
            # Total e por prioridade
            res = await db.execute(
                select(Incidente.prioridade, func.count().label("n"))
                .group_by(Incidente.prioridade)
            )
            por_prio = {r.prioridade: r.n for r in res}
            total = sum(por_prio.values())

            # Abertos
            res_ab = await db.execute(
                select(func.count()).where(
                    Incidente.status.in_(["aberto","em_atendimento"])
                )
            )
            abertos = res_ab.scalar() or 0

            # MTTA (tempo médio até atendimento = fechado_em - aberto_em para resolvidos)
            res_mtta = await db.execute(text("""
                SELECT AVG(EXTRACT(EPOCH FROM (fechado_em - aberto_em))/60)
                FROM incidentes
                WHERE status = 'resolvido' AND fechado_em IS NOT NULL
            """))
            mtta = res_mtta.scalar()

            total_eventos = (await db.execute(select(func.count()).select_from(Evento))).scalar() or 0

            return {
                "total_incidentes": total,
                "abertos": abertos,
                "por_prioridade": por_prio,
                "total_eventos": total_eventos,
                "mtta_minutos": round(mtta, 1) if mtta else None,
                "mttr_horas":   round(mtta/60, 2) if mtta else None,
                "fonte": "banco",
            }
        except Exception as e:
            log.warning(f"Métricas banco falhou: {e}")

    # Fallback memória
    por_prio: dict[str,int] = {}
    for i in _incidentes.values():
        p = i["prioridade"]
        por_prio[p] = por_prio.get(p, 0) + 1

    abertos = sum(1 for i in _incidentes.values()
                  if i["status"] in ("aberto","em_atendimento"))
    return {
        "total_incidentes": len(_incidentes),
        "abertos": abertos,
        "por_prioridade": por_prio,
        "total_eventos": len(_eventos),
        "mtta_minutos": None,
        "mttr_horas":   None,
        "fonte": "memória",
    }
