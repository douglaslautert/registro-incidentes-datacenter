from sqlalchemy import Column, String, Boolean, DateTime, Integer
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime
from app.models.incidente import Base

class Acionamento(Base):
    __tablename__ = "acionamentos"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    incidente_id = Column(String, nullable=False)
    usuario_id   = Column(String, nullable=False)
    canal        = Column(String, nullable=False)  # email|sms|ligacao|webpush
    mensagem     = Column(String)
    acionado_em  = Column(DateTime(timezone=True), default=datetime.utcnow)
    ack_em       = Column(DateTime(timezone=True))
    ack_por      = Column(String)
    escalado     = Column(Boolean, default=False)
