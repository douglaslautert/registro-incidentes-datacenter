-- Tabela de mapeamento QR Code → Ativo (Sprint 5)
CREATE TABLE IF NOT EXISTS qr_codes (
    qr_code VARCHAR(100) PRIMARY KEY,
    ativo_id VARCHAR(100) NOT NULL,
    nome      VARCHAR(200),
    sala      VARCHAR(50),
    rack      VARCHAR(50),
    tipo      VARCHAR(50) DEFAULT 'servidor',
    ativo_em  BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMPTZ DEFAULT NOW()
);

-- Dados iniciais — ativos do CESUP
INSERT INTO qr_codes (qr_code, ativo_id, nome, sala, rack, tipo) VALUES
  ('CESUP-SRV-001', 'srv-node-001',   'Servidor Node 01',  'sala-A', 'rack-01', 'servidor'),
  ('CESUP-SRV-002', 'srv-node-002',   'Servidor Node 02',  'sala-A', 'rack-01', 'servidor'),
  ('CESUP-UPS-001', 'ups-sala-a-1',   'UPS Sala A — 1',    'sala-A', 'rack-01', 'ups'),
  ('CESUP-SW-001',  'switch-core-01', 'Switch Core 01',    'sala-DC','rack-10', 'switch'),
  ('CESUP-STG-001', 'storage-01',     'Storage 01',        'sala-B', 'rack-05', 'storage')
ON CONFLICT (qr_code) DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_qr_ativo_id ON qr_codes(ativo_id);
