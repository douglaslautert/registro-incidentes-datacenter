"""Router de transcrição de voz para texto e interpretação do relato em chamado."""
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from app.services.transcricao import transcrever_audio
from app.services.interpretacao import interpretar
from app.services.s3_client import upload_evidencia
import logging

router = APIRouter(prefix="/api/v1/transcricao", tags=["transcrição"])
log = logging.getLogger("router.transcricao")

# Tipo MIME → extensão salva no S3. Chrome/Android grava WebM/Opus; iPhone, MP4/AAC.
TIPOS_AUDIO = {
    "audio/webm": "webm", "audio/ogg": "ogg",
    "audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav",
    "audio/mpeg": "mp3", "audio/mp4": "m4a", "audio/x-m4a": "m4a", "audio/aac": "aac",
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
    # "audio/webm;codecs=opus" → "audio/webm"
    content_type = (audio.content_type or "audio/webm").split(";")[0].strip().lower()
    if content_type not in TIPOS_AUDIO:
        raise HTTPException(400, f"Tipo de áudio não suportado: {content_type}")

    dados = await audio.read()
    if not dados:
        raise HTTPException(400, "Áudio vazio")
    if len(dados) > 10 * 1024 * 1024:  # 10 MB
        raise HTTPException(400, "Áudio maior que 10MB")

    # Upload e transcrição são bloqueantes (boto3, CPU): fora do event loop
    url_audio = await run_in_threadpool(upload_evidencia, dados, content_type, TIPOS_AUDIO[content_type])
    resultado = await run_in_threadpool(transcrever_audio, dados, content_type)

    log.info(f"Transcrição: incidente={incidente_id} motor={resultado['motor']}")
    return {
        "incidente_id": incidente_id,
        "url_audio": url_audio,
        "texto": resultado["texto"],
        "confianca": resultado["confianca"],
        "motor": resultado["motor"],
        "duracao_segundos": resultado["duracao_segundos"],
        "requer_revisao": resultado["confianca"] < 0.6 or not resultado["texto"],
        "sugestao": interpretar(resultado["texto"]),
    }


class Relato(BaseModel):
    texto: str


@router.post("/interpretar")
async def interpretar_relato(relato: Relato):
    """Reinterpreta o relato depois que o técnico corrige o texto transcrito."""
    return interpretar(relato.texto)
