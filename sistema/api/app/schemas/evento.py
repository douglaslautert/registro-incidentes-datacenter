from pydantic import BaseModel, Field
from typing import Literal, List, Optional
from datetime import datetime

class LocalDC(BaseModel):
    sala:    str
    fileira: Optional[str] = None
    rack:    Optional[str] = None
    unidade: Optional[int] = None

class EventoCreate(BaseModel):
    fonte:             Literal["pessoa", "zabbix", "email"]
    ativo_id:          str
    local:             LocalDC
    sintoma:           str
    confianca:         float = Field(ge=0.0, le=1.0, default=1.0)
    seguranca_pessoas: bool  = False
    evidencias:        Optional[List[str]] = []

class EventoResponse(BaseModel):
    id:                   str
    fonte:                str
    ativo_id:             str
    sintoma:              str
    confianca:            float
    seguranca_pessoas:    bool
    incidente_id:         Optional[str]    = None
    prioridade:           Optional[str]    = None
    recebido_em:          Optional[datetime] = None
    decisao_correlacao:   Optional[str]    = None

    class Config:
        from_attributes = True

class IncidenteResponse(BaseModel):
    id:           str
    titulo:       str
    prioridade:   str
    status:       str
    ativo_id:     Optional[str]
    aberto_em:    datetime
    total_eventos: int = 0

    class Config:
        from_attributes = True
