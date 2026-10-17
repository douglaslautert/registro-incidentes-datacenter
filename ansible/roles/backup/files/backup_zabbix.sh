#!/bin/bash
# Backup semanal do Zabbix — PostgreSQL
# Cron: 0 3 * * 0 /opt/backup/backup_zabbix.sh

set -euo pipefail

DATE=$(date +%Y%m%d)
DEST="/mnt/backup/datacenter/zabbix/$DATE"
LOG="/var/log/backup_zabbix.log"

log() { echo "[$(date '+%F %T')] $*" | tee -a $LOG; }

log "=== Início backup Zabbix ==="
mkdir -p $DEST

sudo -u postgres pg_dump zabbix | gzip -9 > $DEST/zabbix_db.sql.gz

SIZE=$(stat -c%s "$DEST/zabbix_db.sql.gz")
log "Dump OK — tamanho: $(du -sh $DEST/zabbix_db.sql.gz | cut -f1) ($SIZE bytes)"
log "=== Backup Zabbix concluído ==="
