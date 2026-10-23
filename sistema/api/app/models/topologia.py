from sqlalchemy import Column, String, Float, Boolean
from app.models.incidente import Base

class TopologiaAresta(Base):
    __tablename__ = "topologia_arestas"
    origem  = Column(String, primary_key=True)
    destino = Column(String, primary_key=True)
    tipo    = Column(String, default="alimenta")
    peso    = Column(Float, default=1.0)
    ativo_em = Column(Boolean, default=True)
