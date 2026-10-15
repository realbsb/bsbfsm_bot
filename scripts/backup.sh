#!/usr/bin/env bash
# Бэкап MariaDB (схема workflow) и архива медиа.
# Кроном: 0 3 * * * /opt/workflow/scripts/backup.sh

set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-/var/lib/workflow/backup}"
DB_HOST="${DB_HOST:-mariadb}"
DB_USER="${DB_USER:-workflow}"
DB_PASSWORD="${DB_PASSWORD:-change_me}"
DB_NAME="${DB_NAME:-workflow}"
ARCHIVE_DIR="${ARCHIVE_DIR:-/var/lib/workflow/archive}"
KEEP_DAYS="${KEEP_DAYS:-30}"

TS="$(date +%Y%m%d_%H%M%S)"
TARGET="${BACKUP_ROOT}/${TS}"
mkdir -p "${TARGET}"

echo "[backup] dumping DB ${DB_NAME}..."
MYSQL_PWD="${DB_PASSWORD}" mysqldump \
    --host="${DB_HOST}" \
    --user="${DB_USER}" \
    --single-transaction \
    --routines \
    --triggers \
    --default-character-set=utf8mb4 \
    "${DB_NAME}" | gzip > "${TARGET}/db.sql.gz"

if [ -d "${ARCHIVE_DIR}" ]; then
    echo "[backup] archiving media..."
    tar -czf "${TARGET}/archive.tar.gz" -C "$(dirname "${ARCHIVE_DIR}")" "$(basename "${ARCHIVE_DIR}")"
fi

echo "[backup] pruning backups older than ${KEEP_DAYS} days..."
find "${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -type d -mtime "+${KEEP_DAYS}" -exec rm -rf {} +

echo "[backup] done: ${TARGET}"
