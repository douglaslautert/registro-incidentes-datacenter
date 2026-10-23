"""Router de transcrição de voz para texto."""
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.transcricao import transcrever_audio
from app.services.s3_client import upload_evidencia
import logging

router = APIRouter(prefix="/api/v1/transcricao", tags=["transcrição"])
log = logging.getLogger("router.transcricao")

TIPOS_AUDIO = {"audio/webm","audio/ogg","audio/wav","audio/mpeg","audio/mp4"}

@router.post("/voz")
async def transcrever_voz(
    incidente_id: str,
    audio: UploadFile = File(...),
):
    """
    Recebe áudio, salva no S3 e retorna a transcrição.
    Se Whisper não estiver disponível, retorna texto vazio para preenchimento manual.
    """
    content_type = audio.content_type or "audio/webm"
    if content_type not in TIPOS_AUDIO:
        raise HTTPException(400, f"Tipo de áudio não suportado: {content_type}")

    dados = await audio.read()
    if len(dados) > 10 * 1024 * 1024:  # 10 MB
        raise HTTPException(400, "Áudio maior que 10MB")

    # Upload do áudio bruto para S3 (evidência)
    url_audio = upload_evidencia(dados, content_type, "webm")

    # Transcrição
    resultado = transcrever_audio(dados, content_type)

    log.info(f"Transcrição: incidente={incidente_id} motor={resultado['motor']}")
    return {
        "incidente_id": incidente_id,
        "url_audio": url_audio,
        "texto": resultado["texto"],
        "confianca": resultado["confianca"],
        "motor": resultado["motor"],
        "requer_revisao": resultado["confianca"] < 0.6 or resultado["motor"] == "fallback-manual",
    }
