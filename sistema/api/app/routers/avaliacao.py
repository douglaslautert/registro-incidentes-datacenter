"""Avaliação da correlação (Sprint 6): exporta pares para rotular e calcula a precisão."""
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.services import avaliacao
from app.services.seguranca import Usuario, exigir, METRICAS

router = APIRouter(prefix="/api/v1/avaliacao", tags=["avaliação da correlação"])


@router.get("/pares.csv")
async def exportar_pares(limite: int = 200, horas: int = 4, db: AsyncSession = Depends(get_db),
                         u: Usuario = Depends(exigir(METRICAS))):
    """Pares de eventos com até `horas` de diferença, para dois técnicos rotularem
    (1 = mesmo incidente, 0 = diferentes). `mesmo_incidente_sistema` é a decisão do sistema."""
    r = await db.execute(text("""
        SELECT a.id AS evento_a, b.id AS evento_b, a.ativo_id AS ativo_a, b.ativo_id AS ativo_b,
               a.sintoma AS sintoma_a, b.sintoma AS sintoma_b,
               round(EXTRACT(EPOCH FROM (b.recebido_em - a.recebido_em)) / 60) AS minutos_entre,
               CASE WHEN a.incidente_id = b.incidente_id THEN 1 ELSE 0 END AS mesmo_incidente_sistema
          FROM eventos a JOIN eventos b
            ON b.recebido_em > a.recebido_em
           AND b.recebido_em <= a.recebido_em + make_interval(hours => :horas)
         WHERE coalesce(a.status_origem, 'PROBLEM') = 'PROBLEM'
           AND coalesce(b.status_origem, 'PROBLEM') = 'PROBLEM'
         ORDER BY a.recebido_em DESC LIMIT :limite
    """), {"horas": horas, "limite": min(limite, 1000)})
    pares = [{"par_id": i + 1, **dict(l)} for i, l in enumerate(r.mappings())]
    return Response(avaliacao.escrever_csv(pares), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="pares-correlacao.csv"'})


@router.post("/resultado")
async def calcular(arquivo: UploadFile = File(...), u: Usuario = Depends(exigir(METRICAS))):
    """Recebe o CSV rotulado pelos dois técnicos e devolve precisão, revocação e kappa."""
    bruto = await arquivo.read()
    try:
        conteudo = bruto.decode("utf-8-sig")
    except UnicodeDecodeError:
        conteudo = bruto.decode("latin-1")
    linhas = avaliacao.ler_csv(conteudo)
    if not linhas:
        raise HTTPException(400, "CSV vazio")
    return avaliacao.avaliar(linhas)
