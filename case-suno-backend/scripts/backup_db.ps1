# Build Plan Section 13 (Page 20)
# Automated Daily PostgreSQL Backup Script for CASE SUNO (PowerShell)

param(
    [string]$DbName = $env:DB_NAME,
    [string]$DbUser = $env:DB_USER,
    [string]$DbHost = "127.0.0.1",
    [string]$DbPort = "5432",
    [string]$BackupDir = "./backups"
)

if (-not $DbName) { $DbName = "casesuno" }
if (-not $DbUser) { $DbUser = "postgres" }

if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir | Out-Null
}

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupFile = Join-Path $BackupDir "casesuno_backup_$Timestamp.sql.gz"

Write-Host "Starting backup for database '$DbName' to '$BackupFile'..." -ForegroundColor Cyan

# Run pg_dump and pipe to gzip or output sql
try {
    & pg_dump -h $DbHost -p $DbPort -U $DbUser -F c -b -v -f "$BackupDir/casesuno_backup_$Timestamp.dump" $DbName
    Write-Host "Backup completed successfully: $BackupDir/casesuno_backup_$Timestamp.dump" -ForegroundColor Green
} catch {
    Write-Error "Backup failed: $_"
}
