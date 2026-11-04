"""Configuração de login para o PWA e estado dos serviços de IA (degradação graciosa)."""
from fastapi import APIRouter, Depends
from app.core.config import settings
from app.services import visao
from app.services.embedding import MODELO_LOCAL
from app.services.seguranca import Usuario, usuario_atual

router = APIRouter(prefix="/api/v1", tags=["sistema"])


@router.get("/auth/config")
async def auth_config():
    """O PWA consulta antes de abrir: se o login é obrigatório e onde fica o Keycloak."""
    return {"obrigatoria": settings.AUTH_OBRIGATORIA, "realm": settings.KEYCLOAK_REALM,
            "client_id": "incidentes-pwa", "caminho": "/auth"}


@router.get("/auth/eu")
async def eu(u: Usuario = Depends(usuario_atual)):
    return {"id": u.id, "nome": u.nome, "papeis": sorted(u.papeis)}


@router.get("/ia/status")
async def ia_status():
    """O que está ativo: sem GPU, o sistema funciona com transcrição em CPU e sem visão."""
    from app.services.transcricao import dispositivo_whisper
    return {
        "transcricao": {"modelo": settings.WHISPER_MODEL, "dispositivo": dispositivo_whisper()},
        "visao": {"ativa": visao.configurado(), "modelo": settings.VISION_MODEL if visao.configurado() else None},
        "embeddings": {"modelo": settings.EMBEDDINGS_MODEL if settings.EMBEDDINGS_URL else MODELO_LOCAL,
                       "remoto": bool(settings.EMBEDDINGS_URL)},
    }
