# CESUP Incidentes — Servidor principal

## Execução

```bash
chmod +x setup.sh && ./setup.sh
```

## Após o setup

Copie o **VIGIA_TOKEN** do `.env` para o dispositivo do vigia externo.

## Serviços disponíveis

| URL | Serviço |
|-----|---------|
| http://localhost | PWA |
| http://localhost/api/docs | API Swagger |
| http://localhost/auth | Keycloak |
| http://localhost/grafana | Grafana |
| http://localhost/zabbix | Zabbix |
| http://localhost:8081 | GLPI |

## Endpoint do vigia

O vigia externo bate nesta URL a cada 60s:
```
GET http://<IP_DO_SERVIDOR>/api/v1/heartbeat
Authorization: Bearer <VIGIA_TOKEN>
```
