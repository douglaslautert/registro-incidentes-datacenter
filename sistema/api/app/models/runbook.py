from sqlalchemy import Column, String, Integer, DateTime, UniqueConstraint
from app.models.incidente import Base
from datetime import datetime

class Runbook(Base):
    __tablename__ = "runbooks"
    id        = Column(Integer, primary_key=True, autoincrement=True)
    sintoma   = Column(String, nullable=False)
    titulo    = Column(String, nullable=False)
    conteudo  = Column(String, nullable=False)
    versao    = Column(Integer, default=1)
    criado_em = Column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("sintoma", "versao"),)
