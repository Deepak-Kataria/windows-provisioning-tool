#!/usr/bin/env bash
# Nightly Postgres backup. Install with:  sudo crontab -e
#   30 2 * * *  /opt/itops/web/deploy/backup.sh >> /var/log/itops-backup.log 2>&1
# Copy /opt/itops/backups off the box (rclone, scp, ...) - a backup on the same disk is not a backup.
set -euo pipefail
cd "$(dirname "$0")"
DEST=/opt/itops/backups
KEEP_DAYS=14
mkdir -p "$DEST"
chmod 700 "$DEST"
STAMP=$(date +%Y%m%d-%H%M%S)
docker compose exec -T db pg_dump -U itops -d itops --format=custom > "$DEST/itops-$STAMP.dump"
find "$DEST" -name 'itops-*.dump' -mtime +"$KEEP_DAYS" -delete
echo "$(date -Is) backup ok: itops-$STAMP.dump"
