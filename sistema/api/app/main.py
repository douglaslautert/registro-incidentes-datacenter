"""FastAPI — Sprint 6: banco real com lifespan e fallback para memória."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.routers import (healthcheck, incidentes, webhook_zabbix,
                         notificacoes, metricas, evidencias, transcricao, ativos)
import logging

log = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicialização: testar conexão com banco."""
    try:
        from app.database import engine
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        log.info("Banco de dados: conectado")
    except Exception as e:
        log.warning(f"Banco indisponível — modo memória: {e}")
    yield
    # Shutdown
    try:
        from app.database import engine
        await engine.dispose()
    except Exception:
        pass


app = FastAPI(
    title="CESUP Incidentes API",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(healthcheck.router)
app.include_router(incidentes.router,      prefix="/api/v1")
app.include_router(webhook_zabbix.router,  prefix="/api/v1")
app.include_router(notificacoes.router)
app.include_router(metricas.router)
app.include_router(evidencias.router)
app.include_router(transcricao.router)
app.include_router(ativos.router)
