from sqlalchemy import Column, String, Float, Boolean, DateTime
from app.models.incidente import Base

class MetricaIncidente(Base):
    __tablename__ = "metricas_incidente"
    incidente_id   = Column(String, primary_key=True)
    mtta_segundos  = Column(Float)
    mttr_segundos  = Column(Float)
    falso_positivo = Column(Boolean, default=False)
    causa_fp       = Column(String)
    avaliado_em    = Column(DateTime(timezone=True))
