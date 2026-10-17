#!/usr/bin/env python3
"""
Cria o Media Type GLPI no Zabbix via API JSON-RPC.

Uso:
  export ZABBIX_URL=https://zabbix.suarede.intra/zabbix
  export ZABBIX_USER=Admin
  export ZABBIX_PASS=sua_senha
  export GLPI_API_URL=https://glpi.suarede.intra/apirest.php
  export GLPI_SVC_USER=zabbix-api
  export GLPI_SVC_PASS=sua_senha_servico
  export GLPI_APP_TOKEN=seu_app_token
  python3 setup_zabbix_mediatype.py

Dependência: pip install requests
"""
import requests, json, pathlib, os, sys

ZABBIX_URL  = os.environ['ZABBIX_URL']
ZABBIX_USER = os.environ['ZABBIX_USER']
ZABBIX_PASS = os.environ['ZABBIX_PASS']
GLPI_URL    = os.environ['GLPI_API_URL']
GLPI_USER   = os.environ['GLPI_SVC_USER']
GLPI_PASS   = os.environ['GLPI_SVC_PASS']
GLPI_TOKEN  = os.environ['GLPI_APP_TOKEN']

# Carrega o script JS do caminho relativo
SCRIPT_PATH = pathlib.Path(__file__).parent.parent / 'ansible/roles/zabbix/files/glpi_webhook.js'
JS_SCRIPT = SCRIPT_PATH.read_text()

def zapi(method, params, token=None):
    payload = {'jsonrpc': '2.0', 'method': method, 'params': params, 'id': 1}
    hdrs = {'Content-Type': 'application/json'}
    if token:
        hdrs['Authorization'] = 'Bearer ' + token
    r = requests.post(ZABBIX_URL + '/api_jsonrpc.php',
                      json=payload, headers=hdrs, verify=False)
    data = r.json()
    if 'error' in data:
        sys.exit(f"Zabbix API erro: {data['error']}")
    return data['result']

# Autenticar
token = zapi('user.login', {'username': ZABBIX_USER, 'password': ZABBIX_PASS})
print(f"✅ Autenticado no Zabbix")

# Criar Media Type
mt_id = zapi('mediatype.create', {
    'name':         'GLPI Webhook',
    'type':         19,   # 19 = Webhook
    'script':       JS_SCRIPT,
    'timeout':      '30s',
    'process_tags': 1,
    'parameters': [
        {'name': 'glpi_url',        'value': GLPI_URL},
        {'name': 'glpi_user',       'value': GLPI_USER},
        {'name': 'glpi_password',   'value': GLPI_PASS},
        {'name': 'app_token',       'value': GLPI_TOKEN},
        {'name': 'event_id',        'value': '{EVENT.ID}'},
        {'name': 'event_value',     'value': '{EVENT.VALUE}'},
        {'name': 'host_name',       'value': '{HOST.NAME}'},
        {'name': 'trigger_name',    'value': '{TRIGGER.NAME}'},
        {'name': 'trigger_sev',     'value': '{TRIGGER.NSEVERITY}'},
        {'name': 'event_date',      'value': '{EVENT.DATE}'},
        {'name': 'event_time',      'value': '{EVENT.TIME}'},
        {'name': 'glpi_ticket_id',  'value': '{EVENT.TAGS.__glpi_ticket_id}'},
    ]
}, token)

print(f"✅ Media Type 'GLPI Webhook' criado — ID: {mt_id['mediatypeids'][0]}")
print(f"   Verifique em: Zabbix → Administration → Media types → GLPI Webhook")
zapi('user.logout', [], token)
