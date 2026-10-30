"""Router de evidências — fotos, vídeos e áudios no Garage S3, vinculados ao incidente."""
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.incidente import Evento
from app.services.s3_client import upload_evidencia, url_presigned, baixar_evidencia, IntervaloInvalido
from app.services.midia import tipo_do_upload
import logging

router = APIRouter(prefix="/api/v1/evidencias", tags=["evidências"])
log = logging.getLogger("router.evidencias")

# Tipo MIME → (extensão, limite em MB). O iPhone grava vídeo em MOV (video/quicktime)
# e pode enviar fotos em HEIC; o Android grava MP4 ou WebM.
TIPOS = {
    "image/jpeg": ("jpg", 20), "image/png": ("png", 20), "image/webp": ("webp", 20),
    "image/heic": ("heic", 20), "image/heif": ("heif", 20),
    "video/mp4": ("mp4", 90), "video/quicktime": ("mov", 90), "video/webm": ("webm", 90),
    # .weba (e não .webm) para o PWA saber que é áudio, não vídeo
    "audio/webm": ("weba", 20), "audio/ogg": ("ogg", 20), "audio/wav": ("wav", 20),
    "audio/mp4": ("m4a", 20),
}


async def _ultimo_evento(db: AsyncSession, incidente_id: str) -> Evento | None:
    """Evento mais recente do incidente — é nele que a evidência fica registrada."""
    try:
        r = await db.execute(
            select(Evento).where(Evento.incidente_id == incidente_id)
            .order_by(Evento.recebido_em.desc()).limit(1)
        )
        return r.scalars().first()
    except SQLAlchemyError as e:
        log.warning(f"Busca do evento falhou, usando memória: {e}")
        await db.rollback()
        return None


@router.post("/upload")
async def upload(
    incidente_id: str,
    arquivo: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Envia foto, vídeo ou áudio ao S3 e anexa ao incidente."""
    content_type = tipo_do_upload(arquivo)   # MIME ou, se vier genérico, pela extensão (.mov)
    if content_type not in TIPOS:
        raise HTTPException(400, f"Tipo não permitido: {content_type or 'desconhecido'}")
    extensao, limite_mb = TIPOS[content_type]

    # Confere o incidente antes do upload, para não deixar arquivo órfão no S3
    evento = await _ultimo_evento(db, incidente_id)
    if evento is None:
        from app.routers.incidentes import _incidentes
        if incidente_id not in _incidentes:
            raise HTTPException(404, "Incidente não encontrado")

    dados = await arquivo.read()
    if len(dados) == 0:
        raise HTTPException(400, "Arquivo vazio não é permitido")
    if len(dados) > limite_mb * 1024 * 1024:
        raise HTTPException(400, f"Arquivo maior que {limite_mb}MB")

    url = await run_in_threadpool(upload_evidencia, dados, content_type, extensao)
    if not url:
        raise HTTPException(500, "Falha no upload para o S3")

    if evento is not None:
        # Reatribui a lista: o SQLAlchemy não percebe mutação dentro de ARRAY
        evento.evidencias = list(evento.evidencias or []) + [url]
        await db.flush()
    else:
        from app.routers.incidentes import _eventos
        _eventos.append({"incidente_id": incidente_id, "evidencias": [url]})

    log.info(f"Evidência {url} anexada ao incidente {incidente_id}")
    return {
        "incidente_id": incidente_id,
        "url": url,
        "content_type": content_type,
        "tamanho_bytes": len(dados),
    }


@router.get("/arquivo/{key:path}")
async def arquivo(key: str, request: Request):
    """Entrega a evidência a partir do S3. Atende pedidos parciais (Range), que o
    Safari exige para tocar vídeo e que permitem avançar no vídeo sem baixar tudo."""
    if not key.startswith("evidencias/") or ".." in key:
        raise HTTPException(404, "Evidência não encontrada")
    try:
        obj = await run_in_threadpool(baixar_evidencia, key, request.headers.get("range"))
    except IntervaloInvalido:
        raise HTTPException(416, "Intervalo inválido")
    if obj is None:
        raise HTTPException(404, "Evidência não encontrada")

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(obj["ContentLength"]),
        "Cache-Control": "private, max-age=86400",
    }
    status = 200
    if obj.get("ContentRange"):
        headers["Content-Range"] = obj["ContentRange"]
        status = 206
    return StreamingResponse(
        obj["Body"].iter_chunks(64 * 1024), status_code=status,
        media_type=obj.get("ContentType") or "application/octet-stream", headers=headers,
    )


@router.get("/url/{key:path}")
async def url_temporaria(key: str, expira_segundos: int = 3600):
    """Gera URL assinada temporária para acesso a uma evidência."""
    url = url_presigned(key, expira_segundos)
    if not url:
        raise HTTPException(500, "Falha ao gerar URL")
    return {"url": url, "expira_segundos": expira_segundos}
