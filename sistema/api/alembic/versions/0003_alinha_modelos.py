"""Alinha o schema aos modelos ORM — colunas que a API grava e partição default

Instalações criadas pelo init/01_schema.sql antigo não tinham colunas que os
modelos usam (incidentes.local, eventos.local...), e toda escrita da API
falhava e caía no modo memória. Idempotente: pode rodar sobre o schema novo.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-23
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE incidentes ADD COLUMN IF NOT EXISTS local JSONB")
    op.execute("CREATE TABLE IF NOT EXISTS incidentes_default PARTITION OF incidentes DEFAULT")

    op.execute("ALTER TABLE eventos ADD COLUMN IF NOT EXISTS local JSONB")

    op.execute("ALTER TABLE acionamentos ADD COLUMN IF NOT EXISTS mensagem TEXT")
    op.execute("ALTER TABLE acionamentos ADD COLUMN IF NOT EXISTS ack_por TEXT")

    op.execute("ALTER TABLE topologia_arestas ADD COLUMN IF NOT EXISTS ativo_em BOOLEAN NOT NULL DEFAULT true")

    op.execute("ALTER TABLE runbooks ADD COLUMN IF NOT EXISTS versao INT NOT NULL DEFAULT 1")
    op.execute("ALTER TABLE runbooks ADD COLUMN IF NOT EXISTS criado_em TIMESTAMPTZ NOT NULL DEFAULT now()")
    # Unicidade passa de (sintoma) para (sintoma, versao), como no modelo
    op.execute("ALTER TABLE runbooks DROP CONSTRAINT IF EXISTS runbooks_sintoma_key")
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE runbooks ADD CONSTRAINT runbooks_sintoma_versao_key UNIQUE (sintoma, versao);
        EXCEPTION WHEN duplicate_table OR duplicate_object THEN NULL;
        END $$
    """)

    op.execute("ALTER TABLE metricas_incidente ADD COLUMN IF NOT EXISTS causa_fp TEXT")
    op.execute("ALTER TABLE metricas_incidente ADD COLUMN IF NOT EXISTS avaliado_em TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE metricas_incidente DROP COLUMN IF EXISTS avaliado_em")
    op.execute("ALTER TABLE metricas_incidente DROP COLUMN IF EXISTS causa_fp")
    op.execute("ALTER TABLE runbooks DROP CONSTRAINT IF EXISTS runbooks_sintoma_versao_key")
    op.execute("ALTER TABLE runbooks DROP COLUMN IF EXISTS criado_em")
    op.execute("ALTER TABLE runbooks DROP COLUMN IF EXISTS versao")
    op.execute("ALTER TABLE runbooks ADD CONSTRAINT runbooks_sintoma_key UNIQUE (sintoma)")
    op.execute("ALTER TABLE topologia_arestas DROP COLUMN IF EXISTS ativo_em")
    op.execute("ALTER TABLE acionamentos DROP COLUMN IF EXISTS ack_por")
    op.execute("ALTER TABLE acionamentos DROP COLUMN IF EXISTS mensagem")
    op.execute("ALTER TABLE eventos DROP COLUMN IF EXISTS local")
    op.execute("DROP TABLE IF EXISTS incidentes_default")
    op.execute("ALTER TABLE incidentes DROP COLUMN IF EXISTS local")
