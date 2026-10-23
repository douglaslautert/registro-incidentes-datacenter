#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  CESUP Incidentes — setup.sh
#  Configura tudo automaticamente:
#  Keycloak · Garage S3 · Zabbix (banco + webhook) · GLPI (banco + API)
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✔ $1${NC}"; }
info() { echo -e "${BLUE}  → $1${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $1${NC}"; }
fail() { echo -e "${RED}  ✗ $1${NC}"; exit 1; }

echo ""
echo -e "${BLUE}══════════════════════════════════════════════${NC}"
echo -e "${BLUE}  CESUP Incidentes — Setup completo${NC}"
echo -e "${BLUE}══════════════════════════════════════════════${NC}"
echo ""

[ ! -f .env ] && fail "Arquivo .env não encontrado."
source .env
ok ".env carregado"

docker info &>/dev/null || fail "Docker não está rodando."
for _cmd in curl python3; do
    command -v "$_cmd" >/dev/null || fail "$_cmd não encontrado — instale-o no servidor"
done
ok "Docker OK"

# ──────────────────────────────────────────────────────────────
# Função: aguardar container ficar healthy
# ──────────────────────────────────────────────────────────────
# Atualiza (ou acrescenta) CHAVE=VALOR no .env
set_env() {
    if grep -q "^$1=" .env; then
        sed -i "s|^$1=.*|$1=$2|" .env
    else
        echo "$1=$2" >> .env
    fi
}

# Aguarda container healthy (timeout em segundos no 2º argumento)
wait_healthy() {
    local name=$1
    local max=${2:-600}
    local i=0
    info "Aguardando $name ficar pronto (timeout ${max}s)..."
    while [ $i -lt $max ]; do
        status=$(docker inspect --format='{{.State.Health.Status}}' "cesup-$name" 2>/dev/null || echo "starting")
        [ "$status" = "healthy" ] && ok "$name pronto (${i}s)" && return 0
        state=$(docker inspect --format='{{.State.Status}}' "cesup-$name" 2>/dev/null || echo "missing")
        case "$state" in
            exited|dead|missing) warn "$name está '$state' — verifique: docker logs cesup-$name"; return 1 ;;
        esac
        i=$((i+5)); [ $((i % 30)) -eq 0 ] && info "$name ainda iniciando (${i}/${max}s)..."
        sleep 5
    done
    warn "$name não ficou healthy em ${max}s — status: $status"
    return 1
}

# Aguarda URL responder sem limite de tempo
wait_url() {
    local url=$1
    local max=${2:-300}
    local i=0
    info "Aguardando $url (timeout ${max}s)..."
    while [ $i -lt $max ]; do
        code=$(curl -sf -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")
        if [ "$code" = "200" ] || [ "$code" = "302" ] || [ "$code" = "301" ]; then
            ok "URL respondendo ($code)"
            return 0
        fi
        i=$((i+5)); [ $((i % 30)) -eq 0 ] && info "$url ainda não responde (${i}/${max}s, HTTP $code)..."
        sleep 5
    done
    warn "$url não respondeu em ${max}s (HTTP $code)"
    return 1
}

# ══════════════════════════════════════════════════════════════
# PASSO 1 — Build e subida dos containers
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}[1/7] Build e subida dos containers...${NC}"

docker compose build --no-cache api pwa-builder keycloak

# Postgres primeiro → cria DB keycloak → evita crash loop
info "Subindo Postgres primeiro..."
docker compose up -d postgres
wait_healthy postgres 90

KC_DB_EXISTS=$(docker compose exec -T postgres psql -U cesup -d postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname='keycloak';" 2>/dev/null || echo "")
if [ "$KC_DB_EXISTS" = "1" ]; then
    ok "Banco keycloak já existe"
else
    docker compose exec -T postgres psql -U cesup -d postgres \
        -c "CREATE DATABASE keycloak WITH ENCODING='UTF8';" \
        -c "GRANT ALL PRIVILEGES ON DATABASE keycloak TO cesup;" \
        2>/dev/null && ok "Banco keycloak criado" || warn "Erro ao criar banco keycloak"
fi

info "Subindo demais containers..."
docker compose up -d
ok "Containers iniciados"

# ══════════════════════════════════════════════════════════════
# PASSO 2 — Aguardar serviços de banco ficarem prontos
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}[2/7] Aguardando bancos de dados ficarem prontos...${NC}"

wait_healthy mysql    120
wait_healthy valkey    30
ok "Bancos prontos"


# ══════════════════════════════════════════════════════════════
# PASSO 3 — Banco do Zabbix
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}[3/7] Configurando banco do Zabbix...${NC}"

