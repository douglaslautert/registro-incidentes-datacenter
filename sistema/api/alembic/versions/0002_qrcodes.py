"""Migration Sprint 6 — tabela qr_codes

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-22
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "qr_codes",
        sa.Column("qr_code",   sa.String(100), primary_key=True),
        sa.Column("ativo_id",  sa.String(100), nullable=False),
        sa.Column("nome",      sa.String(200)),
        sa.Column("sala",      sa.String(50)),
        sa.Column("rack",      sa.String(50)),
        sa.Column("tipo",      sa.String(50),  server_default="servidor"),
        sa.Column("ativo_em",  sa.Boolean(),   server_default="true"),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
    )
    op.create_index("idx_qr_ativo_id", "qr_codes", ["ativo_id"])

    # Dados iniciais CESUP
    op.execute("""
        INSERT INTO qr_codes (qr_code, ativo_id, nome, sala, rack, tipo) VALUES
          ('CESUP-SRV-001', 'srv-node-001',   'Servidor Node 01',  'sala-A', 'rack-01', 'servidor'),
          ('CESUP-SRV-002', 'srv-node-002',   'Servidor Node 02',  'sala-A', 'rack-01', 'servidor'),
          ('CESUP-UPS-001', 'ups-sala-a-1',   'UPS Sala A - 1',    'sala-A', 'rack-01', 'ups'),
          ('CESUP-SW-001',  'switch-core-01', 'Switch Core 01',    'sala-DC','rack-10', 'switch'),
          ('CESUP-STG-001', 'storage-01',     'Storage 01',        'sala-B', 'rack-05', 'storage')
        ON CONFLICT (qr_code) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_index("idx_qr_ativo_id")
    op.drop_table("qr_codes")
