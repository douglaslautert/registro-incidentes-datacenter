#!/bin/bash
# Limpa o volume do Postgres e reinicia — use quando o postgres está unhealthy
set -euo pipefail
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

echo -e "${YELLOW}⚠ Isso vai apagar TODOS os dados do banco de incidentes e keycloak${NC}"
read -rp "Confirma? (s/N) " C; [[ "${C,,}" == "s" ]] || exit 0

echo "→ Parando postgres..."
docker compose stop postgres keycloak api worker beat 2>/dev/null || true
docker compose rm -f postgres 2>/dev/null || true

echo "→ Apagando volume do postgres..."
docker volume rm cesup-sistema_postgres-data 2>/dev/null || \
docker volume rm cesup_postgres-data 2>/dev/null || \
docker volume ls | grep postgres | awk '{print $2}' | xargs -r docker volume rm

echo "→ Recriando container..."
docker compose up -d postgres

echo "→ Aguardando postgres ficar healthy..."
until docker inspect --format='{{.State.Health.Status}}' cesup-postgres 2>/dev/null | grep -q healthy; do
    sleep 5; echo "   aguardando..."
done

echo -e "${GREEN}✔ Postgres recriado com sucesso${NC}"
echo "→ Reiniciando demais serviços..."
docker compose up -d
