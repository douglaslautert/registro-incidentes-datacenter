"""Fixtures comuns. Testes marcados com `banco` usam o PostgreSQL de teste (incidentes_teste),
preparado pelo testes.sh; os demais não precisam de nada além do código."""
import os
os.environ.setdefault("ENVIRONMENT", "test")

import pytest, httpx
from sqlalchemy import text
from app.core.config import settings
from app.services import tarefas, notificacao, topologia, seguranca


@pytest.fixture(autouse=True)
def configuracao(monkeypatch):
    """Cada teste começa com login opcional, sem IA e com um plantão de teste."""
    for k, v in {"AUTH_OBRIGATORIA": False, "TOKEN_SERVICO": "token-de-teste", "VISION_URL": "",
                 "EMBEDDINGS_URL": "", "PLANTAO_PHONE": "+5551000000001", "PLANTAO_EMAIL": "plantao@teste",
                 "PLANTAO_ESCALONAMENTO_PHONE": "+5551000000002",
                 "PLANTAO_ESCALONAMENTO_EMAIL": "coordenacao@teste", "LIGACAO_P1": True}.items():
        monkeypatch.setattr(settings, k, v)
    seguranca._jwks.update(chaves=None, quando=0.0)
    topologia.invalidar_cache()


@pytest.fixture(autouse=True)
def fila(monkeypatch):
    """Tarefas do Celery ficam registradas aqui em vez de ir para o worker real."""
    enviadas = []
    monkeypatch.setattr(tarefas, "enfileirar", lambda nome, *a: enviadas.append((nome, a)) or True)
    return enviadas


@pytest.fixture(autouse=True)
def canais(monkeypatch):
    """SMS, ligações e e-mails do plantão ficam registrados aqui."""
    feitos = {"sms": [], "ligacao": [], "email": []}
    monkeypatch.setattr(notificacao, "enviar_sms", lambda n, m: feitos["sms"].append((n, m)) or "simulado")
    monkeypatch.setattr(notificacao, "ligar", lambda n: feitos["ligacao"].append(n) or "simulado")

    async def email(para, assunto, corpo):
        feitos["email"].append((para, assunto))
        return True
    monkeypatch.setattr(notificacao, "enviar_email", email)
    return feitos


@pytest.fixture
async def cliente():
    from app.main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://teste") as c:
        yield c


@pytest.fixture
async def db():
    """Sessão no banco de teste, com as tabelas de incidentes limpas antes do teste."""
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as s:
        await s.execute(text("TRUNCATE incidentes, eventos, acionamentos, analises_midia, metricas_incidente"))
        await s.commit()
        yield s
        await s.rollback()


SERVICO = {"X-Token-Servico": "token-de-teste"}


def evento(ativo="srv-node-001", sintoma="Temperatura alta no servidor", sala="sala-A", **extra):
    return {"fonte": "pessoa", "ativo_id": ativo, "local": {"sala": sala}, "sintoma": sintoma, **extra}
