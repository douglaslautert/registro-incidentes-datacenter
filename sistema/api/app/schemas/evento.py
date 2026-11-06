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
    ativo_id:          str = Field(min_length=1, max_length=200)
    local:             LocalDC
    sintoma:           str = Field(min_length=1, max_length=2000)
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
    # novo | anexado | deduplicado | sugerido | duplicado
    decisao_correlacao:   Optional[str]    = None
    sugestao_correlacao:  Optional[str]    = None

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
    sugestao_correlacao: Optional[str] = None
    # Preenchidos nos encerrados (aba Concluídos)
    fechado_em:   Optional[datetime] = None
    fechado_por:  Optional[str] = None
    causa_raiz:   Optional[str] = None
    mesclado_em:  Optional[str] = None

    class Config:
        from_attributes = True
