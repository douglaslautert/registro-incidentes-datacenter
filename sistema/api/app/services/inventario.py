"""Inventário de ativos (QR Code → ativo), persistido na tabela qr_codes.

Fica também em memória (CACHE), porque a interpretação do relato e a dica de vocabulário
da transcrição o consultam de forma síncrona. A API recarrega do banco ao iniciar e a cada
cadastro; se o banco estiver fora, valem os ativos iniciais abaixo.
"""
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger("inventario")

# Ativos iniciais do CESUP (os mesmos do init/02_qrcodes.sql e 03_sprints_1_6.sql)
CACHE: dict[str, dict] = {
    "CESUP-SRV-001": {"ativo_id": "srv-node-001", "nome": "Servidor Node 01", "sala": "sala-A", "rack": "rack-01", "tipo": "servidor"},
    "CESUP-SRV-002": {"ativo_id": "srv-node-002", "nome": "Servidor Node 02", "sala": "sala-A", "rack": "rack-01", "tipo": "servidor"},
    "CESUP-UPS-001": {"ativo_id": "ups-sala-a-1", "nome": "UPS Sala A — 1", "sala": "sala-A", "rack": "rack-01", "tipo": "ups"},
    "CESUP-PDU-001": {"ativo_id": "pdu-a-01", "nome": "PDU Rack 01", "sala": "sala-A", "rack": "rack-01", "tipo": "pdu"},
    "CESUP-SW-001":  {"ativo_id": "switch-core-01", "nome": "Switch Core 01", "sala": "sala-DC", "rack": "rack-10", "tipo": "switch"},
    "CESUP-STG-001": {"ativo_id": "storage-01", "nome": "Storage 01", "sala": "sala-B", "rack": "rack-05", "tipo": "storage"},
}


async def recarregar(db: AsyncSession) -> int:
    r = await db.execute(text(
        "SELECT qr_code, ativo_id, nome, sala, rack, tipo FROM qr_codes WHERE ativo_em ORDER BY qr_code"))
    linhas = r.mappings().all()
    if linhas:
        CACHE.clear()        # mesmo objeto: quem importou CACHE vê a atualização
        for l in linhas:
            CACHE[l["qr_code"].upper()] = {k: l[k] for k in ("ativo_id", "nome", "sala", "rack", "tipo")}
    return len(linhas)


def resolver(referencia: str) -> dict | None:
    """Ativo pelo ID, pelo código QR ou pelo nome (hostname do Zabbix), sem diferenciar caixa."""
    ref = (referencia or "").strip().lower()
    if not ref:
        return None
    for qr, a in CACHE.items():
        if ref in (a["ativo_id"].lower(), qr.lower(), (a.get("nome") or "").lower()):
            return {**a, "qr_code": qr}
    return None


async def cadastrar(db: AsyncSession, qr_code: str, dados: dict) -> None:
    await db.execute(text(
        "INSERT INTO qr_codes (qr_code, ativo_id, nome, sala, rack, tipo) "
        "VALUES (:qr, :ativo_id, :nome, :sala, :rack, :tipo)"),
        {"qr": qr_code.upper(), **{k: dados.get(k) for k in ("ativo_id", "nome", "sala", "rack", "tipo")}})
    CACHE[qr_code.upper()] = {k: dados.get(k) for k in ("ativo_id", "nome", "sala", "rack", "tipo")}
