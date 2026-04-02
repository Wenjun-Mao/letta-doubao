$ErrorActionPreference = 'Stop'

$envFile = if ($args.Count -gt 0 -and $args[0]) { $args[0] } elseif ($env:LETTA_ENV_FILE) { $env:LETTA_ENV_FILE } else { '.env2' }
$env:LETTA_ENV_FILE = $envFile

Write-Host "Using env file: $envFile" -ForegroundColor DarkCyan

Write-Host "Stopping Letta containers..." -ForegroundColor Cyan
docker compose --env-file $envFile down

Write-Host "Wiping old PostgreSQL data in .\data\pgdata\..." -ForegroundColor Yellow
if (Test-Path ".\data\pgdata") {
    Get-ChildItem -Path ".\data\pgdata" -Force | Remove-Item -Recurse -Force
    Write-Host "Data wiped successfully." -ForegroundColor Green
} else {
    Write-Host "No data found or folder is already empty." -ForegroundColor Green
}

Write-Host "Starting Letta containers with new environment..." -ForegroundColor Cyan
docker compose --env-file $envFile up -d

Write-Host "Done! New fresh database is initializing." -ForegroundColor Green
