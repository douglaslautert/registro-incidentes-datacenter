#!/bin/bash
# Testes da API (unidade + integração) num banco separado, incidentes_teste.
# Não toca no banco de produção: recria o de teste a cada execução, com os mesmos
# init/*.sql da instalação, e roda o pytest num container temporário da API com o
# código atual montado (não precisa rebuild). Uso: make test [args="-k zabbix"]
set -euo pipefail
cd "$(dirname "$0")"
set -a; source .env; set +a

BANCO=incidentes_teste
echo "== recriando o banco $BANCO"
docker compose exec -T postgres psql -q -U cesup -d postgres \
    -c "DROP DATABASE IF EXISTS $BANCO WITH (FORCE)" -c "CREATE DATABASE $BANCO"
# Schema de antes das Sprints 1–6; a migração 0004 roda em seguida, como num servidor existente
for f in init/01_schema.sql init/02_qrcodes.sql; do
    docker compose exec -T postgres psql -q -v ON_ERROR_STOP=1 -U cesup -d "$BANCO" < "$f" >/dev/null
done

echo "== pytest"
docker compose run --rm --no-deps --user root \
    -e ENVIRONMENT=test \
    -e DATABASE_URL="postgresql+asyncpg://cesup:${POSTGRES_PASSWORD}@postgres:5432/$BANCO" \
    -e PIP_DISABLE_PIP_VERSION_CHECK=1 \
    -v "$PWD/api/app:/app/app:ro" -v "$PWD/api/tests:/app/tests:ro" \
    -v "$PWD/api/pytest.ini:/app/pytest.ini:ro" -v "$PWD/api/requirements-dev.txt:/app/requirements-dev.txt:ro" \
    -v "$PWD/api/alembic:/app/alembic:ro" -v "$PWD/api/alembic.ini:/app/alembic.ini:ro" \
    api sh -c "pip install -q -r requirements-dev.txt && alembic stamp 0003 && alembic upgrade head \
               && python -m pytest -p no:cacheprovider ${args:-} ${*:-}"
