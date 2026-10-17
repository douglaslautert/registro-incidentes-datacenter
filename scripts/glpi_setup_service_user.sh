#!/bin/bash
# Cria usuário de serviço 'zabbix-api' no GLPI e gera user_token
# Rode uma vez após a instalação do GLPI.
#
# Variáveis necessárias:
#   GLPI_ADMIN_PASS  - senha do admin do GLPI
#   GLPI_APP_TOKEN   - App-Token (GLPI > Setup > General > API)
#   GLPI_SVC_PASS    - senha que o usuário zabbix-api vai usar
#   GLPI_URL         - URL da API REST (ex: https://glpi.intra/apirest.php)

set -euo pipefail

GLPI_URL="${GLPI_URL:-https://glpi.suarede.intra/apirest.php}"

echo "=== Criando usuário de serviço no GLPI ==="

# Iniciar sessão como admin
SESSION=$(curl -sS \
  -H "Content-Type: application/json" \
  -H "App-Token: $GLPI_APP_TOKEN" \
  -H "Authorization: Basic $(echo -n glpi:$GLPI_ADMIN_PASS | base64)" \
  "$GLPI_URL/initSession" | jq -r .session_token)

if [ -z "$SESSION" ] || [ "$SESSION" = "null" ]; then
  echo "ERRO: falha ao autenticar como admin. Verifique GLPI_ADMIN_PASS e GLPI_APP_TOKEN."
  exit 1
fi
echo "✅ Sessão iniciada"

# Criar usuário de serviço
USER_ID=$(curl -sS -X POST \
  -H "Content-Type: application/json" \
  -H "App-Token: $GLPI_APP_TOKEN" \
  -H "Session-Token: $SESSION" \
  -d "{\"input\": {
    \"name\": \"zabbix-api\",
    \"realname\": \"Zabbix Service Account\",
    \"password\": \"$GLPI_SVC_PASS\",
    \"password2\": \"$GLPI_SVC_PASS\",
    \"is_active\": 1,
    \"profiles_id\": 4
  }}" \
  "$GLPI_URL/User" | jq -r .id)

echo "✅ Usuário de serviço criado — ID: $USER_ID"

# Gerar token do usuário
TOKEN=$(curl -sS -X POST \
  -H "Content-Type: application/json" \
  -H "App-Token: $GLPI_APP_TOKEN" \
  -H "Session-Token: $SESSION" \
  -d "{\"input\": {\"users_id\": $USER_ID}}" \
  "$GLPI_URL/UserToken" | jq -r .token)

echo "🔑 user_token: $TOKEN"
echo ""
echo "→ Copie este token e adicione ao group_vars/all.yml via ansible-vault"
echo "→ Comando: ansible-vault encrypt_string '$TOKEN' --name 'glpi_user_token'"

# Encerrar sessão
curl -sS \
  -H "App-Token: $GLPI_APP_TOKEN" \
  -H "Session-Token: $SESSION" \
  "$GLPI_URL/killSession" > /dev/null

echo "✅ Concluído"
