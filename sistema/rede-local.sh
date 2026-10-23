#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  CESUP Incidentes — rede-local.sh
#  Libera o acesso pela rede local: troca localhost pelo IP do
#  servidor (.env), gera certificado HTTPS autoassinado, recria os
#  serviços afetados e libera o IP nos clients do Keycloak.
#
#  Uso:  bash rede-local.sh [IP] [--sem-https]
#        make rede-local [ip=192.168.0.10] [args=--sem-https]
#  Sem IP, usa o IP principal do servidor. Idempotente.
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

HTTPS=1
IP=""
for arg in "$@"; do
    case "$arg" in
        --sem-https) HTTPS=0 ;;
        -h|--help)   sed -n '2,11p' "$0"; exit 0 ;;
        *)           IP="$arg" ;;
    esac
done

# ── Endereço do servidor ──────────────────────────────────────
if [ -z "$IP" ]; then
    IP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i < NF; i++) if ($i == "src") { print $(i + 1); exit }}' || true)
    [ -z "$IP" ] && IP=$(hostname -I 2>/dev/null | awk '{print $1}' || true)
fi
[ -n "$IP" ] || { warn "Não foi possível detectar o IP — informe: make rede-local ip=192.168.0.10"; exit 1; }
if echo "$IP" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'; then
    SAN="IP:$IP"
else
    SAN="DNS:$IP"   # nome DNS da rede local (ex.: incidentes.cesup.local)
fi
info "Endereço na rede local: $IP"

# ── Certificado HTTPS (câmera e microfone do PWA exigem HTTPS) ──
if [ "$HTTPS" = "1" ]; then
    command -v openssl >/dev/null || { warn "openssl não encontrado — instale (apt install openssl) ou use --sem-https"; exit 1; }
    mkdir -p nginx/certs
    if [ -f nginx/certs/cesup.crt ] && openssl x509 -in nginx/certs/cesup.crt -noout -text 2>/dev/null \
        | grep -qE "(IP Address|DNS):$IP(,|$)"; then
        ok "Certificado existente já cobre $IP"
    else
        # MSYS_NO_PATHCONV: no Git Bash/Windows, impede que "/CN=..." vire caminho
        MSYS_NO_PATHCONV=1 openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
            -keyout nginx/certs/cesup.key -out nginx/certs/cesup.crt \
            -subj "/CN=$IP/O=CESUP Incidentes" \
            -addext "subjectAltName=$SAN,DNS:localhost,IP:127.0.0.1" \
            -addext "basicConstraints=critical,CA:FALSE" 2>/dev/null \
            || { warn "Falha ao gerar o certificado"; exit 1; }
        ok "Certificado autoassinado gerado (nginx/certs/cesup.crt, válido por 825 dias)"
    fi
    cp nginx/ssl.conf.template nginx/conf.d/cesup-ssl.conf
    SCHEME=https; WS=wss
else
    rm -f nginx/conf.d/cesup-ssl.conf
    SCHEME=http; WS=ws
    warn "Sem HTTPS: leitura de QR Code, foto pela câmera e gravação de voz não funcionam fora do servidor"
fi

set_env PUBLIC_URL    "$SCHEME://$IP"
set_env PUBLIC_WS_URL "$WS://$IP"
set_env KC_HOSTNAME   "$IP"
PUBLIC_URL="$SCHEME://$IP"
ok ".env atualizado: PUBLIC_URL=$PUBLIC_URL"

# ── Recriar os serviços que usam o endereço público ───────────
info "Reconstruindo o PWA..."
docker compose build pwa-builder >/dev/null \
    && docker compose up -d --force-recreate pwa-builder >/dev/null \
    && ok "PWA reconstruído" \
    || warn "Falha ao reconstruir o PWA — docker compose logs pwa-builder"

info "Recriando Keycloak, Grafana, API e nginx com o novo endereço..."
docker compose up -d keycloak grafana api worker beat nginx >/dev/null
if docker compose exec -T nginx nginx -t >/dev/null 2>&1; then
    docker compose exec -T nginx nginx -s reload >/dev/null 2>&1 || true
    ok "nginx recarregado"
else
    warn "Configuração do nginx inválida:"
    docker compose exec -T nginx nginx -t 2>&1 | sed 's/^/      /' || true
    exit 1
fi

# ── Keycloak: aceitar redirecionamentos para o novo endereço ──
info "Atualizando clients do Keycloak (aguarda o Keycloak reiniciar)..."
KC_URL="http://localhost/auth" PUBLIC_URL="$PUBLIC_URL" \
KC_ADMIN_USER="${KC_ADMIN_USER:-admin}" KC_ADMIN_PASSWORD="${KC_ADMIN_PASSWORD:-admin123}" \
    python3 keycloak/redirects.py | sed 's/^/      /' \
    && ok "Keycloak atualizado" \
    || warn "Keycloak não atualizado — rode de novo: make rede-local"

# ── Resumo ────────────────────────────────────────────────────
echo ""
echo -e "  ${BLUE}Acesse de qualquer computador da rede:${NC}"
echo -e "    PWA      → ${YELLOW}$PUBLIC_URL${NC}"
echo -e "    API docs → ${YELLOW}$PUBLIC_URL/api/docs${NC}"
echo -e "    Keycloak → ${YELLOW}$PUBLIC_URL/auth${NC}"
echo -e "    Grafana  → ${YELLOW}$PUBLIC_URL/grafana${NC}"
echo -e "    Zabbix   → ${YELLOW}$PUBLIC_URL/zabbix/${NC}"
echo -e "    GLPI     → ${YELLOW}http://$IP:8081${NC}"
echo ""
if [ "$HTTPS" = "1" ]; then
    echo -e "  O certificado é autoassinado: no 1º acesso o navegador mostra um aviso."
    echo -e "  Aceite-o, ou instale ${YELLOW}nginx/certs/cesup.crt${NC} como confiável nos celulares/PCs."
fi
echo -e "  Se o servidor tiver firewall, libere as portas 80, 443 e 8081 para a rede local."
