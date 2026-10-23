#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  CESUP Incidentes — reinstalar.sh
#  Reinstalação COMPLETA: apaga tudo e instala do zero
#  ⚠ TODOS OS DADOS SERÃO PERDIDOS
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "${GREEN}  ✔ $1${NC}"; }
info() { echo -e "${BLUE}  → $1${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $1${NC}"; }
fail() { echo -e "${RED}  ✗ $1${NC}"; exit 1; }

echo ""
echo -e "${BOLD}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║  CESUP Incidentes — Reinstalação Completa                  ║${NC}"
echo -e "${BOLD}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}  ⚠ Este script irá:${NC}"
echo -e "${YELLOW}     • Parar e remover todos os containers${NC}"
echo -e "${YELLOW}     • APAGAR todos os volumes (banco, arquivos, cache)${NC}"
echo -e "${YELLOW}     • Reconstruir todas as imagens do zero${NC}"
echo -e "${YELLOW}     • Instalar e configurar tudo novamente${NC}"
echo ""

# Confirmação
read -rp "  Confirma reinstalação completa? (s/N) " CONF
[[ "${CONF,,}" == "s" ]] || { echo "  Cancelado."; exit 0; }
echo ""

# Verificações mínimas
[ ! -f .env ] && fail ".env não encontrado — copie .env.example e preencha"
docker info &>/dev/null || fail "Docker não está rodando"

# ════════════════════════════════════════════════════════════════
# PASSO 1 — Derrubar tudo
# ════════════════════════════════════════════════════════════════
echo -e "${BLUE}[1/6] Derrubando containers e apagando volumes...${NC}"

docker compose down -v --remove-orphans 2>/dev/null || true
ok "Containers e volumes removidos"

# Remover imagens locais para forçar rebuild limpo
for img in cesup-api:latest cesup-keycloak:latest cesup-pwa-builder:latest; do
    docker rmi "$img" 2>/dev/null && info "Imagem $img removida" || true
done
ok "Imagens locais removidas"

# Limpar volumes órfãos
docker volume prune -f &>/dev/null || true

# Remover volumes nomeados explicitamente (garantia extra)
for VOL in postgres-data mysql-data valkey-data garage-data garage-meta glpi-files glpi-plugins glpi-config pwa-dist; do
    docker volume rm "cesup-sistema_${VOL}" 2>/dev/null ||     docker volume rm "cesup_${VOL}" 2>/dev/null || true
done
ok "Volumes removidos (incluindo dados do banco)"

# ════════════════════════════════════════════════════════════════
# PASSO 2 — Reconstruir imagens
# ════════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}[2/6] Reconstruindo imagens (sem cache)...${NC}"
info "Isso pode levar 5-10 minutos na primeira vez"
echo ""

docker compose build --no-cache 2>&1 | grep -E "^\[|^#|Step|Successfully built|ERROR|error" || true

ok "Imagens reconstruídas"

# ════════════════════════════════════════════════════════════════
# PASSO 3 — Subir bancos primeiro, criar banco keycloak, depois o resto
# ════════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}[3/6] Subindo bancos de dados...${NC}"

# Subir apenas os bancos primeiro
docker compose up -d postgres mysql valkey
ok "Bancos iniciados"

# Aguardar cada banco ficar healthy
for SVC in postgres mysql valkey; do
    info "Aguardando $SVC ficar healthy..."
    i=0
    while true; do
        STATUS=$(docker inspect --format='{{.State.Health.Status}}' "cesup-$SVC" 2>/dev/null || echo "starting")
        [ "$STATUS" = "healthy" ] && ok "$SVC pronto" && break
        [ "$STATUS" = "exited"  ] && fail "$SVC falhou — verifique: docker logs cesup-$SVC"
        i=$((i+5)); [ $((i % 30)) -eq 0 ] && info "$SVC ainda iniciando (${i}s)..."
        sleep 5
    done
done

# Criar banco keycloak ANTES de subir o KC
info "Criando banco keycloak..."
KC_DB=$(docker compose exec -T postgres psql -U cesup -d postgres -tAc     "SELECT 1 FROM pg_database WHERE datname='keycloak';" 2>/dev/null || echo "")
if [ "$KC_DB" = "1" ]; then
    ok "Banco keycloak já existe"
else
    docker compose exec -T postgres psql -U cesup -d postgres         -c "CREATE DATABASE keycloak WITH ENCODING='UTF8';"         -c "GRANT ALL PRIVILEGES ON DATABASE keycloak TO cesup;"         2>/dev/null && ok "Banco keycloak criado" || warn "Erro ao criar banco keycloak"
fi

# ════════════════════════════════════════════════════════════════
# PASSO 4 — Subir todos os demais containers
# ════════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}[4/6] Subindo demais containers...${NC}"

docker compose up -d
ok "Todos os containers iniciados"

# ════════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════════
# PASSO 5 — Configurar todos os serviços
# ════════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}[5/6] Executando configuração completa...${NC}"
info "O setup cuida de: Keycloak, Garage S3, GLPI, Zabbix, PWA"
echo ""

bash setup.sh

# RESUMO FINAL
# ════════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║  ✅ INSTALAÇÃO CONCLUÍDA                                    ║${NC}"
echo -e "${BOLD}${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}Serviços disponíveis:${NC}"
echo -e "  PWA          → ${BLUE}http://localhost${NC}"
echo -e "  API Swagger  → ${BLUE}http://localhost/api/docs${NC}"
echo -e "  Keycloak     → ${BLUE}http://localhost/auth${NC}        admin / admin123"
echo -e "  Grafana      → ${BLUE}http://localhost/grafana${NC}     admin / admin123"
echo -e "  Zabbix       → ${BLUE}http://localhost/zabbix${NC}      Admin / zabbix"
echo -e "  GLPI         → ${BLUE}http://localhost:8081${NC}        glpi / glpi"
echo ""
