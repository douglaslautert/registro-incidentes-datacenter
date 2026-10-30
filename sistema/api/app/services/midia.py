"""Tipo de mídia de um upload: MIME do navegador ou, se vier genérico, pela extensão.

Alguns navegadores enviam o arquivo sem tipo ou como application/octet-stream —
comum com vídeos .mov (QuickTime) escolhidos no Windows ou em gerenciadores de arquivo.
"""
import os
from fastapi import UploadFile

GENERICOS = {"", "application/octet-stream", "binary/octet-stream", "application/x-unknown"}

POR_EXTENSAO = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
    ".heic": "image/heic", ".heif": "image/heif",
    ".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime", ".qt": "video/quicktime",
    ".webm": "video/webm",
    ".weba": "audio/webm", ".ogg": "audio/ogg", ".oga": "audio/ogg", ".wav": "audio/wav",
    ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac",
}


def extrair_audio(dados: bytes) -> tuple[bytes, str, str] | None:
    """Separa a trilha de áudio de um vídeo, sem recodificar (cópia dos pacotes).

    Retorna (bytes, MIME, extensão) ou None se o vídeo não tiver som ou o codec não
    couber num contêiner de áudio. Guardado ao lado do vídeo, o áudio toca em qualquer
    navegador — um .mov HEVC do iPhone, por exemplo, não abre no Chrome do PC.
    """
    import io
    import av
    try:
        with av.open(io.BytesIO(dados)) as ent:
            if not ent.streams.audio:
                return None
            trilha = ent.streams.audio[0]
            codec = trilha.codec_context.name
            if codec in ("aac", "alac", "mp3"):
                formato, mime, ext = "mp4", "audio/mp4", "m4a"
            elif codec in ("opus", "vorbis"):
                formato, mime, ext = "webm", "audio/webm", "weba"
            else:
                return None
            saida = io.BytesIO()
            with av.open(saida, "w", format=formato) as sai:
                destino = sai.add_stream(template=trilha)
                for pacote in ent.demux(trilha):
                    if pacote.dts is None:      # pacote de descarga do demuxer
                        continue
                    pacote.stream = destino
                    sai.mux(pacote)
            return saida.getvalue(), mime, ext
    except Exception:
        return None


def tipo_do_upload(arquivo: UploadFile) -> str:
    """MIME normalizado ("audio/webm;codecs=opus" → "audio/webm"); se o navegador não
    informou um tipo útil, deduz pela extensão do nome do arquivo."""
    tipo = (arquivo.content_type or "").split(";")[0].strip().lower()
    if tipo in GENERICOS:
        tipo = POR_EXTENSAO.get(os.path.splitext(arquivo.filename or "")[1].lower(), tipo)
    return tipo
