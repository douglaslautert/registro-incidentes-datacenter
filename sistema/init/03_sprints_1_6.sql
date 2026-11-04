-- Sprints 1–6: deduplicação, escalonamento persistido, topologia, embeddings e análise de mídia.
-- Idempotente. O mesmo conteúdo está na migração Alembic 0004 (instalações já existentes).

-- S3: deduplicação por fingerprint (ativo + sintoma) · S6: sugestão de correlação e mescla
ALTER TABLE incidentes ADD COLUMN IF NOT EXISTS fingerprint TEXT;
ALTER TABLE incidentes ADD COLUMN IF NOT EXISTS sugestao_correlacao TEXT;
ALTER TABLE incidentes ADD COLUMN IF NOT EXISTS mesclado_em TEXT;
CREATE INDEX IF NOT EXISTS idx_incidentes_fingerprint ON incidentes (fingerprint);
CREATE INDEX IF NOT EXISTS idx_incidentes_status ON incidentes (status);

-- S1: PROBLEM/RECOVERY do Zabbix · S6: modelo que gerou o embedding (só se comparam iguais)
ALTER TABLE eventos ADD COLUMN IF NOT EXISTS fingerprint TEXT;
ALTER TABLE eventos ADD COLUMN IF NOT EXISTS embedding_modelo TEXT;
ALTER TABLE eventos ADD COLUMN IF NOT EXISTS status_origem TEXT;
CREATE INDEX IF NOT EXISTS idx_eventos_zabbix ON eventos (zabbix_eventid);
CREATE INDEX IF NOT EXISTS idx_eventos_incidente ON eventos (incidente_id);

-- S4: fila de ACK no banco (a API e o worker são processos diferentes)
ALTER TABLE acionamentos ADD COLUMN IF NOT EXISTS prioridade TEXT;
ALTER TABLE acionamentos ADD COLUMN IF NOT EXISTS ativo_id TEXT;
ALTER TABLE acionamentos ADD COLUMN IF NOT EXISTS nivel INT NOT NULL DEFAULT 1;
ALTER TABLE acionamentos ADD COLUMN IF NOT EXISTS prazo_em TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_acionamentos_pendentes ON acionamentos (prazo_em) WHERE ack_em IS NULL AND NOT escalado;
CREATE INDEX IF NOT EXISTS idx_acionamentos_incidente ON acionamentos (incidente_id);

-- S5: resultado da análise de fotos e vídeos pelo modelo de visão
CREATE TABLE IF NOT EXISTS analises_midia (
    id           SERIAL      PRIMARY KEY,
    incidente_id TEXT        NOT NULL,
    url          TEXT        NOT NULL,
    tipo         TEXT        NOT NULL,
    modelo       TEXT,
    descricao    TEXT,
    dados        JSONB,
    criado_em    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_analises_incidente ON analises_midia (incidente_id);

-- S1: topologia de dependências do inventário (PDU → rack → servidor)
INSERT INTO qr_codes (qr_code, ativo_id, nome, sala, rack, tipo) VALUES
  ('CESUP-PDU-001', 'pdu-a-01', 'PDU Rack 01', 'sala-A', 'rack-01', 'pdu')
ON CONFLICT (qr_code) DO NOTHING;

INSERT INTO topologia_arestas (origem, destino, tipo) VALUES
  ('ups-sala-a-1',   'pdu-a-01',       'alimenta'),
  ('pdu-a-01',       'rack-01',        'alimenta'),
  ('rack-01',        'srv-node-001',   'contem'),
  ('rack-01',        'srv-node-002',   'contem'),
  ('rack-05',        'storage-01',     'contem'),
  ('rack-10',        'switch-core-01', 'contem'),
  ('switch-core-01', 'srv-node-001',   'rede'),
  ('switch-core-01', 'srv-node-002',   'rede'),
  ('switch-core-01', 'storage-01',     'rede')
ON CONFLICT (origem, destino) DO NOTHING;
