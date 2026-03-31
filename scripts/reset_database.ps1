$ErrorActionPreference = 'Stop'

Write-Host "Stopping Letta containers..." -ForegroundColor Cyan
docker compose --env-file .env2 down

Write-Host "Wiping old PostgreSQL data in .\data\pgdata\..." -ForegroundColor Yellow
if (Test-Path ".\data\pgdata") {
    Get-ChildItem -Path ".\data\pgdata" -Force | Remove-Item -Recurse -Force
    Write-Host "Data wiped successfully." -ForegroundColor Green
} else {
    Write-Host "No data found or folder is already empty." -ForegroundColor Green
}

Write-Host "Starting Letta containers with new environment..." -ForegroundColor Cyan
docker compose --env-file .env2 up -d

Write-Host "Done! New fresh database is initializing." -ForegroundColor Green
