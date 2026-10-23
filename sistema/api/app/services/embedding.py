"""Serviço de geração de embeddings para correlação semântica (Sprint 5)."""
import hashlib, logging, math

log = logging.getLogger("embedding")

# Categorias de sintomas — cada categoria ocupa um bloco no vetor
# Isso garante que sintomas da mesma categoria tenham similaridade maior
CATEGORIAS = {
    "termica":    ["temperatura_alta","temperatura_critica","superaquecimento"],
    "energia":    ["ups_sem_bateria","ups_bateria_baixa","ups_falha"],
    "armazenamento": ["disco_cheio","disco_lento","raid_degradado","storage_offline"],
    "processamento": ["cpu_alta","cpu_100","processo_travado","memoria_cheia","swap_alta","oom_killer"],
    "rede":       ["link_down_switch","link_flapping","rede_lenta"],
    "seguranca":  ["deteccao_agua","curto_circuito","falha_psu"],
    "software":   ["job_scheduler_down","gpu_falha"],
}

# Índice invertido: sintoma → categoria
SINTOMA_CATEGORIA = {}
for cat, sintomas in CATEGORIAS.items():
    for s in sintomas:
        SINTOMA_CATEGORIA[s] = cat

# Bloco no vetor por categoria (cada bloco tem 128 dims)
BLOCO_CATEGORIA = {
    "termica":       (0,   128),
    "energia":       (128, 256),
    "armazenamento": (256, 384),
    "processamento": (384, 512),
    "rede":          (512, 640),
    "seguranca":     (640, 768),
    "software":      (768, 896),
    "desconhecido":  (896, 1024),
}

DIM = 1024


def gerar_embedding(sintoma: str, descricao: str = "") -> list[float]:
    """
    Gera embedding determinístico por categoria de sintoma.
    Sintomas da mesma categoria têm similaridade maior que de categorias diferentes.
    Sprint 6+: substituir por sentence-transformers multilingual.
    """
    vetor = [0.0] * DIM

    texto = f"{sintoma} {descricao}".lower().strip()

    # Identificar categoria
    categoria = SINTOMA_CATEGORIA.get(sintoma, "desconhecido")
    inicio, fim = BLOCO_CATEGORIA[categoria]

    # Preencher bloco da categoria com hash do sintoma
    h = hashlib.sha256(sintoma.encode()).digest()
    for i in range(fim - inicio):
        vetor[inicio + i] = h[i % len(h)] / 255.0

    # Sinal fraco em outras categorias (10% da amplitude)
    h2 = hashlib.sha256(texto.encode()).digest()
    for i in range(DIM):
        if inicio <= i < fim:
            continue
        vetor[i] = (h2[i % len(h2)] / 255.0) * 0.1

    # Normalizar para norma unitária
    norma = math.sqrt(sum(v*v for v in vetor)) or 1.0
    vetor = [v / norma for v in vetor]

    log.debug(f"Embedding: sintoma={sintoma} categoria={categoria}")
    return vetor


def similaridade_cosseno(a, b) -> float:
    """Calcula similaridade cosseno entre dois embeddings. Retorna 0 se inválido."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x*y for x,y in zip(a,b))
    na  = math.sqrt(sum(x*x for x in a)) or 1.0
    nb  = math.sqrt(sum(y*y for y in b)) or 1.0
    return max(0.0, dot / (na * nb))
