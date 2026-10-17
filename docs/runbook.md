# Runbook — Registro de Incidentes do Datacenter

**Sistema:** GLPI + Zabbix · on-premises · Proxmox  
**Versão:** 1.0 · 17/10/2026

---

## Pré-requisitos antes de qualquer deploy

```bash
# Snapshot da VM-GLPI antes de qualquer mudança
qm snapshot <VMID_GLPI> pre-deploy-$(date +%Y%m%d) --description "Antes do deploy"
```

---

## Validar webhook após deploy

### 1. Criar trigger de teste no Zabbix
Zabbix → Configuration → Hosts → VM-GLPI → Triggers → criar com:
- Expressão: `last(/VM-GLPI/system.uptime)>999999`
- Severity: High

### 2. Verificar log do Zabbix Server
```bash
grep -i "glpi\|webhook\|mediatype" /var/log/zabbix/zabbix_server.log | tail -30
```
Procurar por `ticket_id` no retorno do script JS.

### 3. Confirmar chamado no GLPI
GLPI → Assistance → Tickets → filtrar por "[Zabbix]"
Verificar: nome do equipamento, severidade e timestamp corretos.

### 4. Testar recuperação
Remover a trigger de teste → verificar que o chamado foi atualizado
com status "Resolvido" e horário de fim preenchido.

---

## Webhook não está criando chamados

| Verificação | Comando | Ação se falhar |
|---|---|---|
| GLPI API responde | `curl -k https://glpi.intra/apirest.php` | `systemctl restart apache2` |
| Porta 443 aberta | `nc -zv 192.168.10.200 443` (da VM-ZABBIX) | `ufw status verbose` |
| Usuário ativo | GLPI → Admin → Users → zabbix-api → ativo = sim | Reativar e regenerar token |
| App-Token válido | GLPI → Setup → General → API | Regenerar e atualizar vault |
| Log do Media Type | Zabbix → Admin → Media Types → GLPI Webhook → Test | Ver mensagem de erro |

---

## Verificar backup

```bash
# Último backup GLPI
ls -lh /mnt/backup/datacenter/glpi/ | tail -5

# Tamanho do dump (abaixo de 100 KB = possível falha)
du -sh /mnt/backup/datacenter/glpi/$(ls -t /mnt/backup/datacenter/glpi | head -1)/glpi_db.sql.gz

# Log de backup
journalctl -t backup_glpi | tail -20
```

---

## Restaurar GLPI após falha grave

```bash
# 1. Parar Apache
systemctl stop apache2

# 2. Restaurar banco (ajustar data do backup)
BACKUP="20261017_020001"
zcat /mnt/backup/datacenter/glpi/$BACKUP/glpi_db.sql.gz | mysql glpi

# 3. Restaurar arquivos
rsync -a --delete /mnt/backup/datacenter/glpi/$BACKUP/files/ /var/lib/glpi/files/
chown -R www-data:www-data /var/lib/glpi/

# 4. Reiniciar e verificar
systemctl start apache2
curl -sk https://glpi.intra/apirest.php | grep -c session
```

---

## Atualizar GLPI ou Zabbix

1. **Snapshot da VM no Proxmox antes de qualquer atualização**
   ```bash
   qm snapshot <VMID> pre-update-$(date +%Y%m%d)
   ```
2. Seguir upgrade guide oficial da ferramenta
3. Testar webhook após atualização (procedimento acima)
4. Se Plugin Fields quebrar, reverter para o snapshot
5. Atualizar `workspace.dsl` se a arquitetura mudou e commitar no Git

---

## Alertas do Zabbix — o que fazer

| Alerta | Causa provável | Ação |
|---|---|---|
| GLPI API indisponível (> 30s) | Apache caiu ou MariaDB travou | `systemctl status apache2 mariadb` → reiniciar |
| Volume de anexos > 80% | Crescimento de fotos | Limpeza ou migração para MinIO (ADR-04) |
| Backup falhou | Disco cheio ou NAS inacessível | Verificar espaço e montagem do NAS |
| Zabbix lag > 30s | Muitos hosts ou CPU saturada | Aumentar `StartPollers` no `zabbix_server.conf` |

---

## Proxmox — comandos úteis

```bash
# Listar VMs
qm list

# Status de uma VM
qm status <VMID>

# Tirar snapshot
qm snapshot <VMID> <nome> --description "descrição"

# Listar snapshots
qm listsnapshot <VMID>

# Reverter para snapshot
qm rollback <VMID> <nome>
```
