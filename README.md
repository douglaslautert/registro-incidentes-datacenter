# Registro de Incidentes do Datacenter

Sistema de registro automático de incidentes baseado em **GLPI + Zabbix**, implantado on-premises em duas VMs no Proxmox.

## Arquitetura

- **VM-GLPI** (192.168.10.200) — PHP 8.2 + Apache + MariaDB + Plugin Fields
- **VM-ZABBIX** (192.168.10.201) — Zabbix Server 7.x + PostgreSQL + Nginx
- **Integração** — Webhook JavaScript (Media Type Zabbix) → API REST GLPI

## Pré-requisitos

- GLPI já instalado e acessível em HTTPS
- Proxmox como hypervisor
- Ansible com acesso SSH às VMs
- Python 3.8+ e `pip install requests` para os scripts

## Ordem de execução

1. **Snapshot da VM-GLPI** no Proxmox
2. **Criar VM-ZABBIX** no Proxmox (ver `docs/runbook.md`)
3. **Rodar playbook Ansible**:
   ```bash
   ansible-playbook site.yml --ask-vault-pass
   ```
4. **Criar usuário de serviço**:
   ```bash
   export GLPI_ADMIN_PASS=... GLPI_APP_TOKEN=... GLPI_SVC_PASS=...
   bash scripts/glpi_setup_service_user.sh
   ```
5. **Criar Media Type no Zabbix**:
   ```bash
   export ZABBIX_URL=... ZABBIX_USER=... ZABBIX_PASS=... \
          GLPI_API_URL=... GLPI_SVC_USER=... GLPI_SVC_PASS=... GLPI_APP_TOKEN=...
   python3 scripts/setup_zabbix_mediatype.py
   ```
6. **Criar regras de categorização**:
   ```bash
   export GLPI_API_URL=... GLPI_APP_TOKEN=... GLPI_SESSION_TOKEN=...
   python3 scripts/glpi_setup_rules.py
   ```
7. **Configurar Plugin Fields** no GLPI UI (Setup → Plugins → Fields)
8. **Validar webhook** com chamado de teste
9. **Configurar monitor** da VM-GLPI:
   ```bash
   export ZABBIX_URL=... ZABBIX_API_TOKEN=... GLPI_API_URL=...
   python3 scripts/zabbix_setup_glpi_monitor.py
   ```

## Documentação

- `docs/workspace.dsl` — Modelo C4 (Structurizr Lite/structurizr.com)
- `docs/runbook.md` — Procedimentos operacionais

## Arquitetura (Modelo C4)

Visualizar os diagramas:
```bash
# Via Structurizr Lite (Docker)
docker run -it --rm -p 8080:8080 \
  -v $(pwd)/docs:/usr/local/structurizr \
  structurizr/lite
# Acesse: http://localhost:8080
```

## Segurança

- Senhas gerenciadas via **Ansible Vault** — nunca em texto plano no Git
- Autenticação via **LDAP institucional** — zero contas locais em produção
- Acesso restrito à **rede interna ou VPN**
- TLS 1.2+ em todas as interfaces

## Roadmap

| Fase | Escopo | Status |
|---|---|---|
| MVP | Detecção + Chamados + Ativos + Segurança | 🚧 Em implantação |
| Fase 2 | Integração NetBox | ⏳ Aguardando cadastro |
| Fase 3 | Assistência por IA (Ollama local) | ⏳ Aguardando decisão |
