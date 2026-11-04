"""Embeddings para a correlação semântica (Sprint 6).

Com EMBEDDINGS_URL configurado, usa o modelo do cluster GPU (bge-m3, 1024 dimensões) por
uma API compatível com a OpenAI. Sem ele, ou se o serviço cair, usa um embedding local:
metade do vetor marca a categoria do sintoma (térmica, energia, rede...) e a outra metade
as palavras do relato. Relatos da mesma categoria ficam próximos; com palavras em comum,
mais ainda. Cada evento guarda o nome do modelo, e só se comparam vetores do mesmo modelo.
"""
import hashlib, logging, math, re, unicodedata
import httpx
from app.core.config import settings

log = logging.getLogger("embedding")

DIM = 1024
MODELO_LOCAL = "local-v2"

CATEGORIAS = {
    "termica":       ("temperatura", "quente", "calor", "aquec", "quec", "termic", "thermal", "crac",
                      "refrigera", "ar condicionado", "ventila", "cooler"),
    "energia":       ("ups", "nobreak", "bateria", "energia", "power", "pdu", "tensao", "eletric",
                      "queda de luz", "disjuntor", "fonte"),
    "armazenamento": ("disco", "storage", "raid", "disk", "volume", "lun", "nfs", "armazenamento", "lustre"),
    "processamento": ("cpu", "memoria", "memory", "swap", "oom", "processo", "load", "travad", "lento"),
    "rede":          ("rede", "switch", "link", "network", "porta", "ping", "latencia", "flapping",
                      "interface", "roteador", "infiniband", "fibra"),
    "seguranca":     ("agua", "alagad", "vazamento", "fumaca", "fogo", "incendio", "curto", "psu",
                      "faisca", "cheiro de queimado", "choque"),
    "software":      ("job", "scheduler", "slurm", "gpu", "servico", "daemon", "aplicacao", "fila"),
}
_BLOCO = 64                                   # 8 blocos de 64 dims para as categorias
_ORDEM = list(CATEGORIAS) + ["outros"]
_PALAVRAS_INICIO = 512                        # 512 dims para as palavras (hashing)
_VAZIAS = {"de", "da", "do", "das", "dos", "na", "no", "nas", "nos", "em", "um", "uma", "com",
           "por", "para", "que", "esta", "esta", "estao", "foi", "ser", "sala", "rack", "servidor",
           "muito", "mais", "tem", "ter", "sem", "the", "and"}


def _norm(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()


def categorias(texto: str) -> list[str]:
    """Categorias de sintoma presentes no texto (pode haver mais de uma)."""
    t = _norm(texto).replace("_", " ")
    return [c for c, chaves in CATEGORIAS.items() if any(k in t for k in chaves)]


def _unitario(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else v


def embedding_local(texto: str) -> list[float]:
    """Embedding determinístico de 1024 dimensões (sem modelo)."""
    cat = [0.0] * DIM
    for c in categorias(texto) or []:
        i = _ORDEM.index(c) * _BLOCO
        for j in range(i, i + _BLOCO):
            cat[j] = 1.0
    pal = [0.0] * DIM
    for p in re.findall(r"[a-z]{3,}", _norm(texto).replace("_", " ")):
        if p in _VAZIAS:
            continue
        h = hashlib.md5(p[:6].encode()).digest()     # prefixo de 6 letras ≈ radical
        idx = _PALAVRAS_INICIO + int.from_bytes(h[:2], "big") % (DIM - _PALAVRAS_INICIO)
        pal[idx] += 1.0 if h[2] & 1 else -1.0
    cat, pal = _unitario(cat), _unitario(pal)
    # Categoria pesa 0,6 e palavras 0,4: mesma categoria com palavras diferentes ≈ 0,69
    return _unitario([0.6 * a + 0.4 * b for a, b in zip(cat, pal)])


async def gerar(texto: str) -> tuple[list[float], str]:
    """(vetor, modelo). Tenta o modelo do cluster GPU e cai para o local se não houver."""
    if settings.EMBEDDINGS_URL:
        try:
            headers = {"Authorization": f"Bearer {settings.IA_API_KEY}"} if settings.IA_API_KEY else {}
            async with httpx.AsyncClient(timeout=min(settings.IA_TIMEOUT_S, 10)) as c:
                r = await c.post(f"{settings.EMBEDDINGS_URL.rstrip('/')}/embeddings", headers=headers,
                                 json={"model": settings.EMBEDDINGS_MODEL, "input": texto})
                r.raise_for_status()
                vetor = r.json()["data"][0]["embedding"]
            if len(vetor) == DIM:
                return _unitario([float(x) for x in vetor]), settings.EMBEDDINGS_MODEL
            log.warning(f"Embedding de {len(vetor)} dimensões (esperado {DIM}) — usando o local")
        except Exception as e:
            log.warning(f"Serviço de embeddings indisponível ({e}) — usando o local")
    return embedding_local(texto), MODELO_LOCAL


def similaridade_cosseno(a, b) -> float:
    """Similaridade cosseno entre dois embeddings (0 se inválidos)."""
    if a is None or b is None or len(a) == 0 or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return max(0.0, dot / (na * nb))
