"""Serviço de transcrição de voz — faster-whisper local (on-premises) ou fallback manual."""
import io, logging, math, threading
from app.core.config import settings

log = logging.getLogger("transcricao")

_modelo = None
_trava = threading.Lock()


def _carregar_modelo():
    """Carrega o modelo uma única vez por processo (a 1ª chamada leva alguns segundos)."""
    global _modelo
    with _trava:
        if _modelo is None:
            from faster_whisper import WhisperModel
            _modelo = WhisperModel(settings.WHISPER_MODEL, device="cpu", compute_type="int8")
            log.info(f"Modelo faster-whisper '{settings.WHISPER_MODEL}' carregado")
    return _modelo


def _dica_vocabulario() -> str:
    """Nomes dos ativos e locais do CESUP: orientam o Whisper nos termos do datacenter
    (sem isso, "Node 01" vira "Nord-01")."""
    from app.routers.ativos import _qr_map
    ativos = ", ".join(a["nome"] for a in _qr_map.values())
    salas = ", ".join(sorted({a["sala"].replace("-", " ") for a in _qr_map.values()}))
    return f"Relato de incidente no datacenter do CESUP. Ativos: {ativos}. Locais: {salas}."


def _tem_audio(dados: bytes) -> bool:
    """O arquivo tem trilha de áudio? Vídeo gravado sem som faria o faster-whisper
    falhar com IndexError, em vez de uma mensagem clara."""
    try:
        import av
        with av.open(io.BytesIO(dados)) as c:
            return len(c.streams.audio) > 0
    except Exception:
        return True   # na dúvida, deixa o faster-whisper tentar


def transcrever_audio(dados: bytes, content_type: str) -> dict:
    """
    Transcreve a fala de um áudio (WebM/Opus, MP4/AAC, WAV, OGG, MP3) ou da trilha de
    áudio de um vídeo (MP4, MOV, WebM) para texto em português.
    Se o faster-whisper não estiver instalado, devolve texto vazio para preenchimento manual.
    """
    resultado = {
        "texto": "",
        "confianca": 0.0,
        "motor": "indisponivel",
        "duracao_segundos": None,
    }
    try:
        if not _tem_audio(dados):
            resultado["motor"] = "sem-audio"
            log.info("Arquivo sem trilha de áudio — relato manual")
            return resultado
        modelo = _carregar_modelo()
        segmentos, info = modelo.transcribe(
            io.BytesIO(dados), language="pt", beam_size=5,
            vad_filter=True, initial_prompt=_dica_vocabulario(),
        )
        segmentos = list(segmentos)
        texto = " ".join(s.text.strip() for s in segmentos).strip()
        # Confiança: média de exp(avg_logprob) dos segmentos (0 a 1)
        confianca = sum(math.exp(s.avg_logprob) for s in segmentos) / len(segmentos) if segmentos else 0.0
        resultado.update({
            "texto": texto,
            "confianca": round(confianca, 2),
            "motor": f"faster-whisper-{settings.WHISPER_MODEL}",
            "duracao_segundos": round(info.duration, 1),
        })
        log.info(f"Transcrição ({resultado['duracao_segundos']}s, conf {resultado['confianca']}): '{texto[:60]}'")
    except ImportError:
        # faster-whisper não instalado — o técnico digita o relato
        resultado["motor"] = "fallback-manual"
        log.warning("faster-whisper não instalado — transcrição manual necessária")
    except Exception as e:
        log.error(f"Erro na transcrição: {e}")
        resultado["motor"] = f"erro: {e}"
    return resultado
