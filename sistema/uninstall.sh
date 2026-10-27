#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  CESUP Incidentes — uninstall.sh
#  Remove o que a instalação criou no Docker: containers, rede,
#  volumes (dados) e as imagens construídas para o sistema.
#
#  Uso:  bash uninstall.sh [--manter-dados] [--sim]
#        make uninstall [args="--manter-dados --sim"]
#    --manter-dados  preserva os volumes (bancos, arquivos, S3)
#    --sim           não pede confirmação
#
#  Mexe só no projeto "cesup": containers e volumes de outros
#  projetos Docker da máquina não são tocados. O .env, o
#  certificado (nginx/certs) e a configuração HTTPS ficam no disco.
#  Para reinstalar: make uninstall && make install
# ═══════════════════════════════════════════════════════════════
set -euo pipefail
cd "$(dirname "$0")"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✔ $1${NC}"; }
info() { echo -e "${BLUE}  → $1${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $1${NC}"; }
fail() { echo -e "${RED}  ✗ $1${NC}"; exit 1; }

MANTER_DADOS=0
SEM_PERGUNTA=0
for arg in "$@"; do
    case "$arg" in
        --manter-dados) MANTER_DADOS=1 ;;
        --sim)          SEM_PERGUNTA=1 ;;
        -h|--help)      sed -n '2,16p' "$0"; exit 0 ;;
        *)              fail "Opção desconhecida: $arg (use --help)" ;;
    esac
done

docker info &>/dev/null || fail "Docker não está rodando."

# Imagens construídas pelo projeto (as públicas, como postgres e nginx, ficam no cache do Docker)
IMAGENS=$(docker compose config --images 2>/dev/null | grep -E '^cesup' | sort -u || true)
VOLUMES=$(docker volume ls -q --filter label=com.docker.compose.project=cesup)

echo ""
echo -e "${BLUE}══════════════════════════════════════════════${NC}"
echo -e "${BLUE}  CESUP Incidentes — Desinstalação${NC}"
echo -e "${BLUE}══════════════════════════════════════════════${NC}"
echo ""
echo "  Será removido:"
echo "    • containers e rede do projeto cesup"
echo "    • imagens: $(echo $IMAGENS | sed 's/ /, /g')"
if [ "$MANTER_DADOS" = "1" ]; then
    echo "    • volumes: mantidos (--manter-dados)"
else
    echo -e "    • ${RED}volumes com TODOS OS DADOS${NC}: $(echo $VOLUMES | wc -w) (bancos, chamados, evidências, Zabbix, GLPI)"
fi
echo ""

if [ "$SEM_PERGUNTA" = "0" ]; then
    read -rp "  Confirma a desinstalação? (s/N) " CONF
    [[ "${CONF,,}" == "s" ]] || { echo "  Cancelado. Nada foi removido."; exit 0; }
    echo ""
fi

info "Parando e removendo containers..."
if [ "$MANTER_DADOS" = "1" ]; then
    docker compose down --remove-orphans
else
    docker compose down --volumes --remove-orphans
fi
ok "Containers e rede removidos"

for img in $IMAGENS; do
    docker image rm "$img" >/dev/null 2>&1 && ok "Imagem $img removida" || info "Imagem $img já não existia"
done

if [ "$MANTER_DADOS" = "0" ]; then
    RESTANTES=$(docker volume ls -q --filter label=com.docker.compose.project=cesup)
    [ -z "$RESTANTES" ] && ok "Volumes removidos" || warn "Volumes ainda em uso: $RESTANTES"
fi

echo ""
ok "Desinstalação concluída"
echo ""
echo "  Ficaram no disco (apague à mão se quiser):"
echo "    • .env — senhas e endereço de acesso"
[ -d nginx/certs ] && echo "    • nginx/certs/ e nginx/conf.d/cesup-ssl.conf — HTTPS da rede local"
echo ""
echo -e "  Para instalar de novo: ${YELLOW}make install${NC}"
echo ""
