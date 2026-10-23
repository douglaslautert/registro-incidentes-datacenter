from fastapi import APIRouter, Header, HTTPException
from typing import Optional
import os

router = APIRouter(tags=["health"])

@router.get("/health")
async def health():
    return {"status": "ok", "service": "cesup-incidentes-api"}

@router.get("/api/v1/heartbeat")
async def heartbeat(
    authorization: Optional[str] = Header(None)  # Authorization: Bearer <VIGIA_TOKEN>
):
    """
    Endpoint para o vigia externo bater coração.
    Requer: Authorization: Bearer <VIGIA_TOKEN>
    """
    vigia_token = os.environ.get("VIGIA_TOKEN", "")
    if vigia_token:
        expected = f"Bearer {vigia_token}"
        if authorization != expected:
            raise HTTPException(status_code=401, detail="Token inválido")
    return {"alive": True, "service": "cesup-incidentes-api"}