# Verificar se o banco do Zabbix já tem tabelas
ZBX_TABLES=$(docker compose exec -T mysql mysql \
    -u zabbix -p"${MYSQL_ZABBIX_PASSWORD}" zabbix \
    -sse "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='zabbix';" \
    2>/dev/null || echo "0")
ZBX_TABLES=$(echo "${ZBX_TABLES}" | tr -d '[:space:]\n' | grep -E '^[0-9]+$' || echo "0")

if [ "$ZBX_TABLES" -gt "10" ]; then
    warn "Banco do Zabbix já tem $ZBX_TABLES tabelas — pulando"
else
    info "Aguardando Zabbix Server criar o schema..."
    info "(Isso pode levar até 3 minutos na primeira vez)"

    # O zabbix-server cria o schema automaticamente ao iniciar
    # Apenas aguardamos ele terminar
    i=0
    max=180
    while [ $i -lt $max ]; do
        ZBX_TABLES=$(docker compose exec -T mysql mysql \
            -u zabbix -p"${MYSQL_ZABBIX_PASSWORD}" zabbix \
            -sse "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='zabbix';" \
            2>/dev/null || echo "0")
        ZBX_TABLES=$(echo "${ZBX_TABLES}" | tr -d '[:space:]\n' | grep -E '^[0-9]+$' || echo "0")
        if [ "$ZBX_TABLES" -gt "50" ]; then
            ok "Schema do Zabbix criado ($ZBX_TABLES tabelas)"
            break
        fi
        sleep 5; i=$((i+5))
        echo -ne "    aguardando... ${i}s/${max}s\r"
    done
    echo ""

    [ "$ZBX_TABLES" -le "50" ] && warn "Schema do Zabbix pode não estar completo — verifique os logs: make zabbix-logs"
fi

wait_healthy zabbix-web 180 || warn "zabbix-web ainda não healthy — seguindo"

# ══════════════════════════════════════════════════════════════
# PASSO 4 — GLPI: banco, API REST e App-Token (glpi-setup.sh)
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}[4/7] Instalando GLPI...${NC}"

bash glpi-setup.sh && ok "GLPI configurado" \
    || warn "GLPI não configurado — corrija e rode: make glpi-setup"

# PASSO 5 — Configurar Keycloak
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}[5/7] Configurando Keycloak...${NC}"

# Keycloak demora 60-180s na primeira vez (importa o realm, conecta ao Postgres)
# Aguardar até 300s tentando autenticar a cada 10s
KC_URL="http://localhost/auth"
KC_ADMIN="${KC_ADMIN_USER:-admin}"
KC_PASS="${KC_ADMIN_PASSWORD:-admin123}"
KC_TOKEN=""

info "Aguardando Keycloak ficar pronto (timeout 5 min)..."
KC_WAIT=0
KC_MAX=300
KC_TOKEN=""
while [ $KC_WAIT -lt $KC_MAX ]; do
    KC_STATE=$(docker inspect --format='{{.State.Status}}' cesup-keycloak 2>/dev/null || echo "missing")
    if [ "$KC_STATE" = "exited" ] || [ "$KC_STATE" = "dead" ] || [ "$KC_STATE" = "missing" ]; then
        warn "Container Keycloak está '$KC_STATE' — docker logs cesup-keycloak"
        break
    fi
    KC_TOKEN=$(curl -sf --max-time 5 -X POST \
        "$KC_URL/realms/master/protocol/openid-connect/token" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "username=$KC_ADMIN&password=$KC_PASS&grant_type=password&client_id=admin-cli" \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")
    if [ -n "$KC_TOKEN" ]; then
        ok "Keycloak pronto (${KC_WAIT}s)"
        break
    fi
    KC_WAIT=$((KC_WAIT+10))
    [ $((KC_WAIT % 30)) -eq 0 ] && info "Keycloak ainda iniciando (${KC_WAIT}/${KC_MAX}s)..."
    sleep 10
done
if [ -z "$KC_TOKEN" ]; then
    warn "Keycloak não autenticou — verifique: docker logs cesup-keycloak"
else
    ok "Autenticado no Keycloak"

    # Verificar se o realm foi importado pelo --import-realm (já deve estar lá)
    REALM_STATUS=$(curl -sf --max-time 5 -o /dev/null -w "%{http_code}"         -H "Authorization: Bearer $KC_TOKEN"         "$KC_URL/admin/realms/cesup" 2>/dev/null || echo "000")

    if [ "$REALM_STATUS" = "200" ]; then
        ok "Realm 'cesup' já importado automaticamente"
    else
        info "Importando realm cesup via API..."
        HTTP=$(curl -sf --max-time 10 -o /dev/null -w "%{http_code}" -X POST             "$KC_URL/admin/realms"             -H "Authorization: Bearer $KC_TOKEN"             -H "Content-Type: application/json"             -d @keycloak/realm-cesup.json 2>/dev/null || echo "000")
        case "$HTTP" in
            201) ok "Realm 'cesup' criado com sucesso" ;;
            409) ok "Realm 'cesup' já existe" ;;
            *)   warn "Importação do realm retornou HTTP $HTTP — verifique em http://localhost/auth" ;;
        esac
    fi
