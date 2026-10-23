"""Schema inicial — todas as tabelas do CESUP

Revision ID: 0001
Revises:
Create Date: 2026-10-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pgvector — já criado pelo initdb, mas garantir
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Tipos ENUM
    op.execute("DO $$ BEGIN CREATE TYPE fonte_evento AS ENUM ('pessoa','zabbix','email'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE prioridade_enum AS ENUM ('P1','P2','P3','P4'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE status_incidente AS ENUM ('aberto','em_atendimento','resolvido','falso_positivo'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE canal_notif AS ENUM ('email','sms','ligacao','webpush'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")

    op.create_table("incidentes",
        sa.Column("id",        sa.String(),  primary_key=True),
        sa.Column("titulo",    sa.String(),  nullable=False),
        sa.Column("prioridade",sa.String(),  nullable=False, server_default="P4"),
        sa.Column("status",    sa.String(),  nullable=False, server_default="aberto"),
        sa.Column("ativo_id",  sa.String()),
        sa.Column("causa_raiz",sa.String()),
        sa.Column("aberto_em", sa.DateTime(timezone=True), primary_key=True, server_default=sa.text("now()")),
        sa.Column("fechado_em",sa.DateTime(timezone=True)),
        sa.Column("criado_por",sa.String()),
        postgresql_partition_by="RANGE (aberto_em)",
    )
    op.execute("CREATE TABLE IF NOT EXISTS incidentes_2026_q4 PARTITION OF incidentes FOR VALUES FROM ('2026-10-01') TO ('2027-01-01')")
    op.execute("CREATE TABLE IF NOT EXISTS incidentes_2027_q1 PARTITION OF incidentes FOR VALUES FROM ('2027-01-01') TO ('2027-04-01')")

    op.create_table("acionamentos",
        sa.Column("id",           sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("incidente_id", sa.String(),  nullable=False),
        sa.Column("usuario_id",   sa.String(),  nullable=False),
        sa.Column("canal",        sa.String(),  nullable=False),
        sa.Column("mensagem",     sa.String()),
        sa.Column("acionado_em",  sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("ack_em",       sa.DateTime(timezone=True)),
        sa.Column("ack_por",      sa.String()),
        sa.Column("escalado",     sa.Boolean(), server_default="false"),
    )
    op.create_table("topologia_arestas",
        sa.Column("origem",  sa.String(), primary_key=True),
        sa.Column("destino", sa.String(), primary_key=True),
        sa.Column("tipo",    sa.String(), server_default="alimenta"),
        sa.Column("peso",    sa.Float(),  server_default="1.0"),
        sa.Column("ativo_em",sa.Boolean(),server_default="true"),
    )
    op.create_table("runbooks",
        sa.Column("id",       sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("sintoma",  sa.String(),  nullable=False),
        sa.Column("titulo",   sa.String(),  nullable=False),
        sa.Column("conteudo", sa.String(),  nullable=False),
        sa.Column("versao",   sa.Integer(), server_default="1"),
        sa.Column("criado_em",sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("sintoma","versao"),
    )
    op.create_table("metricas_incidente",
        sa.Column("incidente_id",   sa.String(),  primary_key=True),
        sa.Column("mtta_segundos",  sa.Float()),
        sa.Column("mttr_segundos",  sa.Float()),
        sa.Column("falso_positivo", sa.Boolean(), server_default="false"),
        sa.Column("causa_fp",       sa.String()),
        sa.Column("avaliado_em",    sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("metricas_incidente")
    op.drop_table("runbooks")
    op.drop_table("topologia_arestas")
    op.drop_table("acionamentos")
    op.drop_table("incidentes")
