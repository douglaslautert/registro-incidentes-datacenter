"""Histórico do incidente: quem encerrou (incidentes.fechado_por) e quem fez cada relato
(eventos.autor). Mesmo conteúdo de init/04_historico.sql. Idempotente.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-06
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE incidentes ADD COLUMN IF NOT EXISTS fechado_por TEXT")
    op.execute("ALTER TABLE eventos ADD COLUMN IF NOT EXISTS autor TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE eventos DROP COLUMN IF EXISTS autor")
    op.execute("ALTER TABLE incidentes DROP COLUMN IF EXISTS fechado_por")
