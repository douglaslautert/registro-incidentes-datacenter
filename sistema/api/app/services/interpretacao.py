"""Interpreta o relato falado/escrito e sugere os campos do chamado — regras determinísticas, nunca IA.

Identifica o ativo citado (pelo nome, ID ou código QR), sala e rack, risco a pessoas
e a prioridade que o motor P1–P4 daria. O técnico revisa tudo antes de criar o chamado.
"""
import re, unicodedata
from app.services.prioridade import calcular_prioridade, inferir_impacto_urgencia

# Palavras que não identificam um ativo específico
GENERICAS = {"servidor", "sala", "de", "da", "do", "a", "o", "e"}

# Indícios de risco à segurança de pessoas
RISCO_PESSOAS = ("fumaca", "fogo", "incendio", "queimad", "faisca", "choque",
                 "agua", "alagad", "vazamento", "ferid", "desmai")

# Palavras que seguem "sala" sem ser o nome dela ("sala de servidores", "sala do nobreak")
SALA_NAO = {"de", "da", "do", "das", "dos", "e", "o", "os", "as", "em", "no", "na", "um", "ao"}

# Só "zero um", "zero dois"... viram número: "um" sozinho é artigo ("um alarme")
ZERO_FALADO = re.compile(r"\bzero (um|dois|tres|quatro|cinco|seis|sete|oito|nove)\b")
DIGITO = {"um": "1", "dois": "2", "tres": "3", "quatro": "4", "cinco": "5",
          "seis": "6", "sete": "7", "oito": "8", "nove": "9"}


def normalizar(texto: str) -> str:
    """Minúsculas, sem acentos e sem pontuação (exceto hífen)."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9\- ]", " ", sem_acento.lower())


def _tokens(texto: str) -> set[str]:
    """Palavras do texto; números sem zeros à esquerda ("01" → "1")."""
    norm = ZERO_FALADO.sub(lambda m: "0" + DIGITO[m.group(1)], normalizar(texto))
    out = set()
    for t in re.split(r"[\s\-]+", norm):
        if t:
            out.add(str(int(t)) if t.isdigit() else t)
    return out


def _identificar_ativo(texto: str, ativos: dict[str, dict]) -> dict | None:
    """Ativo citado: código QR ou ID literal; senão, o único cujo nome bate com o texto."""
    norm = normalizar(texto)
    for qr, a in ativos.items():
        if qr.lower() in norm or a["ativo_id"].lower() in norm:
            return {**a, "qr_code": qr}

    # Pontua pelas palavras do nome citadas ("switch" acha o "Switch Core 01")
    toks = _tokens(texto)
    candidatos = []
    for qr, a in ativos.items():
        chave = _tokens(a["nome"]) - GENERICAS
        palavras = {t for t in chave if not t.isdigit()}
        numeros = {t for t in chave if t.isdigit()}
        pontos = len(palavras & toks)
        if pontos:
            candidatos.append((pontos, qr, a, numeros))
    if not candidatos:
        return None
    melhor = max(c[0] for c in candidatos)
    candidatos = [c for c in candidatos if c[0] == melhor]
    if len(candidatos) > 1:
        # Vários do mesmo tipo (ex.: Node 01 e Node 02): desempata pelo número falado
        candidatos = [c for c in candidatos if c[3] and c[3] <= toks]
    if len(candidatos) == 1:
        _, qr, a, _ = candidatos[0]
        return {**a, "qr_code": qr}
    return None  # ambíguo: o técnico escolhe


def interpretar(texto: str) -> dict:
    """Sugestão de chamado a partir do relato."""
    from app.routers.ativos import _qr_map
    texto = (texto or "").strip()
    norm = normalizar(texto)

    ativo = _identificar_ativo(texto, _qr_map)
    sala = ativo["sala"] if ativo else None
    rack = ativo.get("rack") if ativo else None
    if not sala:
        # "sala A", "sala DC", "sala 4", "sala T4", "sala B-12"; "sala de servidores" não é sala
        for m in re.finditer(r"\bsala\s+([a-z]{1,2}-?\d{1,3}|[a-z]{1,2}|\d{1,3})\b", norm):
            if m.group(1) not in SALA_NAO:
                sala = f"sala-{m.group(1).replace('-', '').upper()}"
                break
    m = re.search(r"\brack\s*-?\s*(\d{1,3})\b", norm)
    if m:
        rack = f"rack-{int(m.group(1)):02d}"

    seguranca = any(k in norm for k in RISCO_PESSOAS)
    impacto, urgencia = inferir_impacto_urgencia(texto, "pessoa")
    prioridade = calcular_prioridade(seguranca, impacto, urgencia, 1.0)

    return {
        "sintoma": texto,
        "ativo_id": ativo["ativo_id"] if ativo else None,
        "ativo_nome": ativo["nome"] if ativo else None,
        "sala": sala,
        "rack": rack,
        "seguranca_pessoas": seguranca,
        "prioridade_prevista": prioridade,
    }
