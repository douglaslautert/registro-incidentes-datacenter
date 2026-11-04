"""Análise de fotos e vídeos por modelo de visão no cluster GPU (Sprint 5).

O modelo (servido pelo vLLM, API compatível com a OpenAI) lê LEDs, displays e etiquetas.
Do vídeo saem quadros-chave (PyAV, sem ffmpeg externo), analisados como fotos.
Degradação graciosa: sem VISION_URL ou com o serviço fora do ar, devolve None e o
sistema segue sem a análise.
"""
import base64, io, json, logging, re
import httpx
from app.core.config import settings

log = logging.getLogger("visao")

PROMPT = (
    "Você analisa fotos de equipamentos de um datacenter para um técnico de plantão. "
    "Responda só com um JSON, em português, com as chaves: "
    '"descricao" (uma frase sobre o que se vê), "leds" (lista: cor e estado de cada LED de alerta), '
    '"displays" (lista: textos ou códigos de erro em telas), "etiquetas" (lista: identificações '
    'legíveis, como nome do servidor ou patrimônio), "riscos" (lista: água, fumaça, fogo, cabo solto, '
    'peça danificada; vazia se nada), "risco_pessoas" (true se há fumaça, fogo, água perto de energia '
    "ou fios expostos)."
)


def configurado() -> bool:
    return bool(settings.VISION_URL)


def quadros_chave(dados: bytes, quantidade: int = 4, largura: int = 768) -> list[bytes]:
    """JPEGs de quadros espaçados ao longo do vídeo (início, 1/4, 1/2, 3/4...)."""
    import av
    quadros = []
    with av.open(io.BytesIO(dados)) as c:
        if not c.streams.video:
            return []
        v = c.streams.video[0]
        duracao = float(c.duration / 1_000_000) if c.duration else 0.0
        alvos = [duracao * i / quantidade for i in range(quantidade)] if duracao else [0.0]
        for t in alvos:
            try:
                if t > 0:
                    c.seek(int(t / v.time_base), stream=v, any_frame=False, backward=True)
                quadro = next(c.decode(v))
            except Exception:          # StopIteration no fim, erros de decodificação do PyAV
                continue
            img = quadro.to_image()
            if img.width > largura:
                img = img.resize((largura, int(img.height * largura / img.width)))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=80)
            quadros.append(buf.getvalue())
    return quadros


def _json_da_resposta(texto: str) -> dict:
    m = re.search(r"\{.*\}", texto, re.S)
    try:
        return json.loads(m.group(0)) if m else {"descricao": texto.strip()}
    except json.JSONDecodeError:
        return {"descricao": texto.strip()}


async def analisar_imagens(imagens: list[tuple[bytes, str]]) -> dict | None:
    """Envia uma ou mais imagens ao modelo. None = sem IA (não configurada ou fora do ar)."""
    if not configurado() or not imagens:
        return None
    conteudo = [{"type": "text", "text": PROMPT}] + [
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(d).decode()}"}}
        for d, mime in imagens
    ]
    headers = {"Authorization": f"Bearer {settings.IA_API_KEY}"} if settings.IA_API_KEY else {}
    try:
        async with httpx.AsyncClient(timeout=settings.IA_TIMEOUT_S) as c:
            r = await c.post(f"{settings.VISION_URL.rstrip('/')}/chat/completions", headers=headers, json={
                "model": settings.VISION_MODEL, "temperature": 0, "max_tokens": 600,
                "messages": [{"role": "user", "content": conteudo}],
            })
            r.raise_for_status()
            texto = r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log.warning(f"Modelo de visão indisponível ({e}) — seguindo sem análise")
        return None
    dados = _json_da_resposta(texto)
    dados.setdefault("descricao", "")
    return {"modelo": settings.VISION_MODEL, "descricao": str(dados["descricao"]), "dados": dados}


async def analisar(dados: bytes, tipo: str, mime: str = "image/jpeg") -> dict | None:
    """tipo: 'imagem' ou 'video'."""
    if not configurado():
        return None
    if tipo == "video":
        imagens = [(q, "image/jpeg") for q in quadros_chave(dados)]
        if not imagens:
            return None
        res = await analisar_imagens(imagens)
        if res:
            res["dados"]["quadros"] = len(imagens)
        return res
    return await analisar_imagens([(dados, mime)])
