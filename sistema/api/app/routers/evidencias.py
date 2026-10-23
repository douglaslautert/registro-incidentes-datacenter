"""Router de evidências — upload de fotos e arquivos para Garage S3."""
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.s3_client import upload_evidencia, url_presigned
import logging, mimetypes

router = APIRouter(prefix="/api/v1/evidencias", tags=["evidências"])
log = logging.getLogger("router.evidencias")

TIPOS_PERMITIDOS = {"image/jpeg","image/png","image/webp","audio/webm","audio/ogg","audio/wav"}
TAMANHO_MAX_MB = 20

@router.post("/upload")
async def upload(
    incidente_id: str,
    arquivo: UploadFile = File(...),
):
    """Faz upload de foto ou áudio e retorna a URL pública no S3."""
    content_type = arquivo.content_type or "application/octet-stream"
    if content_type not in TIPOS_PERMITIDOS:
        raise HTTPException(400, f"Tipo não permitido: {content_type}")

    dados = await arquivo.read()
    if len(dados) == 0:
        raise HTTPException(400, "Arquivo vazio não é permitido")
    if len(dados) > TAMANHO_MAX_MB * 1024 * 1024:
        raise HTTPException(400, f"Arquivo maior que {TAMANHO_MAX_MB}MB")

    ext = mimetypes.guess_extension(content_type) or ".bin"
    url = upload_evidencia(dados, content_type, ext.lstrip("."))
    if not url:
        raise HTTPException(500, "Falha no upload para o S3")

    log.info(f"Evidência salva: {url} para incidente {incidente_id}")
    return {
        "incidente_id": incidente_id,
        "url": url,
        "content_type": content_type,
        "tamanho_bytes": len(dados),
    }

@router.get("/url/{key:path}")
async def url_temporaria(key: str, expira_segundos: int = 3600):
    """Gera URL assinada temporária para acesso a uma evidência."""
    url = url_presigned(key, expira_segundos)
    if not url:
        raise HTTPException(500, "Falha ao gerar URL")
    return {"url": url, "expira_segundos": expira_segundos}
