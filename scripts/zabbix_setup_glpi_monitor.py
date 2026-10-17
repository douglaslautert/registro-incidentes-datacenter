#!/usr/bin/env python3
"""
Cria host 'VM-GLPI' no Zabbix com web scenario e trigger
para monitorar a disponibilidade da API REST do GLPI.

Uso:
  export ZABBIX_URL=https://zabbix.suarede.intra/zabbix
  export ZABBIX_API_TOKEN=seu_token_api
  export GLPI_API_URL=https://glpi.suarede.intra/apirest.php
  python3 zabbix_setup_glpi_monitor.py
"""
import requests, os, sys

ZABBIX_URL = os.environ['ZABBIX_URL']
TOKEN      = os.environ['ZABBIX_API_TOKEN']
GLPI_URL   = os.environ['GLPI_API_URL']

def zapi(method, params):
    r = requests.post(ZABBIX_URL + '/api_jsonrpc.php',
        json={'jsonrpc': '2.0', 'method': method, 'params': params, 'id': 1},
        headers={
            'Authorization': 'Bearer ' + TOKEN,
            'Content-Type': 'application/json'
        }, verify=False)
    result = r.json()
    if 'error' in result:
        sys.exit(f"Erro Zabbix API: {result['error']}")
    return result['result']

print("=== Configurando monitoramento da VM-GLPI ===")

# 1. Obter ID do grupo 'Linux servers'
groups = zapi('hostgroup.get', {'filter': {'name': ['Linux servers']}})
if not groups:
    sys.exit("Grupo 'Linux servers' não encontrado. Crie-o no Zabbix primeiro.")
hostgroup_id = groups[0]['groupid']

# 2. Criar host VM-GLPI
host = zapi('host.create', {
    'host': 'VM-GLPI',
    'name': 'VM-GLPI (192.168.10.200)',
    'groups': [{'groupid': hostgroup_id}],
    'interfaces': [{
        'type':   1,   # 1 = Agent
        'main':   1,
        'useip':  1,
        'ip':     '192.168.10.200',
        'dns':    '',
        'port':   '10050'
    }]
})
host_id = host['hostids'][0]
print(f"✅ Host VM-GLPI criado — ID: {host_id}")

# 3. Web scenario: verifica API a cada 60s
zapi('httptest.create', {
    'name':    'GLPI API Health',
    'hostid':  host_id,
    'delay':   '60s',
    'timeout': '30s',
    'retries': 3,
    'steps': [{
        'name':         'GET /apirest.php',
        'url':          GLPI_URL,
        'status_codes': '200',
        'no':           1
    }]
})
print("✅ Web scenario 'GLPI API Health' criado (60s, timeout 30s, 3 retries)")

# 4. Trigger: alertar se GLPI não responder
zapi('trigger.create', {
    'description': 'GLPI API indisponível (> 30s)',
    'expression':  'last(/VM-GLPI/web.test.fail[GLPI API Health])>0',
    'priority':    4,   # 4 = High
    'manual_close': 0
})
print("✅ Trigger criada — alerta P4/High se API não responder")
print("")
print("=== Configuração concluída ===")
print("   Verifique em: Zabbix → Monitoring → Hosts → VM-GLPI → Web")
