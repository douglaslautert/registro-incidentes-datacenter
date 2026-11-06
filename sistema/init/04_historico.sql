-- Histórico do incidente: quem encerrou e quem fez cada relato. Idempotente.
-- O mesmo conteúdo está na migração Alembic 0005 (instalações já existentes).
ALTER TABLE incidentes ADD COLUMN IF NOT EXISTS fechado_por TEXT;
ALTER TABLE eventos ADD COLUMN IF NOT EXISTS autor TEXT;
