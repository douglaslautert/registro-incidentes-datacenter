"""Model SQLAlchemy para mapeamento QR Code → Ativo."""
from sqlalchemy import Column, String, Boolean, DateTime, Index
from sqlalchemy.sql import func
from app.database import Base

class QrCode(Base):
    __tablename__ = "qr_codes"

    qr_code   = Column(String(100), primary_key=True)
    ativo_id  = Column(String(100), nullable=False, index=True)
    nome      = Column(String(200))
    sala      = Column(String(50))
    rack      = Column(String(50))
    tipo      = Column(String(50), default="servidor")
    ativo_em  = Column(Boolean, default=True)
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
