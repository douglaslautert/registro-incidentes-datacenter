#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  CESUP Incidentes — zabbix-setup.sh
#  Configura o Zabbix via API: usuário de API, webhook para a API
#  de incidentes, ação de alerta e host Docker. Idempotente: pode
#  ser rodado de novo a qualquer momento — make zabbix-setup
# ═══════════════════════════════════════════════════════════════
set -euo pipefail
cd "$(dirname "$0")"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✔ $1${NC}"; }
info() { echo -e "${BLUE}  → $1${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $1${NC}"; }

[ -f .env ] || { warn ".env não encontrado"; exit 1; }
source .env
command -v python3 >/dev/null || { warn "python3 não encontrado — instale-o no servidor"; exit 1; }

ZBX_API="http://localhost/zabbix/api_jsonrpc.php"
ZBX_USER="${ZABBIX_USER:-Admin}"
ZBX_PASS="${ZABBIX_PASSWORD:-zabbix}"
ZBX_API_PASS="${ZABBIX_API_PASSWORD:-CesupApi-2026}"
ZBX_TOKEN=""
ZBX_LAST="$(mktemp)"

# Chamada JSON-RPC: zbx_call <método> <params JSON> — imprime a resposta (nunca falha)
zbx_call() {
    local auth=()
    [ -n "$ZBX_TOKEN" ] && auth=(-H "Authorization: Bearer $ZBX_TOKEN")
    curl -s --max-time 15 -X POST "$ZBX_API" \
        -H "Content-Type: application/json-rpc" ${auth[@]+"${auth[@]}"} \
        -d "{\"jsonrpc\":\"2.0\",\"method\":\"$1\",\"params\":$2,\"id\":1}" 2>/dev/null \
        || echo '{"error":{"data":"sem resposta da API"}}'
}
# Avalia expressão Python sobre a resposta (r) lida do stdin
zbx_py() { python3 -c "import sys,json; r=json.load(sys.stdin); print($1)" 2>/dev/null || echo ""; }
# zbx_create <descrição> <método> <params JSON> — informa sucesso ou o erro real da API
zbx_create() {
    local resp err
    resp=$(zbx_call "$2" "$3")
    echo "$resp" > "$ZBX_LAST"
    if echo "$resp" | zbx_py "'result' in r" | grep -q True; then
        ok "$1"
    else
        err=$(echo "$resp" | zbx_py "r['error'].get('data') or r['error'].get('message')")
        warn "$1 — falhou: ${err:-resposta inválida}"
    fi
}

# Mostra por que a API não responde (nginx, containers, frontend)
zbx_diagnostico() {
    local req='{"jsonrpc":"2.0","method":"apiinfo.version","params":{},"id":1}' code resp
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 -X POST "$ZBX_API" \
        -H "Content-Type: application/json-rpc" -d "$req" 2>/dev/null || true)
    resp=$(curl -s --max-time 10 -X POST "$ZBX_API" \
        -H "Content-Type: application/json-rpc" -d "$req" 2>/dev/null | head -c 300 || true)
    warn "Via nginx ($ZBX_API): HTTP ${code:-000}"
    [ -n "$resp" ] && echo "      resposta: $resp"
    for c in zabbix-web zabbix-server nginx; do
        echo "      cesup-$c: $(docker inspect --format='{{.State.Status}} {{if .State.Health}}({{.State.Health.Status}}){{end}}' "cesup-$c" 2>/dev/null || echo 'não existe')"
    done
    resp=$(docker compose exec -T zabbix-web curl -s --max-time 10 -X POST http://localhost:8080/api_jsonrpc.php \
        -H "Content-Type: application/json-rpc" -d "$req" 2>&1 | head -c 300 || true)
    echo "      direto no zabbix-web (sem nginx): ${resp:-sem resposta}"
    info "Logs: make zabbix-logs   |   docker logs cesup-nginx --tail 20"
}

# O frontend demora no 1º start; nginx pode estar com IP antigo de um container recriado
info "Aguardando a API do Zabbix..."
ZBX_VER=""
for i in $(seq 1 30); do
    ZBX_VER=$(zbx_call apiinfo.version '{}' | zbx_py "r.get('result','')")
    [ -n "$ZBX_VER" ] && break
    if [ $((i % 3)) -eq 0 ]; then
        info "API do Zabbix ainda não responde ($((i * 10))/300s)..."
        docker compose exec -T nginx nginx -s reload >/dev/null 2>&1 || true
    fi
    sleep 10
done
if [ -z "$ZBX_VER" ]; then
    warn "API do Zabbix não respondeu em 300s"
    zbx_diagnostico
    exit 1
fi
ok "API do Zabbix respondendo (versão $ZBX_VER)"

info "Autenticando no Zabbix como $ZBX_USER..."
RESP=$(zbx_call user.login "{\"username\":\"$ZBX_USER\",\"password\":\"$ZBX_PASS\"}")
ZBX_TOKEN=$(echo "$RESP" | zbx_py "r.get('result','')")
if [ -z "$ZBX_TOKEN" ]; then
    ERR=$(echo "$RESP" | zbx_py "r['error'].get('data') or r['error'].get('message')")
    warn "Login no Zabbix falhou: ${ERR:-resposta inválida}"
    warn "Confira ZABBIX_USER/ZABBIX_PASSWORD no .env (padrão do Zabbix: Admin / zabbix)"
    exit 1
