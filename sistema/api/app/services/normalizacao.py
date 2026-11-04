"""Normalização para o evento canônico (Sprint 6) — a mesma forma para todas as fontes.

Pessoa (PWA), Zabbix (webhook e reconciliação) e e-mail chegam diferentes; daqui saem com
o ativo resolvido pelo inventário, o local completado pelo cadastro do ativo, o sintoma
limpo, o risco a pessoas detectado no texto e o fingerprint de deduplicação.
"""
from app.schemas.evento import EventoCreate, LocalDC
from app.services import inventario, fingerprint
from app.services.interpretacao import RISCO_PESSOAS, interpretar, normalizar as _norm

# Severidade do Zabbix → confiança do evento
CONFIANCA_ZABBIX = {"not classified": 0.4, "information": 0.5, "warning": 0.6,
                    "average": 0.7, "high": 0.85, "disaster": 1.0}
CONFIANCA_ZABBIX_NUM = {0: 0.4, 1: 0.5, 2: 0.6, 3: 0.7, 4: 0.85, 5: 1.0}
LOCAIS_GENERICOS = {"", "datacenter", "desconhecido", "nao-informada"}


def normalizar(ev: EventoCreate) -> tuple[EventoCreate, str]:
    """(evento canônico, fingerprint)."""
    ativo = inventario.resolver(ev.ativo_id)
    ativo_id = ativo["ativo_id"] if ativo else ev.ativo_id.strip()

    local = ev.local.model_copy()
    if ativo:
        if (local.sala or "").strip().lower() in LOCAIS_GENERICOS:
            local = LocalDC(sala=ativo["sala"], rack=ativo.get("rack"),
                            fileira=local.fileira, unidade=local.unidade)
        elif not local.rack and local.sala == ativo["sala"]:
            local.rack = ativo.get("rack")

    sintoma = " ".join(ev.sintoma.split())
    seguranca = ev.seguranca_pessoas or any(k in _norm(sintoma) for k in RISCO_PESSOAS)
    canon = ev.model_copy(update={"ativo_id": ativo_id, "local": local, "sintoma": sintoma,
                                  "seguranca_pessoas": seguranca})
    return canon, fingerprint.calcular(ativo_id, sintoma)


def de_zabbix(body: dict) -> tuple[EventoCreate, str, str]:
    """Webhook do Zabbix → (evento, eventid, PROBLEM|RECOVERY)."""
    status = str(body.get("status", "PROBLEM")).upper()
    status = "RECOVERY" if status in ("RECOVERY", "RESOLVED", "OK") else "PROBLEM"
    ev = EventoCreate(
        fonte="zabbix",
        ativo_id=str(body.get("host") or "desconhecido"),
        local=LocalDC(sala="datacenter"),
        sintoma=str(body.get("trigger") or "alerta_zabbix"),
        confianca=CONFIANCA_ZABBIX.get(str(body.get("severity", "average")).lower(), 0.7),
    )
    return ev, str(body.get("eventid") or ""), status


def de_problema_zabbix(p: dict) -> tuple[EventoCreate, str]:
    """Problema lido pela API JSON-RPC do Zabbix (reconciliação) → (evento, eventid)."""
    hosts = p.get("hosts") or [{}]
    ev = EventoCreate(
        fonte="zabbix",
        ativo_id=str(hosts[0].get("host") or "desconhecido"),
        local=LocalDC(sala="datacenter"),
        sintoma=str(p.get("name") or "alerta_zabbix"),
        confianca=CONFIANCA_ZABBIX_NUM.get(int(p.get("severity", 3)), 0.7),
    )
    return ev, str(p.get("eventid") or "")


def de_email(remetente: str, assunto: str, corpo: str) -> EventoCreate:
    """E-mail de relato → evento. A interpretação acha ativo, sala e risco no texto."""
    texto = f"{assunto}. {corpo}".strip(" .")
    s = interpretar(texto)
    return EventoCreate(
        fonte="email",
        ativo_id=s["ativo_id"] or "nao-identificado",
        local=LocalDC(sala=s["sala"] or "nao-informada", rack=s["rack"]),
        sintoma=(assunto or corpo or "relato por e-mail").strip()[:300],
        confianca=0.6,                      # texto livre sem revisão humana
        seguranca_pessoas=s["seguranca_pessoas"],
    )
