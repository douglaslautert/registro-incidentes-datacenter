"""Router de ativos — busca por ID, hostname ou código QR."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging

router = APIRouter(prefix="/api/v1/ativos", tags=["ativos"])
log = logging.getLogger("router.ativos")

# Mapa de QR → ativo (em memória no MVP; banco no Sprint 6)
_qr_map: dict[str, dict] = {
    "CESUP-SRV-001": {"ativo_id":"srv-node-001","nome":"Servidor Node 01","sala":"sala-A","rack":"rack-01","tipo":"servidor"},
    "CESUP-SRV-002": {"ativo_id":"srv-node-002","nome":"Servidor Node 02","sala":"sala-A","rack":"rack-01","tipo":"servidor"},
    "CESUP-UPS-001": {"ativo_id":"ups-sala-a-1","nome":"UPS Sala A — 1","sala":"sala-A","rack":"rack-01","tipo":"ups"},
    "CESUP-SW-001":  {"ativo_id":"switch-core-01","nome":"Switch Core 01","sala":"sala-DC","rack":"rack-10","tipo":"switch"},
    "CESUP-STG-001": {"ativo_id":"storage-01","nome":"Storage 01","sala":"sala-B","rack":"rack-05","tipo":"storage"},
}

@router.get("/qr/{codigo}")
async def buscar_por_qr(codigo: str):
    """Retorna os dados do ativo associado ao código QR."""
    ativo = _qr_map.get(codigo.upper())
    if not ativo:
        raise HTTPException(404, f"QR Code '{codigo}' não mapeado")
    log.info(f"QR lido: {codigo} → {ativo['ativo_id']}")
    return ativo

@router.get("/{ativo_id}")
async def buscar_por_id(ativo_id: str):
    """Busca ativo pelo ID direto."""
    for qr, ativo in _qr_map.items():
        if ativo["ativo_id"] == ativo_id:
            return {**ativo, "qr_code": qr}
    raise HTTPException(404, f"Ativo '{ativo_id}' não encontrado")

@router.get("/")
async def listar_ativos():
    """Lista todos os ativos mapeados com QR Code."""
    return list(_qr_map.values())

class AtivoCreate(BaseModel):
    qr_code: str
    ativo_id: str
    nome: str
    sala: str
    rack: Optional[str] = None
    tipo: str = "servidor"

@router.post("/", status_code=201)
async def cadastrar_ativo(payload: AtivoCreate):
    """Cadastra novo mapeamento QR → ativo."""
    if payload.qr_code.upper() in _qr_map:
        raise HTTPException(409, f"QR Code '{payload.qr_code}' já cadastrado")
    _qr_map[payload.qr_code.upper()] = payload.model_dump(exclude={"qr_code"})
    log.info(f"Ativo cadastrado: {payload.qr_code} → {payload.ativo_id}")
    return {"msg": "Ativo cadastrado", "qr_code": payload.qr_code}
