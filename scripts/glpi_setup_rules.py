#!/usr/bin/env python3
"""
Cria as 9 regras de categorização automática no GLPI.
Regras baseadas no nome do chamado (preenchido pelo webhook do Zabbix).

Uso:
  export GLPI_API_URL=https://glpi.suarede.intra/apirest.php
  export GLPI_APP_TOKEN=seu_app_token
  export GLPI_SESSION_TOKEN=token_obtido_via_initSession
  python3 glpi_setup_rules.py

IMPORTANTE: Ajuste os IDs de categoria (category_id) conforme o
            seu ambiente. Consulte via: GET /apirest.php/ITILCategory
"""
import requests, os, sys

BASE = os.environ['GLPI_API_URL']
HDR  = {
    'Content-Type': 'application/json',
    'App-Token':    os.environ['GLPI_APP_TOKEN'],
    'Session-Token': os.environ['GLPI_SESSION_TOKEN'],
}

# Mapeamento: palavra-chave no título → categoria GLPI
# Ajuste os IDs de categoria conforme o GLPI da sua instalação
RULES = [
    {'match': 'disk',        'category_id': 10, 'label': 'Hardware / Disco'},
    {'match': 'power',       'category_id': 11, 'label': 'Hardware / Fonte'},
    {'match': 'fan',         'category_id': 12, 'label': 'Hardware / Ventilação'},
    {'match': 'unreachable', 'category_id': 20, 'label': 'Rede / Conectividade'},
    {'match': 'interface',   'category_id': 21, 'label': 'Rede / Interface'},
    {'match': 'cpu',         'category_id': 30, 'label': 'Performance / CPU'},
    {'match': 'memory',      'category_id': 31, 'label': 'Performance / Memória'},
    {'match': 'temperature', 'category_id': 40, 'label': 'Ambiente / Temperatura'},
    {'match': 'ups',         'category_id': 50, 'label': 'Energia / Nobreak'},
]

print("=== Criando regras de categorização no GLPI ===")
for i, rule in enumerate(RULES):
    payload = {'input': {
        'name':       rule['label'],
        'sub_type':  'RuleTicket',
        'ranking':    i + 1,
        'match':      1,   # AND
        'is_active':  1,
        'conditions': [{
            'criteria':  'name',
            'condition': 6,   # 6 = contains (regex)
            'pattern':   rule['match'],
        }],
        'actions': [{
            'action': 'assign',
            'field':  'itilcategories_id',
            'value':  rule['category_id'],
        }]
    }}
    r = requests.post(BASE + '/Rule', json=payload, headers=HDR, verify=False)
    status = '✅' if r.ok else '❌'
    print(f"{status} {rule['label']} (keyword: {rule['match']})")
    if not r.ok:
        print(f"   Erro: {r.text}")

print("=== Concluído ===")
