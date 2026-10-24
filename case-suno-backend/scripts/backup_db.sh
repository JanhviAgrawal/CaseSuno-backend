#!/bin/bash
# Build Plan Section 13 (Page 20)
# Automated Daily PostgreSQL Backup Script for CASE SUNO (Bash / Linux / Docker)

set -e

DB_NAME="${DB_NAME:-casesuno}"
DB_USER="${DB_USER:-postgres}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5432}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"

mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/casesuno_backup_$TIMESTAMP.dump"

echo "Starting automated PostgreSQL backup for database '$DB_NAME' to '$BACKUP_FILE'..."

pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -F c -b -v -f "$BACKUP_FILE" "$DB_NAME"

echo "Backup completed successfully: $BACKUP_FILE"
