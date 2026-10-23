"""Models SQLAlchemy — Incidente e Evento com pgvector."""
from sqlalchemy import (Column, String, Float, Boolean, DateTime,
                        Integer, ForeignKey, Text)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from app.database import Base

try:
    from pgvector.sqlalchemy import Vector
    _vector_ok = True
except ImportError:
    from sqlalchemy import ARRAY, Float as _Float
    def Vector(dim): return ARRAY(_Float)
    _vector_ok = False


class Incidente(Base):
    __tablename__ = "incidentes"
    __table_args__ = {"postgresql_partition_by": "RANGE (aberto_em)"}

    id          = Column(String,  primary_key=True)
    titulo      = Column(String,  nullable=False)
    prioridade  = Column(String,  nullable=False, default="P4")
    status      = Column(String,  nullable=False, default="aberto")
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
    fonte        = Column(String,  nullable=False)
    ativo_id     = Column(String)
    sintoma      = Column(String)
    confianca    = Column(Float,   default=1.0)
    seguranca    = Column(Boolean, default=False)
    local        = Column(JSONB)
    evidencias   = Column(JSONB,   default=list)
    recebido_em  = Column(DateTime(timezone=True), default=datetime.utcnow)
    embedding    = Column(Vector(1024))  # pgvector — correlação semântica

    incidente    = relationship("Incidente", back_populates="eventos",
                                foreign_keys=[incidente_id])
