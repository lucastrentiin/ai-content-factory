#!/bin/sh
# Backup diário do PostgreSQL com retenção. Executado pelo serviço "backup" do docker-compose.
set -e
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
INTERVAL="${BACKUP_INTERVAL_SECONDS:-86400}"
mkdir -p /backups
while true; do
  TS=$(date -u +%Y%m%d_%H%M%S)
  FILE="/backups/factory_${TS}.sql.gz"
  if pg_dump -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner | gzip > "$FILE.tmp"; then
    mv "$FILE.tmp" "$FILE"
    echo "backup ok: $FILE ($(du -h "$FILE" | cut -f1))"
  else
    echo "backup FALHOU em $TS" >&2
    rm -f "$FILE.tmp"
  fi
  find /backups -name 'factory_*.sql.gz' -mtime +"$RETENTION_DAYS" -delete
  sleep "$INTERVAL"
done
