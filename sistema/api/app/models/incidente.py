"""Models SQLAlchemy — Incidente e Evento com pgvector."""
from sqlalchemy import (Column, String, Float, Boolean, DateTime,
                        Integer, ForeignKey, Text)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB, ARRAY, ENUM
from datetime import datetime
from app.database import Base

try:
    from pgvector.sqlalchemy import Vector
    _vector_ok = True
except ImportError:
    from sqlalchemy import ARRAY, Float as _Float
    def Vector(dim): return ARRAY(_Float)
    _vector_ok = False


# Tipos ENUM criados pelo init/01_schema.sql — create_type=False: não recriar
FONTE_EVENTO     = ENUM("pessoa", "zabbix", "email", name="fonte_evento", create_type=False)
PRIORIDADE       = ENUM("P1", "P2", "P3", "P4", name="prioridade_enum", create_type=False)
STATUS_INCIDENTE = ENUM("aberto", "em_atendimento", "resolvido", "falso_positivo",
                        name="status_incidente", create_type=False)
CANAL_NOTIF      = ENUM("email", "sms", "ligacao", "webpush", name="canal_notif", create_type=False)


class Incidente(Base):
    __tablename__ = "incidentes"
    __table_args__ = {"postgresql_partition_by": "RANGE (aberto_em)"}

    id          = Column(String,  primary_key=True)
    titulo      = Column(String,  nullable=False)
    prioridade  = Column(PRIORIDADE,       nullable=False, default="P4")
    status      = Column(STATUS_INCIDENTE, nullable=False, default="aberto")
    ativo_id    = Column(String)
    causa_raiz  = Column(String)
    aberto_em   = Column(DateTime(timezone=True), primary_key=True,
                         default=datetime.utcnow)
    fechado_em  = Column(DateTime(timezone=True))
    criado_por  = Column(String)
    local       = Column(JSONB)

    eventos = relationship("Evento", back_populates="incidente",
                           primaryjoin="Incidente.id == foreign(Evento.incidente_id)",
                           lazy="select")


class Evento(Base):
    __tablename__ = "eventos"

    id           = Column(String,  primary_key=True)
    incidente_id = Column(String,  ForeignKey("incidentes.id", ondelete="CASCADE"))
    fonte        = Column(FONTE_EVENTO, nullable=False)
    ativo_id     = Column(String,  nullable=False)
    sintoma      = Column(String,  nullable=False)
    confianca    = Column(Float,   nullable=False, default=1.0)
    seguranca    = Column("seguranca_pessoas", Boolean, nullable=False, default=False)
    local        = Column(JSONB)
    evidencias   = Column(ARRAY(Text), default=list)
    recebido_em  = Column(DateTime(timezone=True), default=datetime.utcnow)
    embedding    = Column(Vector(1024))  # pgvector — correlação semântica
    zabbix_eventid = Column(String)
    raw_payload    = Column(JSONB)

    incidente    = relationship("Incidente", back_populates="eventos",
                                foreign_keys=[incidente_id])
