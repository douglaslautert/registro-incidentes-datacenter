# CESUP Incidentes — stack Docker Compose

Este diretório contém o artefato principal: a stack completa do sistema de registro de incidentes, que sobe com Docker Compose.

O roteiro completo está no [README da raiz](../README.md): requisitos, instalação, teste mínimo, experimentos e problemas comuns.

## Resumo rápido

```bash
cp .env.example .env     # ajuste as senhas se necessário
make setup               # instalação completa (15–30 min na 1ª vez)
make health              # estado dos containers
```

| URL | Serviço |
|-----|---------|
| http://localhost | PWA |
| http://localhost/api/docs | API (Swagger) |
| http://localhost/auth | Keycloak |
| http://localhost/grafana | Grafana |
| http://localhost/zabbix/ | Zabbix |
| http://localhost:8081 | GLPI |

## Vigia externo

O vigia ([`vigia/`](vigia/)) roda em outro dispositivo, com 4G/GSM, e consulta a cada 60 s:

```
GET http://<IP_DO_SERVIDOR>/api/v1/heartbeat
Authorization: Bearer <VIGIA_TOKEN>
```

Copie o `VIGIA_TOKEN` do `.env` para o dispositivo do vigia.
