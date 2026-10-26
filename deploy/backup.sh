#!/usr/bin/env bash
# Konsistente SQLite-Kopie (auch bei laufendem Betrieb) + Fotos; alte Stände nach KEEP_DAYS löschen.
set -euo pipefail
: "${DB:?}" "${PHOTOS:?}" "${BACKUP_DIR:?}"
KEEP_DAYS="${KEEP_DAYS:-30}"
stamp=$(date +%F)

mkdir -p "$BACKUP_DIR"
sqlite3 "$DB" ".backup '$BACKUP_DIR/lager-$stamp.db'"
sqlite3 "$BACKUP_DIR/lager-$stamp.db" "PRAGMA integrity_check" | grep -qx ok
if [ -d "$PHOTOS" ]; then
  tar -czf "$BACKUP_DIR/photos-$stamp.tar.gz" -C "$(dirname "$PHOTOS")" "$(basename "$PHOTOS")"
fi
find "$BACKUP_DIR" -maxdepth 1 -name 'lager-*.db' -mtime +"$KEEP_DAYS" -delete
find "$BACKUP_DIR" -maxdepth 1 -name 'photos-*.tar.gz' -mtime +"$KEEP_DAYS" -delete
echo "Backup $stamp ok"