fi
ok "Autenticado no Zabbix (token: ${ZBX_TOKEN:0:8}...)"

# Usuário de API (a política padrão do Zabbix 7 exige senha com 8+ caracteres)
API_USER_EXISTS=$(zbx_call user.get '{"filter":{"username":"incidentes_api"}}' | zbx_py "len(r.get('result',[]))")
if [ "${API_USER_EXISTS:-0}" -gt "0" ]; then
    warn "Usuário 'incidentes_api' já existe"
else
    zbx_create "Usuário 'incidentes_api' criado" user.create \
        "{\"username\":\"incidentes_api\",\"passwd\":\"$ZBX_API_PASS\",\"roleid\":\"1\",\"usrgrps\":[{\"usrgrpid\":\"7\"}]}"
fi

# Webhook → API de incidentes. As macros só são expandidas nos parâmetros,
# que o script recebe como JSON na variável "value".
MT_ID=$(zbx_call mediatype.get '{"filter":{"name":"CESUP Incidentes"},"output":["mediatypeid"]}' | zbx_py "r['result'][0]['mediatypeid'] if r.get('result') else ''")
if [ -n "$MT_ID" ]; then
    warn "Webhook 'CESUP Incidentes' já existe"
else
    MT_PARAMS=$(python3 zabbix/webhook_params.py)
    zbx_create "Webhook 'CESUP Incidentes' criado" mediatype.create "$MT_PARAMS"
    MT_ID=$(zbx_py "r['result']['mediatypeids'][0] if 'result' in r else ''" < "$ZBX_LAST")
fi

# Ação: problemas de severidade >= Warning disparam o webhook (via mídia do Admin)
ACTION_EXISTS=$(zbx_call action.get '{"filter":{"name":"CESUP Incidentes"}}' | zbx_py "len(r.get('result',[]))")
if [ "${ACTION_EXISTS:-0}" -gt "0" ]; then
    warn "Ação 'CESUP Incidentes' já existe"
elif [ -z "$MT_ID" ]; then
    warn "Sem webhook — ação 'CESUP Incidentes' não criada"
else
    ADMIN_ID=$(zbx_call user.get "{\"filter\":{\"username\":\"$ZBX_USER\"},\"output\":[\"userid\"]}" | zbx_py "r['result'][0]['userid'] if r.get('result') else ''")
    zbx_create "Mídia do webhook associada ao usuário $ZBX_USER" user.update \
        "{\"userid\":\"$ADMIN_ID\",\"medias\":[{\"mediatypeid\":\"$MT_ID\",\"sendto\":\"cesup\",\"active\":0,\"severity\":63,\"period\":\"1-7,00:00-24:00\"}]}"
    OP="{\"operationtype\":0,\"opmessage\":{\"default_msg\":1,\"mediatypeid\":\"$MT_ID\"},\"opmessage_usr\":[{\"userid\":\"$ADMIN_ID\"}]}"
    zbx_create "Ação 'CESUP Incidentes' criada" action.create \
        "{\"name\":\"CESUP Incidentes\",\"eventsource\":0,\"status\":0,\"esc_period\":\"1h\",\"filter\":{\"evaltype\":0,\"conditions\":[{\"conditiontype\":4,\"operator\":5,\"value\":\"2\"}]},\"operations\":[$OP],\"recovery_operations\":[$OP]}"
fi

# Host do Docker — o agente é alcançado pelo nome DNS do container (useip=0)
HOST_EXISTS=$(zbx_call host.get '{"filter":{"host":"cesup-docker-host"}}' | zbx_py "len(r.get('result',[]))")
if [ "${HOST_EXISTS:-0}" -gt "0" ]; then
    warn "Host 'cesup-docker-host' já existe"
else
    GROUP_ID=$(zbx_call hostgroup.get '{"filter":{"name":"Linux servers"}}' | zbx_py "r['result'][0]['groupid'] if r.get('result') else '2'")
    TPL_ID=$(zbx_call template.get '{"filter":{"host":"Linux by Zabbix agent"},"output":["templateid"]}' | zbx_py "r['result'][0]['templateid'] if r.get('result') else ''")
    TPL_JSON=""
    [ -n "$TPL_ID" ] && TPL_JSON=",\"templates\":[{\"templateid\":\"$TPL_ID\"}]"
    zbx_create "Host Docker registrado no Zabbix" host.create \
        "{\"host\":\"cesup-docker-host\",\"name\":\"CESUP — Servidor Docker\",\"groups\":[{\"groupid\":\"${GROUP_ID:-2}\"}]$TPL_JSON,\"interfaces\":[{\"type\":1,\"main\":1,\"useip\":0,\"ip\":\"\",\"dns\":\"zabbix-agent\",\"port\":\"10050\"}]}"
fi
rm -f "$ZBX_LAST"
