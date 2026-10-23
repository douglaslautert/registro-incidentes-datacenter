"""Serviço de escalonamento de plantão com ACK e reescalonamento."""
from datetime import datetime, timedelta, timezone
from app.core.config import settings
from app.services.notificacao import notificar_plantao
import logging

log = logging.getLogger("escalonamento")

# Janelas de ACK por prioridade (minutos)
ACK_TIMEOUT = {"P1": 10, "P2": 30, "P3": 120, "P4": None}

# Fila em memória (substituir por banco/Valkey no Sprint 4)
_fila: dict[str, dict] = {}

def registrar_acionamento(incidente_id: str, prioridade: str, titulo: str, ativo: str):
    """Registra um acionamento pendente de ACK."""
    timeout = ACK_TIMEOUT.get(prioridade)
    _fila[incidente_id] = {
        "incidente_id": incidente_id,
        "prioridade":   prioridade,
        "titulo":       titulo,
        "ativo":        ativo,
        "acionado_em":  datetime.now(timezone.utc),
        "ack_em":       None,
        "ack_por":      None,
        "escalado":     False,
        "timeout_min":  timeout,
    }
    log.info(f"Acionamento registrado: {incidente_id} [{prioridade}] timeout={timeout}min")

def confirmar_ack(incidente_id: str, usuario_id: str) -> bool:
    """Registra ACK do plantonista. Idempotente — primeiro ACK tem precedência."""
    if incidente_id not in _fila:
        return False
    if _fila[incidente_id].get("ack_em") is None:
        _fila[incidente_id]["ack_em"]  = datetime.now(timezone.utc)
        _fila[incidente_id]["ack_por"] = usuario_id
        log.info(f"ACK confirmado: {incidente_id} por {usuario_id}")
    else:
        log.info(f"ACK duplicado ignorado: {incidente_id} (ja confirmado por {_fila[incidente_id]['ack_por']})")
    return True

async def verificar_timeouts() -> None:
    """Verifica acionamentos sem ACK e reescalona se necessário (chamada pelo Celery Beat)."""
    agora = datetime.now(timezone.utc)
    for iid, ac in list(_fila.items()):
        if ac["ack_em"] or not ac["timeout_min"]:
            continue
        delta = (agora - ac["acionado_em"]).total_seconds() / 60
        if delta >= ac["timeout_min"] and not ac["escalado"]:
            log.warning(f"Timeout de ACK: {iid} [{ac['prioridade']}] — reescalonando")
            ac["escalado"] = True
            await notificar_plantao(iid, ac["prioridade"],
                f"[REESCALONADO] {ac['titulo']}", ac["ativo"])
