#!/bin/sh
# Copies the database to ./backups/army_passion_YYYY-MM-DD_HHMM.sql.gz and
# keeps the last 14. Run from the project folder, or nightly from cron:
#   0 2 * * * cd /opt/army-passion && sh deploy/backup.sh >> backups/backup.log 2>&1
set -e
mkdir -p backups
stamp=$(date +%Y-%m-%d_%H%M)
docker compose -f docker-compose.prod.yml --env-file .env.production exec -T db \
  pg_dump -U army -d army_passion | gzip > "backups/army_passion_${stamp}.sql.gz"
ls -1t backups/army_passion_*.sql.gz | tail -n +15 | xargs -r rm --
echo "Saved backups/army_passion_${stamp}.sql.gz"
