#!/bin/bash
# Backup diário do GLPI — MariaDB + volume de anexos
# Cron: 0 2 * * * /opt/backup/backup_glpi.sh

set -euo pipefail

DATE=$(date +%Y%m%d_%H%M%S)
DEST="/mnt/backup/datacenter/glpi/$DATE"
RETENTION_DAYS=30
LOG="/var/log/backup_glpi.log"

log() { echo "[$(date '+%F %T')] $*" | tee -a $LOG; }

log "=== Início backup GLPI ==="
mkdir -p $DEST

# 1. Dump MariaDB
log "Dump MariaDB → $DEST/glpi_db.sql.gz"
mysqldump \
  --defaults-file=/etc/backup/.my.cnf \
  --single-transaction \
  --quick \
  glpi | gzip -9 > $DEST/glpi_db.sql.gz

SIZE=$(stat -c%s "$DEST/glpi_db.sql.gz")
if [ $SIZE -lt 100000 ]; then
  log "ERRO: dump muito pequeno ($SIZE bytes) — possível falha"
  exit 1
fi
log "Dump OK — tamanho: $(du -sh $DEST/glpi_db.sql.gz | cut -f1)"

# 2. Sincronizar volume de arquivos (fotos, laudos)
log "Sincronizando /var/lib/glpi/files/ → $DEST/files/"
rsync -a --delete \
  /var/lib/glpi/files/ \
  $DEST/files/
log "Arquivos OK — tamanho: $(du -sh $DEST/files | cut -f1)"

# 3. Cópia off-site
if mountpoint -q /mnt/backup-offsite; then
  rsync -a $DEST/ /mnt/backup-offsite/glpi/$DATE/
  log "Cópia off-site OK"
else
  log "AVISO: /mnt/backup-offsite não montado — cópia off-site pulada"
fi

# 4. Limpeza de backups antigos
log "Limpando backups com mais de $RETENTION_DAYS dias..."
find /mnt/backup/datacenter/glpi/ -maxdepth 1 -mtime +$RETENTION_DAYS -type d -exec rm -rf {} +

log "=== Backup concluído com sucesso ==="
