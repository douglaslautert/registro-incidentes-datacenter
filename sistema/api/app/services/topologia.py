"""Topologia de dependências do inventário (Sprint 1): PDU → rack → servidor, switch → servidor.

O grafo vem da tabela topologia_arestas e entra na correlação (Sprint 6): dois eventos em
ativos vizinhos (o servidor e a PDU que o alimenta) pesam mais que em ativos sem ligação.
A falha se propaga nos dois sentidos para efeito de correlação, então o grafo é não dirigido.
"""
import time
from collections import deque
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_cache: dict = {"grafo": None, "quando": 0.0}
CACHE_S = 60

# Distância em saltos → componente topológico do score
SCORE_POR_SALTOS = {0: 1.0, 1: 0.8, 2: 0.6, 3: 0.45}
SCORE_DISTANTE = 0.3          # ligados, mas a 4–5 saltos
SCORE_SEM_LIGACAO = 0.1


def montar_grafo(arestas: list[tuple[str, str]]) -> dict[str, set[str]]:
    g: dict[str, set[str]] = {}
    for a, b in arestas:
        g.setdefault(a, set()).add(b)
        g.setdefault(b, set()).add(a)
    return g


def saltos(grafo: dict[str, set[str]], a: str, b: str, limite: int = 5) -> int | None:
    """Menor número de arestas entre a e b (None se não há caminho até `limite`)."""
    if a == b:
        return 0
    vistos, fila = {a}, deque([(a, 0)])
    while fila:
        no, d = fila.popleft()
        if d >= limite:
            continue
        for viz in grafo.get(no, ()):
            if viz == b:
                return d + 1
            if viz not in vistos:
                vistos.add(viz)
                fila.append((viz, d + 1))
    return None


def score(grafo: dict[str, set[str]], a: str, b: str) -> float:
    d = saltos(grafo, a, b)
    if d is None:
        return SCORE_SEM_LIGACAO
    return SCORE_POR_SALTOS.get(d, SCORE_DISTANTE)


async def grafo(db: AsyncSession) -> dict[str, set[str]]:
    if _cache["grafo"] is None or time.time() - _cache["quando"] > CACHE_S:
        r = await db.execute(text("SELECT origem, destino FROM topologia_arestas WHERE ativo_em"))
        _cache.update(grafo=montar_grafo([(o, d) for o, d in r.all()]), quando=time.time())
    return _cache["grafo"]


def invalidar_cache() -> None:
    _cache["grafo"] = None
