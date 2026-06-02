<#
.SYNOPSIS
    Stop and remove the FinAlly container on Windows.

.DESCRIPTION
    Idempotent: safe to run when nothing is running. Does NOT delete the SQLite
    database — db/finally.db persists on the host (PLAN §11). To start fresh,
    run: Remove-Item db/finally.db

.EXAMPLE
    .\scripts\stop_windows.ps1
#>
$ErrorActionPreference = "Stop"

$Container = "finally"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "docker is not installed or not on PATH."
    exit 1
}

$existing = docker ps -a --format '{{.Names}}' | Select-String -SimpleMatch -Pattern $Container
if ($existing) {
    Write-Host "Stopping and removing container $Container..."
    docker rm -f $Container | Out-Null
    Write-Host "Stopped. Database preserved at db/finally.db (delete it to start fresh)."
} else {
    Write-Host "No container named $Container is running. Nothing to do."
}
