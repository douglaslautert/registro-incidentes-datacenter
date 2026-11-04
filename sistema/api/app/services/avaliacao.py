"""Avaliação da correlação (Sprint 6): conjunto de 100–200 pares rotulados por dois técnicos.

Fluxo: a API exporta pares de eventos próximos no tempo (CSV) com a decisão do sistema;
dois técnicos preenchem, cada um, se os dois eventos são o mesmo incidente (1) ou não (0).
Os pares em que os dois concordam formam o gabarito. A meta da Sprint 6 é precisão ≥ 85%:
dos pares que o sistema juntou (anexou ou sugeriu), quantos são de fato o mesmo incidente.
"""
import csv, io

META_PRECISAO = 0.85
COLUNAS = ["par_id", "evento_a", "evento_b", "ativo_a", "ativo_b", "sintoma_a", "sintoma_b",
           "minutos_entre", "mesmo_incidente_sistema", "rotulo_tecnico_1", "rotulo_tecnico_2"]


def _bin(v) -> int | None:
    v = str(v).strip().lower()
    if v in ("1", "sim", "s", "true", "mesmo"):
        return 1
    if v in ("0", "nao", "não", "n", "false", "diferente"):
        return 0
    return None


def kappa(r1: list[int], r2: list[int]) -> float | None:
    """Kappa de Cohen: concordância entre os dois técnicos além do acaso."""
    n = len(r1)
    if n == 0:
        return None
    po = sum(a == b for a, b in zip(r1, r2)) / n
    p1, p2 = sum(r1) / n, sum(r2) / n
    pe = p1 * p2 + (1 - p1) * (1 - p2)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def avaliar(linhas: list[dict]) -> dict:
    """Linhas do CSV rotulado → precisão, revocação, F1 e concordância entre técnicos."""
    rotulados, r1s, r2s, divergentes = [], [], [], 0
    for l in linhas:
        a, b = _bin(l.get("rotulo_tecnico_1", "")), _bin(l.get("rotulo_tecnico_2", ""))
        s = _bin(l.get("mesmo_incidente_sistema", ""))
        if a is None or b is None or s is None:
            continue
        r1s.append(a); r2s.append(b)
        if a != b:
            divergentes += 1
            continue
        rotulados.append((s, a))
    vp = sum(1 for s, g in rotulados if s == 1 and g == 1)
    fp = sum(1 for s, g in rotulados if s == 1 and g == 0)
    fn = sum(1 for s, g in rotulados if s == 0 and g == 1)
    precisao = vp / (vp + fp) if vp + fp else None
    revocacao = vp / (vp + fn) if vp + fn else None
    f1 = (2 * precisao * revocacao / (precisao + revocacao)
          if precisao and revocacao else None)
    return {
        "pares_avaliados": len(rotulados), "pares_divergentes": divergentes,
        "kappa_tecnicos": kappa(r1s, r2s),
        "verdadeiros_positivos": vp, "falsos_positivos": fp, "falsos_negativos": fn,
        "precisao": precisao, "revocacao": revocacao, "f1": f1,
        "meta_precisao": META_PRECISAO,
        "meta_atingida": precisao is not None and precisao >= META_PRECISAO,
        "suficiente": len(rotulados) >= 100,   # o plano pede 100–200 casos
    }


def ler_csv(conteudo: str) -> list[dict]:
    amostra = conteudo[:2048]
    sep = ";" if amostra.count(";") > amostra.count(",") else ","   # Excel em pt-BR usa ;
    return list(csv.DictReader(io.StringIO(conteudo), delimiter=sep))


def escrever_csv(pares: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUNAS, delimiter=";")
    w.writeheader()
    for p in pares:
        w.writerow({c: p.get(c, "") for c in COLUNAS})
    return buf.getvalue()