fi

# ══════════════════════════════════════════════════════════════
# PASSO 6 — Configurar Garage S3
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}[6/7] Configurando Garage S3...${NC}"

bash garage-setup.sh || warn "Garage S3 não configurado — corrija e rode: make garage-setup"

# Banco novo: schema já criado pelos scripts init/*.sql — só marcar o Alembic.
# Banco já versionado (reexecução do setup): aplicar as migrações pendentes.
wait_healthy api 120 || true
ALEMBIC_REV=$(docker compose exec -T postgres psql -U cesup -d incidentes -tAc \
    "SELECT version_num FROM alembic_version LIMIT 1;" 2>/dev/null | tr -d '[:space:]' || true)
if [ -z "$ALEMBIC_REV" ]; then
    docker compose exec -T api alembic stamp head >/dev/null 2>&1 \
        && ok "Alembic marcado na revisão atual" \
        || warn "Não foi possível marcar o Alembic — rode: docker compose exec api alembic stamp head"
else
    docker compose exec -T api alembic upgrade head >/dev/null 2>&1 \
        && ok "Migrações Alembic aplicadas (a partir de $ALEMBIC_REV)" \
        || warn "Falha nas migrações — rode: make migrate"
fi

# ══════════════════════════════════════════════════════════════
# PASSO 7 — Configurar Zabbix via API
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}[7/7] Configurando Zabbix via API...${NC}"

bash zabbix-setup.sh || warn "Zabbix não configurado — corrija e rode: make zabbix-setup"


# ══════════════════════════════════════════════════════════════
# INSTRUÇÃO FINAL — Vigia externo
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${YELLOW}══════════════════════════════════════════════${NC}"
echo -e "${YELLOW}  PRÓXIMO PASSO — Configurar o vigia externo${NC}"
echo -e "${YELLOW}══════════════════════════════════════════════${NC}"
echo ""
echo -e "  O vigia externo deve ser instalado em outro dispositivo"
echo -e "  (Raspberry Pi, notebook) em outro prédio com 4G/GSM."
echo ""
echo -e "  Token do vigia (copie para o .env do vigia):"
echo -e "  ${YELLOW}VIGIA_TOKEN=$(grep VIGIA_TOKEN .env | cut -d= -f2)${NC}"
echo ""
echo -e "  URL do heartbeat:"
echo -e "  ${YELLOW}${PUBLIC_URL}/api/v1/heartbeat${NC}"
echo ""
# ══════════════════════════════════════════════════════════════
# RESULTADO FINAL
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${GREEN}══════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Setup concluído com sucesso!${NC}"
echo -e "${GREEN}══════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BLUE}Sistema de incidentes:${NC}"
echo -e "    PWA      → ${YELLOW}http://localhost${NC}"
echo -e "    API docs → ${YELLOW}http://localhost/api/docs${NC}"
echo -e "    Keycloak → ${YELLOW}http://localhost/auth${NC}   (${KC_ADMIN} / ${KC_PASS})"
echo -e "    Grafana  → ${YELLOW}http://localhost/grafana${NC} (${GRAFANA_USER:-admin} / ${GRAFANA_PASSWORD:-admin123})"
echo ""
echo -e "  ${BLUE}ITSM (instalados e configurados):${NC}"
echo -e "    Zabbix   → ${YELLOW}http://localhost/zabbix${NC}  (Admin / zabbix)"
echo -e "    GLPI     → ${YELLOW}http://localhost:8081${NC}    (glpi / glpi)"
echo ""
echo -e "  ${BLUE}Usuários de teste (Keycloak):${NC}"
echo -e "    tecnico / tecnico123"
echo -e "    gestor  / gestor123"
echo ""
echo -e "  ${BLUE}Comandos úteis:${NC}"
echo -e "    ${YELLOW}make ps${NC}        — status de todos os containers"
echo -e "    ${YELLOW}make logs${NC}      — ver todos os logs"
echo -e "    ${YELLOW}make health${NC}    — checar saúde dos containers"
echo -e "    ${YELLOW}make db${NC}        — abrir psql no banco de incidentes"
echo -e "    ${YELLOW}make down${NC}      — parar tudo"
echo -e "    ${YELLOW}make clean${NC}     — parar e apagar tudo (volumes inclusos)"
echo ""
