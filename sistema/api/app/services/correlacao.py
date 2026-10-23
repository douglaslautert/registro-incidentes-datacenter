"""Motor de correlação — S = 0.35·topo + 0.25·tempo + 0.20·local + 0.20·sem"""
import math
from datetime import timedelta

TAU_MINUTES      = 10.0
THRESHOLD_AUTO   = 0.75
THRESHOLD_SUGERE = 0.45

def score_tempo(delta: timedelta) -> float:
    return math.exp(-delta.total_seconds() / 60 / TAU_MINUTES)

def score_local(a: dict, b: dict) -> float:
    if a.get("rack") and a.get("rack") == b.get("rack"):           return 1.0
    if a.get("fileira") and a.get("fileira") == b.get("fileira"):  return 0.6
    if a.get("sala") == b.get("sala"):                             return 0.3
    return 0.0

def score_semantico(ea: list, eb: list) -> float:
    if not ea or not eb:
        return 0.0
    dot = sum(x * y for x, y in zip(ea, eb))
    na  = math.sqrt(sum(x**2 for x in ea))
    nb  = math.sqrt(sum(x**2 for x in eb))
    return dot / (na * nb) if na and nb else 0.0

def calcular_score(
    topologia: float,
    delta: timedelta,
    local_a: dict,
    local_b: dict,
    embed_a: list = [],
    embed_b: list = [],
) -> float:
    return (
        0.35 * topologia +
        0.25 * score_tempo(delta) +
        0.20 * score_local(local_a, local_b) +
        0.20 * score_semantico(embed_a, embed_b)
    )

def decisao(score: float) -> str:
    if score >= THRESHOLD_AUTO:   return "anexa"
    if score >= THRESHOLD_SUGERE: return "sugere"
    return "novo"


def calcular_score_completo(
    topo: float,
    delta,
    local_a: dict,
    local_b: dict,
    emb_a=None,
    emb_b=None,
) -> float:
    """Score completo Sprint 5: usa embeddings se disponíveis."""
    if emb_a and emb_b:
        return (
            0.30 * topo +
            0.20 * score_tempo(delta) +
            0.20 * score_local(local_a, local_b) +
            0.30 * score_semantico(emb_a, emb_b)
        )
    return calcular_score(topo, delta, local_a, local_b)
