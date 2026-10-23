#!/bin/bash
# Diagnóstico rápido do Keycloak
set -e
echo "=== Status do container ==="
docker compose ps keycloak 2>/dev/null || docker ps -a --filter name=cesup-keycloak
echo ""
echo "=== Últimas 80 linhas de log ==="
docker logs cesup-keycloak --tail 80 2>&1 || true
echo ""
echo "=== Banco keycloak existe? ==="
docker compose exec -T postgres psql -U cesup -d postgres -tAc \
  "SELECT datname FROM pg_database WHERE datname='keycloak';" 2>/dev/null || echo "(postgres indisponível)"
echo ""
echo "=== Teste HTTP interno (via docker) ==="
docker compose exec -T keycloak bash -c 'exec 3<>/dev/tcp/127.0.0.1/8080 && echo PORT_8080_OK' 2>/dev/null || echo "PORT_8080_FAIL"
echo ""
echo "=== Token admin via nginx ==="
curl -sS -m 5 -X POST "http://localhost/auth/realms/master/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=${KC_ADMIN_USER:-admin}&password=${KC_ADMIN_PASSWORD:-admin123}&grant_type=password&client_id=admin-cli" \
  | head -c 200 || echo "token request failed"
echo ""
