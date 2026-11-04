"""Gera os parâmetros JSON do mediatype.create do webhook CESUP (usado pelo zabbix-setup.sh)."""
import json, os

# O Zabbix entrega os parâmetros (já com as macros expandidas) como JSON em `value`
SCRIPT = r"""var p = JSON.parse(value);
var req = new HttpRequest();
req.addHeader('Content-Type: application/json');
if (p.TOKEN) { req.addHeader('X-Token-Servico: ' + p.TOKEN); }
var body = JSON.stringify({
    eventid: p.eventid, host: p.host, trigger: p.trigger, severity: p.severity,
    status: (p.status === 'RESOLVED' ? 'RECOVERY' : p.status),
    item: p.item, lastvalue: p.lastvalue
});
var resp = req.post(p.URL, body);
if (req.getStatus() < 200 || req.getStatus() >= 300) {
    throw 'HTTP ' + req.getStatus() + ': ' + resp;
}
return 'OK';"""

PARAMETERS = [
    {"name": "URL",       "value": "http://api:8000/api/v1/webhook/zabbix"},
    # Token de serviço da API (TOKEN_SERVICO do .env); vazio = sem cabeçalho
    {"name": "TOKEN",     "value": os.environ.get("TOKEN_SERVICO", "")},
    {"name": "eventid",   "value": "{EVENT.ID}"},
    # Nome técnico do host (não o visível): é ele que casa com o ativo_id do inventário
    {"name": "host",      "value": "{HOST.HOST}"},
    {"name": "trigger",   "value": "{EVENT.NAME}"},
    {"name": "severity",  "value": "{EVENT.SEVERITY}"},
    {"name": "status",    "value": "{EVENT.STATUS}"},
    {"name": "item",      "value": "{ITEM.NAME}"},
    {"name": "lastvalue", "value": "{ITEM.LASTVALUE}"},
]

MESSAGE_TEMPLATES = [
    {"eventsource": 0, "recovery": 0, "subject": "Problema: {EVENT.NAME}",  "message": "{HOST.NAME}: {EVENT.NAME}"},
    {"eventsource": 0, "recovery": 1, "subject": "Resolvido: {EVENT.NAME}", "message": "{HOST.NAME}: {EVENT.NAME}"},
]

print(json.dumps({
    "name": "CESUP Incidentes",
    "type": 4,
    "status": 0,                 # habilitada: sem isso o Zabbix 7 cria a mídia desabilitada
    "timeout": "10s",
    "parameters": PARAMETERS,
    "script": SCRIPT,
    "message_templates": MESSAGE_TEMPLATES,
}))
