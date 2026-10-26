#!/usr/bin/env bash
# Installation im Debian-13-LXC (als root). Erwartet den Code unter /opt/sortiersystem.
# Aufruf: LAGER_HOST=lager.home.lan BACKUP_DIR=/mnt/backup bash /opt/sortiersystem/deploy/install.sh
set -euo pipefail

LAGER_HOST="${LAGER_HOST:-lager.home.lan}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/sortiersystem}"
APP_DIR=/opt/sortiersystem
DATA_DIR=/var/lib/sortiersystem

apt-get update
apt-get install -y --no-install-recommends caddy sqlite3 curl ca-certificates

id lager >/dev/null 2>&1 || useradd --system --home "$DATA_DIR" --shell /usr/sbin/nologin lager
install -d -o lager -g lager "$DATA_DIR" "$BACKUP_DIR"

# uv + Abhängigkeiten (ohne Dev-Tools); uv lädt bei Bedarf passendes Python
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
fi
chown -R lager:lager "$APP_DIR"
sudo -u lager env UV_PYTHON_INSTALL_DIR="$DATA_DIR/python" UV_CACHE_DIR="$DATA_DIR/.cache" \
  uv sync --project "$APP_DIR" --no-dev --frozen

cat >/etc/sortiersystem.env <<EOF
LAGER_DATA_DIR=$DATA_DIR
LAGER_BASE_URL=https://$LAGER_HOST
EOF
cat >/etc/sortiersystem-backup.env <<EOF
DB=$DATA_DIR/lager.db
PHOTOS=$DATA_DIR/photos
BACKUP_DIR=$BACKUP_DIR
KEEP_DAYS=30
EOF

install -m 644 "$APP_DIR"/deploy/sortiersystem*.service "$APP_DIR"/deploy/sortiersystem-backup.timer \
  /etc/systemd/system/
sed "s/{\$LAGER_HOST}/$LAGER_HOST/g" "$APP_DIR/deploy/Caddyfile" >/etc/caddy/Caddyfile

systemctl daemon-reload
systemctl enable --now sortiersystem.service sortiersystem-backup.timer
systemctl restart caddy

echo
echo "Fertig. Prüfen: curl -sk https://$LAGER_HOST/health"
echo "Root-Zertifikat fürs Handy: http://$LAGER_HOST/ca.crt"
