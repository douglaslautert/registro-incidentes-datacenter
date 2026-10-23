#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  CESUP Incidentes — glpi-setup.sh
#  Instala o banco do GLPI via bin/console, ativa a API REST e cria
#  o API client "CESUP Incidentes" (App-Token salvo no .env).
#  Idempotente: pode ser rodado de novo a qualquer momento — make glpi-setup
# ═══════════════════════════════════════════════════════════════
set -euo pipefail
cd "$(dirname "$0")"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✔ $1${NC}"; }
info() { echo -e "${BLUE}  → $1${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $1${NC}"; }

# Atualiza (ou acrescenta) CHAVE=VALOR no .env
set_env() {
    if grep -q "^$1=" .env; then
        sed -i "s|^$1=.*|$1=$2|" .env
    else
        echo "$1=$2" >> .env
    fi
}

[ -f .env ] || { warn ".env não encontrado"; exit 1; }
source .env
command -v python3 >/dev/null || { warn "python3 não encontrado — instale-o no servidor"; exit 1; }

GLPI_DIR=/var/www/html/glpi
glpi_mysql() { docker compose exec -T mysql mysql -u glpi -p"${MYSQL_GLPI_PASSWORD}" glpi "$@"; }
glpi_tables() {
    glpi_mysql -sse "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='glpi';" 2>/dev/null \
        | tr -d '[:space:]' | grep -E '^[0-9]+$' || echo "0"
}

# ── Usuário MySQL glpi alinhado com a senha do .env ───────────
docker compose exec -T mysql mysql -u root -p"${MYSQL_ROOT_PASSWORD}" -e "
CREATE DATABASE IF NOT EXISTS glpi CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'glpi'@'%' IDENTIFIED BY '${MYSQL_GLPI_PASSWORD}';
ALTER USER 'glpi'@'%' IDENTIFIED BY '${MYSQL_GLPI_PASSWORD}';
GRANT ALL PRIVILEGES ON glpi.* TO 'glpi'@'%';
FLUSH PRIVILEGES;" 2>/dev/null || warn "Não foi possível ajustar o usuário MySQL 'glpi'"

# ── Código do GLPI (a imagem diouxx baixa o tarball no 1º start) ──
info "Aguardando código do GLPI (bin/console)..."
_gwait=0
while ! docker compose exec -T glpi test -f "$GLPI_DIR/bin/console" 2>/dev/null; do
    STATE=$(docker inspect --format='{{.State.Status}}' cesup-glpi 2>/dev/null || echo "missing")
    case "$STATE" in
        exited|dead|missing) warn "Container GLPI está '$STATE' — docker logs cesup-glpi"; exit 1 ;;
    esac
    [ $_gwait -ge 600 ] && { warn "bin/console não apareceu em 600s — docker logs cesup-glpi"; exit 1; }
    _gwait=$((_gwait + 10))
    [ $((_gwait % 60)) -eq 0 ] && info "Ainda sem bin/console (${_gwait}/600s)..."
    sleep 10
done
ok "bin/console disponível"

# ── Banco do GLPI ─────────────────────────────────────────────
GLPI_TABLES=$(glpi_tables)
if [ "$GLPI_TABLES" -gt "10" ]; then
    ok "GLPI já instalado ($GLPI_TABLES tabelas)"
else
    info "Instalando banco do GLPI (pode levar alguns minutos)..."
    # O console roda como www-data (usuário do Apache): assim config_db.php e
    # glpicrypt.key ficam com o dono certo. Rodar como root exigiria
    # --allow-superuser, opção que o database:install do GLPI 10.0.x não aceita.
    docker compose exec -T glpi chown -R www-data:www-data "$GLPI_DIR/config" "$GLPI_DIR/files" 2>/dev/null || true

    OUT=""
    # database:install é o nome no GLPI 10 (db:install é alias); glpi:database:install no 9.5
    for GLPI_CMD in database:install db:install glpi:database:install; do
        info "php bin/console $GLPI_CMD"
        OUT=$(docker compose exec -T -u www-data glpi php "$GLPI_DIR/bin/console" "$GLPI_CMD" \
            --db-host=mysql --db-port=3306 --db-name=glpi \
            --db-user=glpi --db-password="${MYSQL_GLPI_PASSWORD}" \
            --default-language=pt_BR --reconfigure --force --no-interaction 2>&1) || true
        # Comando inexistente nesta versão → tentar o próximo nome
        echo "$OUT" | grep -qiE 'is not defined|There are no commands' && continue
        break
    done

    GLPI_TABLES=$(glpi_tables)
    if [ "$GLPI_TABLES" -gt "10" ]; then
        ok "GLPI instalado ($GLPI_TABLES tabelas)"
        # Instalador web não é mais necessário
        docker compose exec -T glpi rm -f "$GLPI_DIR/install/install.php" 2>/dev/null || true
    else
        warn "GLPI não instalou. Saída do console:"
        echo "$OUT" | tail -15 | sed 's/^/      /'
        warn "Alternativa: instalação web em http://localhost:8081"
        warn "  host=mysql  usuário=glpi  senha=${MYSQL_GLPI_PASSWORD}  banco=glpi"
        exit 1
    fi
fi

# ── API REST ──────────────────────────────────────────────────
glpi_mysql -e "UPDATE glpi_configs SET value='1' WHERE name IN ('enable_api','enable_api_login_credentials');" 2>/dev/null \
    && ok "API REST do GLPI ativada" \
    || warn "Não foi possível ativar a API REST do GLPI"

# ── API client e App-Token no .env ────────────────────────────
GLPI_APP_TOKEN="${GLPI_APP_TOKEN:-}"
[ -z "$GLPI_APP_TOKEN" ] && GLPI_APP_TOKEN=$(python3 -c "import secrets; print(secrets.token_hex(20))")
if glpi_mysql -e "UPDATE glpi_apiclients SET app_token='${GLPI_APP_TOKEN}', is_active=1 WHERE name='CESUP Incidentes';
        INSERT INTO glpi_apiclients (name, is_active, app_token, app_token_date, dolog_method)
        SELECT 'CESUP Incidentes', 1, '${GLPI_APP_TOKEN}', NOW(), 0 FROM DUAL
        WHERE NOT EXISTS (SELECT 1 FROM glpi_apiclients WHERE name='CESUP Incidentes');" 2>/dev/null; then
    set_env GLPI_APP_TOKEN "$GLPI_APP_TOKEN"
    ok "App-Token do GLPI salvo no .env"
    info "User-Token: gere em GLPI → Preferências → Chaves de acesso remoto e rode: make glpi-token"
else
    warn "Não foi possível criar o API client do GLPI"
    exit 1
fi
