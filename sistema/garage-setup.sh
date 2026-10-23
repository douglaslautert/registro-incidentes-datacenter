#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  CESUP Incidentes — garage-setup.sh
#  Configura o Garage S3: layout do nó, bucket "evidencias" e
#  chave "cesup-api" (salva no .env). Idempotente: pode ser
#  rodado de novo a qualquer momento — make garage-setup
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

G=(docker compose exec -T garage /garage --config /etc/garage.toml)
BUCKET=evidencias
KEY_NAME=cesup-api

# ── Container rodando ─────────────────────────────────────────
GARAGE_STATE=""
for _i in $(seq 1 24); do
    GARAGE_STATE=$(docker inspect --format='{{.State.Status}}' cesup-garage 2>/dev/null || echo "missing")
    [ "$GARAGE_STATE" = "running" ] && break
    sleep 5
done
[ "$GARAGE_STATE" = "running" ] || { warn "Garage está '$GARAGE_STATE' — docker logs cesup-garage"; exit 1; }

# ── Node ID ───────────────────────────────────────────────────
# "node id -q" imprime "<id>@<host>:<porta>"; layout assign quer só o <id>
NODE_ID=""
for _i in $(seq 1 20); do
    NODE_ID=$("${G[@]}" node id -q 2>/dev/null | head -1 | cut -d@ -f1 | tr -d '[:space:]' || true)
    [ -n "$NODE_ID" ] && break
    sleep 3
done
[ -n "$NODE_ID" ] || { warn "Não foi possível obter o node ID do Garage"; exit 1; }
info "Node ID: ${NODE_ID:0:16}..."

# ── Layout (necessário para o cluster ter quorum) ─────────────
# A tabela do layout atual mostra os 16 primeiros caracteres do ID
if "${G[@]}" layout show 2>/dev/null \
    | sed -n '/CURRENT CLUSTER LAYOUT/,/STAGED/p' | grep -q "${NODE_ID:0:16}"; then
    ok "Layout já aplicado"
else
    OUT=$("${G[@]}" layout assign -z dc1 -c 1G "$NODE_ID" 2>&1) \
        || { warn "layout assign falhou: $OUT"; exit 1; }
    VER=$("${G[@]}" layout show 2>/dev/null \
        | grep -oE 'Current cluster layout version: [0-9]+' | grep -oE '[0-9]+$' || echo 0)
    OUT=$("${G[@]}" layout apply --version $((VER + 1)) 2>&1) \
        || { warn "layout apply falhou: $OUT"; exit 1; }
    ok "Layout aplicado (versão $((VER + 1)))"
fi

# ── Bucket ────────────────────────────────────────────────────
if "${G[@]}" bucket info "$BUCKET" >/dev/null 2>&1; then
    ok "Bucket '$BUCKET' já existe"
else
    # Logo após o layout o cluster pode levar alguns segundos para aceitar escritas
    CRIADO=0
    for _i in $(seq 1 10); do
        if OUT=$("${G[@]}" bucket create "$BUCKET" 2>&1); then CRIADO=1; break; fi
        sleep 3
    done
    [ "$CRIADO" = "1" ] || { warn "Erro ao criar bucket '$BUCKET': $OUT"; exit 1; }
    ok "Bucket '$BUCKET' criado"
fi

# ── Chave de acesso ───────────────────────────────────────────
KEY_OUTPUT=""
if "${G[@]}" key info "$KEY_NAME" >/dev/null 2>&1; then
    if [ -z "${GARAGE_ACCESS_KEY:-}" ] || [ -z "${GARAGE_SECRET_KEY:-}" ]; then
        KEY_OUTPUT=$("${G[@]}" key info "$KEY_NAME" --show-secret 2>&1) \
            || { warn "Não foi possível ler a chave '$KEY_NAME': $KEY_OUTPUT"; exit 1; }
    else
        ok "Chave '$KEY_NAME' já configurada no .env"
    fi
else
    KEY_OUTPUT=$("${G[@]}" key create "$KEY_NAME" 2>&1) \
        || { warn "Erro ao criar a chave '$KEY_NAME': $KEY_OUTPUT"; exit 1; }
    ok "Chave '$KEY_NAME' criada"
fi

OUT=$("${G[@]}" bucket allow --read --write --owner "$BUCKET" --key "$KEY_NAME" 2>&1) \
    || { warn "Erro ao liberar o bucket para a chave: $OUT"; exit 1; }
ok "Chave '$KEY_NAME' com acesso ao bucket '$BUCKET'"

if [ -n "$KEY_OUTPUT" ]; then
    ACCESS_KEY=$(echo "$KEY_OUTPUT" | grep -i "key id" | awk '{print $NF}' | tr -d '\r' || true)
    SECRET_KEY_S3=$(echo "$KEY_OUTPUT" | grep -i "secret key" | awk '{print $NF}' | tr -d '\r' || true)
    if [ -z "$ACCESS_KEY" ] || [ -z "$SECRET_KEY_S3" ]; then
        warn "Não foi possível ler Key ID/Secret da saída do Garage:"
        echo "$KEY_OUTPUT"
        exit 1
    fi
    set_env GARAGE_ACCESS_KEY "$ACCESS_KEY"
    set_env GARAGE_SECRET_KEY "$SECRET_KEY_S3"
    ok "Chave S3 salva no .env: $ACCESS_KEY"
    # restart não relê o .env — é preciso recriar os containers
    docker compose up -d api worker beat >/dev/null 2>&1 \
        && ok "API, worker e beat recriados com as chaves S3" \
        || warn "Recrie os containers: docker compose up -d api worker beat"
    # Container recriado ganha IP novo — o nginx precisa resolver o upstream de novo
    docker compose exec -T nginx nginx -s reload >/dev/null 2>&1 || true
fi
