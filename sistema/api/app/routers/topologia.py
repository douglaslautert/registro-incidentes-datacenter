"""Topologia de dependências do inventário (Sprint 1): PDU → rack → servidor, switch → servidor."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.services import topologia
from app.services.seguranca import Usuario, exigir, LER, GERIR

router = APIRouter(prefix="/api/v1/topologia", tags=["topologia"])


class Aresta(BaseModel):
    origem: str = Field(min_length=1)
    destino: str = Field(min_length=1)
    tipo: str = "alimenta"          # alimenta | contem | rede
    peso: float = 1.0


@router.get("/arestas")
async def listar(db: AsyncSession = Depends(get_db), u: Usuario = Depends(exigir(LER))):
    r = await db.execute(text("SELECT origem, destino, tipo, peso FROM topologia_arestas "
                              "WHERE ativo_em ORDER BY origem, destino"))
    return [dict(l) for l in r.mappings()]


@router.post("/arestas", status_code=201)
async def criar(a: Aresta, db: AsyncSession = Depends(get_db), u: Usuario = Depends(exigir(GERIR))):
    if a.origem == a.destino:
        raise HTTPException(400, "Origem e destino iguais")
    await db.execute(text("""
        INSERT INTO topologia_arestas (origem, destino, tipo, peso) VALUES (:origem, :destino, :tipo, :peso)
        ON CONFLICT (origem, destino) DO UPDATE SET tipo = EXCLUDED.tipo, peso = EXCLUDED.peso, ativo_em = true
    """), a.model_dump())
    topologia.invalidar_cache()
    return {"msg": "Aresta gravada", **a.model_dump()}


@router.delete("/arestas")
async def remover(origem: str, destino: str, db: AsyncSession = Depends(get_db),
                  u: Usuario = Depends(exigir(GERIR))):
    r = await db.execute(text("UPDATE topologia_arestas SET ativo_em = false "
                              "WHERE origem = :o AND destino = :d"), {"o": origem, "d": destino})
    if not r.rowcount:
        raise HTTPException(404, "Aresta não encontrada")
    topologia.invalidar_cache()
    return {"msg": "Aresta desativada"}


@router.get("/distancia")
async def distancia(a: str, b: str, db: AsyncSession = Depends(get_db), u: Usuario = Depends(exigir(LER))):
    """Saltos entre dois ativos e o componente topológico do score de correlação."""
    g = await topologia.grafo(db)
    return {"a": a, "b": b, "saltos": topologia.saltos(g, a, b), "score": topologia.score(g, a, b)}
