"""Engine SQLAlchemy assíncrona — PostgreSQL com pgvector."""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings
import logging

log = logging.getLogger("database")

# Engine assíncrona com pool conservador para o MVP
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,   # reconecta automaticamente
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

class Base(DeclarativeBase):
    pass

async def get_db():
    """Dependência FastAPI: session por requisição com commit/rollback automático."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def criar_tabelas():
    """Cria todas as tabelas no banco (usado na inicialização em dev)."""
    async with engine.begin() as conn:
        from app.models import incidente, acionamento, topologia, runbook, metrica, qrcode
        await conn.run_sync(Base.metadata.create_all)
    log.info("Tabelas criadas/verificadas no banco")
