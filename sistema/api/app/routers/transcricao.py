"""Router de transcrição de voz para texto e interpretação do relato em chamado."""
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from app.services.transcricao import transcrever_audio
from app.services.interpretacao import interpretar
from app.services.s3_client import upload_evidencia
from app.services.midia import tipo_do_upload, extrair_audio
import logging

router = APIRouter(prefix="/api/v1/transcricao", tags=["transcrição"])
log = logging.getLogger("router.transcricao")

# Tipo MIME → extensão salva no S3. Chrome/Android grava WebM/Opus; iPhone, MP4/AAC.
TIPOS_AUDIO = {
    "audio/webm": "weba", "audio/ogg": "ogg",   # .weba: áudio WebM, distinto de vídeo .webm
    "audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav",
    "audio/mpeg": "mp3", "audio/mp4": "m4a", "audio/x-m4a": "m4a", "audio/aac": "aac",
}
# Vídeo: o iPhone grava MOV (video/quicktime); o Android, MP4 ou WebM
TIPOS_VIDEO = {"video/mp4": "mp4", "video/quicktime": "mov", "video/webm": "webm"}


async def _relato(arquivo: UploadFile, tipos: dict, limite_mb: int, nome: str) -> dict:
    """Salva a mídia no S3 como evidência, transcreve a fala e sugere o chamado."""
    content_type = tipo_do_upload(arquivo)   # MIME ou, se vier genérico, pela extensão (.mov)
    if content_type not in tipos:
        raise HTTPException(400, f"Tipo de {nome} não suportado: {content_type or 'desconhecido'}")

    dados = await arquivo.read()
    if not dados:
        raise HTTPException(400, f"{nome.capitalize()} vazio")
    if len(dados) > limite_mb * 1024 * 1024:
        raise HTTPException(400, f"{nome.capitalize()} maior que {limite_mb}MB")

    # Upload e transcrição são bloqueantes (boto3, CPU): fora do event loop
    url = await run_in_threadpool(upload_evidencia, dados, content_type, tipos[content_type])
    resultado = await run_in_threadpool(transcrever_audio, dados, content_type)
    return {
        "url": url,
        "texto": resultado["texto"],
        "confianca": resultado["confianca"],
        "motor": resultado["motor"],
        "duracao_segundos": resultado["duracao_segundos"],
        "requer_revisao": resultado["confianca"] < 0.6 or not resultado["texto"],
        "sugestao": interpretar(resultado["texto"]),
    }


@router.post("/voz")
async def transcrever_voz(
    audio: UploadFile = File(...),
    incidente_id: Optional[str] = None,
):
    """
    Recebe áudio, salva no S3 como evidência, transcreve e sugere os campos do chamado.
    Sem `incidente_id`, serve para abrir um chamado novo a partir do relato falado.
    """
    r = await _relato(audio, TIPOS_AUDIO, 10, "áudio")
    log.info(f"Transcrição de áudio: incidente={incidente_id} motor={r['motor']}")
    return {"incidente_id": incidente_id, "url_audio": r.pop("url"), **r}


@router.post("/video")
async def transcrever_video(video: UploadFile = File(...)):
    """
    Recebe o vídeo do problema, salva no S3 o vídeo e, à parte, o áudio extraído dele,
    transcreve a fala e sugere os campos do chamado. Vídeo sem som volta com texto
    vazio (motor "sem-audio") para o técnico digitar o relato.
    """
    r = await _relato(video, TIPOS_VIDEO, 90, "vídeo")

    # Guarda também o áudio do vídeo como evidência própria: toca em qualquer
    # navegador, mesmo quando o vídeo (ex.: .mov HEVC do iPhone) não abre
    url_audio = None
    await video.seek(0)
    audio = await run_in_threadpool(extrair_audio, await video.read())
    if audio:
        dados, mime, ext = audio
        url_audio = await run_in_threadpool(upload_evidencia, dados, mime, ext)

    log.info(f"Transcrição de vídeo: motor={r['motor']} duração={r['duracao_segundos']}s áudio={'sim' if url_audio else 'não'}")
    return {"url_video": r.pop("url"), "url_audio": url_audio, **r}


class Relato(BaseModel):
    texto: str


@router.post("/interpretar")
async def interpretar_relato(relato: Relato):
    """Reinterpreta o relato depois que o técnico corrige o texto transcrito."""
    return interpretar(relato.texto)
