"""FastAPI — banco com lifespan e fallback para memória; Sprints 1–6."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.routers import (healthcheck, incidentes, webhook_zabbix, notificacoes, metricas,
                         evidencias, transcricao, ativos, topologia, ingestao, avaliacao, sistema)
import logging

log = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicialização: testa o banco e carrega o inventário de ativos."""
    try:
        from app.database import AsyncSessionLocal
        from app.services import inventario
        async with AsyncSessionLocal() as db:
            n = await inventario.recarregar(db)
        log.info(f"Banco de dados: conectado ({n} ativos no inventário)")
    except Exception as e:
        log.warning(f"Banco indisponível — modo memória: {e}")
    yield
    try:
        from app.database import engine
        await engine.dispose()
    except Exception:
        pass


app = FastAPI(
    title="CESUP Incidentes API",
    version="1.6.0",
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
for r in (notificacoes, metricas, evidencias, transcricao, ativos, topologia, ingestao, avaliacao, sistema):
    app.include_router(r.router)
