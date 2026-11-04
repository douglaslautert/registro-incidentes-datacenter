from sqlalchemy import Column, String, Boolean, DateTime, Integer
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from app.models.incidente import Base, CANAL_NOTIF

class Acionamento(Base):
    """Acionamento do plantão pendente de ACK (Sprint 4). Fica no banco porque quem
    reescalona é o worker do Celery, outro processo que não a API."""
    __tablename__ = "acionamentos"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    incidente_id = Column(String, nullable=False)
    usuario_id   = Column(String, nullable=False)
    canal        = Column(CANAL_NOTIF, nullable=False)
    mensagem     = Column(String)
    prioridade   = Column(String)
    ativo_id     = Column(String)
    nivel        = Column(Integer, nullable=False, default=1)
    acionado_em  = Column(DateTime(timezone=True), default=datetime.utcnow)
    prazo_em     = Column(DateTime(timezone=True))   # sem ACK até aqui → reescalona
    ack_em       = Column(DateTime(timezone=True))
    ack_por      = Column(String)
    escalado     = Column(Boolean, default=False)


class AnaliseMidia(Base):
    """Análise de foto ou vídeo pelo modelo de visão (Sprint 5)."""
    __tablename__ = "analises_midia"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    incidente_id = Column(String, nullable=False)
    url          = Column(String, nullable=False)
    tipo         = Column(String, nullable=False)
    modelo       = Column(String)
    descricao    = Column(String)
    dados        = Column(JSONB)
    criado_em    = Column(DateTime(timezone=True), default=datetime.utcnow)
