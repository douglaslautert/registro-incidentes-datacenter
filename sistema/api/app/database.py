"""Engine SQLAlchemy assíncrona — PostgreSQL com pgvector."""
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from app.core.config import settings
import logging

log = logging.getLogger("database")

# Engine assíncrona com pool conservador para o MVP. Nos testes, sem pool: cada teste
# roda num event loop próprio e não pode herdar conexões de outro.
engine = (
    create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    if settings.ENVIRONMENT == "test" else
    create_async_engine(
        settings.DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,   # reconecta automaticamente
        echo=False,
    )
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

@asynccontextmanager
async def sessao_isolada():
    """Sessão com engine própria e sem pool, para as tarefas do Celery: cada tarefa roda
    num asyncio.run() novo, e conexões do pool global ficariam presas ao loop anterior."""
    eng = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        async with async_sessionmaker(eng, expire_on_commit=False)() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise
    finally:
        await eng.dispose()

async def criar_tabelas():
    """Cria todas as tabelas no banco (usado na inicialização em dev)."""
    async with engine.begin() as conn:
        from app.models import incidente, acionamento, topologia, runbook, metrica, qrcode
        await conn.run_sync(Base.metadata.create_all)
    log.info("Tabelas criadas/verificadas no banco")
