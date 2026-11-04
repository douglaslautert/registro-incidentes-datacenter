"""Router de ativos — busca por ID, hostname ou código QR. Persistido em qr_codes."""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.services import inventario
from app.services.seguranca import Usuario, exigir, LER, GERIR
import logging

router = APIRouter(prefix="/api/v1/ativos", tags=["ativos"])
log = logging.getLogger("router.ativos")

# Compatibilidade: a interpretação e a transcrição leem este mapa (o mesmo objeto do cache)
_qr_map = inventario.CACHE


@router.get("/qr/{codigo}")
async def buscar_por_qr(codigo: str, u: Usuario = Depends(exigir(LER))):
    """Retorna os dados do ativo associado ao código QR."""
    ativo = _qr_map.get(codigo.upper())
    if not ativo:
        raise HTTPException(404, f"QR Code '{codigo}' não mapeado")
    log.info(f"QR lido: {codigo} → {ativo['ativo_id']}")
    return {**ativo, "qr_code": codigo.upper()}


@router.get("/{ativo_id}")
async def buscar_por_id(ativo_id: str, u: Usuario = Depends(exigir(LER))):
    """Busca ativo pelo ID, código QR ou nome."""
    ativo = inventario.resolver(ativo_id)
    if not ativo:
        raise HTTPException(404, f"Ativo '{ativo_id}' não encontrado")
    return ativo


@router.get("/")
async def listar_ativos(u: Usuario = Depends(exigir(LER))):
    """Lista todos os ativos mapeados com QR Code."""
    return [{**a, "qr_code": qr} for qr, a in _qr_map.items()]


class AtivoCreate(BaseModel):
    qr_code: str
    ativo_id: str
    nome: str
    sala: str
    rack: Optional[str] = None
    tipo: str = "servidor"


@router.post("/", status_code=201)
async def cadastrar_ativo(payload: AtivoCreate, db: AsyncSession = Depends(get_db),
                          u: Usuario = Depends(exigir(GERIR))):
    """Cadastra novo mapeamento QR → ativo."""
    if payload.qr_code.upper() in _qr_map:
        raise HTTPException(409, f"QR Code '{payload.qr_code}' já cadastrado")
    try:
        await inventario.cadastrar(db, payload.qr_code, payload.model_dump(exclude={"qr_code"}))
        await db.flush()
    except IntegrityError:
        raise HTTPException(409, f"QR Code '{payload.qr_code}' já cadastrado")
    log.info(f"Ativo cadastrado: {payload.qr_code} → {payload.ativo_id}")
    return {"msg": "Ativo cadastrado", "qr_code": payload.qr_code.upper()}
