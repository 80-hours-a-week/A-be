#!/usr/bin/env bash
# DocSuri local-serving Postgres backup — dump inside the compose container → verify → S3.
#
# The Mac mini serves DocSuri from backend/docker-compose.yml with no Multi-AZ safety net,
# so this script IS the durability story: dump, prove the archive is readable
# (pg_restore --list), then ship it off-machine to the personal-account bucket.
#
# Cron (daily 03:30):
#   30 3 * * * $HOME/Projects/DocSuri/ops/local/backup-db.sh >> $HOME/Library/Logs/docsuri-backup.log 2>&1
#
# Requires: the compose stack's postgres service running, and an AWS profile allowed
# s3:PutObject on the bucket (docsuri-dev). No host pg_dump needed — dump and verify both
# run inside the postgres:16 container, so client/server versions can never drift.
set -euo pipefail

DOCSURI_REPO="${DOCSURI_REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
COMPOSE_FILE="$DOCSURI_REPO/backend/docker-compose.yml"
BUCKET="${DOCSURI_BACKUP_BUCKET:-docsuri-backups-559352512800}"
export AWS_PROFILE="${AWS_PROFILE:-docsuri-dev}"
DB_USER="${DOCSURI_DB_USER:-docsuri}"
DB_NAME="${DOCSURI_DB_NAME:-docsuri}"

STAMP="$(date +%Y%m%d-%H%M%S)"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT
DUMP="$WORKDIR/docsuri-$STAMP.dump"

echo "[$(date '+%F %T')] dumping $DB_NAME …"
# Dump to a container-side temp file and verify there before copying out: pg_restore --list
# on a real file (not a pipe) is unambiguous for custom-format archives, and a dump that
# pg_restore can't even list is not a backup — fail before uploading garbage.
docker compose -f "$COMPOSE_FILE" exec -T postgres bash -c "
  set -euo pipefail
  pg_dump -U '$DB_USER' --format=custom --no-owner -f /tmp/docsuri-backup.dump '$DB_NAME'
  pg_restore --list /tmp/docsuri-backup.dump > /dev/null
"
docker compose -f "$COMPOSE_FILE" cp postgres:/tmp/docsuri-backup.dump "$DUMP"
docker compose -f "$COMPOSE_FILE" exec -T postgres rm -f /tmp/docsuri-backup.dump

KEY="postgres/docsuri-$STAMP.dump"
aws s3 cp "$DUMP" "s3://$BUCKET/$KEY" --sse AES256 --no-progress
echo "[$(date '+%F %T')] backup ok: s3://$BUCKET/$KEY ($(du -h "$DUMP" | cut -f1))"
