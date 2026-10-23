CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

DO $$ BEGIN
    CREATE TYPE fonte_evento     AS ENUM ('pessoa', 'zabbix', 'email');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE prioridade_enum  AS ENUM ('P1', 'P2', 'P3', 'P4');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE status_incidente AS ENUM ('aberto', 'em_atendimento', 'resolvido', 'falso_positivo');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE canal_notif      AS ENUM ('email', 'sms', 'ligacao', 'webpush');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS incidentes (
    id           TEXT        NOT NULL DEFAULT 'inc_' || substr(md5(random()::text),1,12),
    titulo       TEXT        NOT NULL,
    prioridade   prioridade_enum  NOT NULL DEFAULT 'P4',
    status       status_incidente NOT NULL DEFAULT 'aberto',
    ativo_id     TEXT,
    causa_raiz   TEXT,
    aberto_em    TIMESTAMPTZ NOT NULL DEFAULT now(),
    fechado_em   TIMESTAMPTZ,
    criado_por   TEXT,
    PRIMARY KEY (id, aberto_em)
) PARTITION BY RANGE (aberto_em);

CREATE TABLE IF NOT EXISTS incidentes_2026_q4 PARTITION OF incidentes FOR VALUES FROM ('2026-10-01') TO ('2027-01-01');
CREATE TABLE IF NOT EXISTS incidentes_2027_q1 PARTITION OF incidentes FOR VALUES FROM ('2027-01-01') TO ('2027-04-01');

CREATE TABLE IF NOT EXISTS eventos (
    id                TEXT        PRIMARY KEY,
    incidente_id      TEXT,
    fonte             fonte_evento NOT NULL,
    ativo_id          TEXT        NOT NULL,
    local_sala        TEXT,
    local_fileira     TEXT,
    local_rack        TEXT,
    local_unidade     INT,
    sintoma           TEXT        NOT NULL,
    confianca         FLOAT       NOT NULL CHECK (confianca BETWEEN 0 AND 1),
    seguranca_pessoas BOOLEAN     NOT NULL DEFAULT false,
    evidencias        TEXT[],
    embedding         vector(1024),
    recebido_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    zabbix_eventid    TEXT,
    raw_payload       JSONB
);

CREATE INDEX IF NOT EXISTS idx_eventos_embedding ON eventos USING ivfflat (embedding vector_cosine_ops) WITH (lists=100);
CREATE INDEX IF NOT EXISTS idx_eventos_recebido_em ON eventos (recebido_em DESC);
CREATE INDEX IF NOT EXISTS idx_eventos_ativo_id ON eventos (ativo_id);

CREATE TABLE IF NOT EXISTS acionamentos (
    id            SERIAL      PRIMARY KEY,
    incidente_id  TEXT        NOT NULL,
    usuario_id    TEXT        NOT NULL,
    canal         canal_notif NOT NULL,
    acionado_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
    ack_em        TIMESTAMPTZ,
    escalado      BOOLEAN     NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS topologia_arestas (
    origem   TEXT  NOT NULL,
    destino  TEXT  NOT NULL,
    tipo     TEXT  NOT NULL DEFAULT 'alimenta',
    peso     FLOAT NOT NULL DEFAULT 1.0,
    PRIMARY KEY (origem, destino)
);

CREATE TABLE IF NOT EXISTS runbooks (
    id        SERIAL PRIMARY KEY,
    sintoma   TEXT   NOT NULL,
    titulo    TEXT   NOT NULL,
    conteudo  TEXT   NOT NULL,
    UNIQUE (sintoma)
);

CREATE TABLE IF NOT EXISTS metricas_incidente (
    incidente_id   TEXT    PRIMARY KEY,
    mtta_segundos  FLOAT,
    mttr_segundos  FLOAT,
    falso_positivo BOOLEAN NOT NULL DEFAULT false
);

CREATE OR REPLACE VIEW v_incidentes_abertos AS
SELECT i.id, i.titulo, i.prioridade, i.status, i.ativo_id, i.aberto_em,
       EXTRACT(EPOCH FROM (now() - i.aberto_em))/60 AS minutos_aberto,
       count(e.id) AS total_eventos
FROM incidentes i
LEFT JOIN eventos e ON e.incidente_id = i.id
WHERE i.status IN ('aberto','em_atendimento')
GROUP BY i.id, i.titulo, i.prioridade, i.status, i.ativo_id, i.aberto_em
ORDER BY CASE i.prioridade WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 WHEN 'P3' THEN 3 ELSE 4 END, i.aberto_em;

-- ─── View: MTTA e MTTR por período ───────────────────────────────────────────
CREATE OR REPLACE VIEW v_metricas_periodo AS
SELECT
    date_trunc('week', i.aberto_em) AS semana,
    i.prioridade,
    count(*)                         AS total,
    avg(m.mtta_segundos) / 60        AS mtta_minutos,
    avg(m.mttr_segundos) / 3600      AS mttr_horas,
    sum(CASE WHEN m.falso_positivo THEN 1 ELSE 0 END) AS falsos_positivos
FROM incidentes i
LEFT JOIN metricas_incidente m ON m.incidente_id = i.id
GROUP BY date_trunc('week', i.aberto_em), i.prioridade
ORDER BY semana DESC, i.prioridade;

-- ─── Função: distância topológica (CTE recursiva) ────────────────────────────
CREATE OR REPLACE FUNCTION distancia_topologica(
    origem TEXT, destino TEXT, max_depth INT DEFAULT 5
) RETURNS FLOAT AS $$
DECLARE dist FLOAT := 0.0;
BEGIN
    WITH RECURSIVE caminho AS (
        SELECT origem AS no, 0 AS prof, 1.0 AS acum
        UNION ALL
        SELECT t.destino, c.prof + 1, c.acum * t.peso
        FROM topologia_arestas t
        JOIN caminho c ON t.origem = c.no
        WHERE c.prof < max_depth
    )
    SELECT 1.0 / (1.0 + prof) INTO dist
    FROM caminho WHERE no = destino
    ORDER BY prof LIMIT 1;
    RETURN COALESCE(dist, 0.0);
END;
$$ LANGUAGE plpgsql;
