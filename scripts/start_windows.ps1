<#
.SYNOPSIS
    Build (if needed) and run the FinAlly container on Windows.

.DESCRIPTION
    Idempotent: safe to run repeatedly. Builds the image if it is missing or
    when -Build is passed, then (re)starts a single container with the db/ bind
    mount, port 8000 mapping, and the project .env file.

.PARAMETER Build
    Force a fresh image build even if one already exists.

.PARAMETER NoOpen
    Do not open the browser after the container is healthy.

.EXAMPLE
    .\scripts\start_windows.ps1 -Build
#>
param(
    [switch]$Build,
    [switch]$NoOpen
)

$ErrorActionPreference = "Stop"

$Image     = "finally:latest"
$Container = "finally"
$Port      = 8000
$Url       = "http://localhost:$Port"

# Resolve project root (this script lives in scripts/).
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir   = Split-Path -Parent $ScriptDir
Set-Location $RootDir

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "docker is not installed or not on PATH."
    exit 1
}

if (-not (Test-Path ".env")) {
    Write-Warning "No .env file found. Copy .env.example to .env and add your keys."
    Write-Warning "The simulator + LLM mock work without keys, but chat needs OPENROUTER_API_KEY."
}

# Ensure the host bind-mount dir exists.
New-Item -ItemType Directory -Force -Path (Join-Path $RootDir "db") | Out-Null

# Build the image if forced, or if it does not already exist.
docker image inspect $Image *> $null
$imageExists = ($LASTEXITCODE -eq 0)
if ($Build -or -not $imageExists) {
    Write-Host "Building image $Image..."
    docker build -t $Image $RootDir
} else {
    Write-Host "Image $Image already present (use -Build to rebuild)."
}

# Remove any existing container so the run is repeatable.
$existing = docker ps -a --format '{{.Names}}' | Select-String -SimpleMatch -Pattern $Container
if ($existing) {
    Write-Host "Removing existing container $Container..."
    docker rm -f $Container | Out-Null
}

$envArgs = @()
if (Test-Path ".env") {
    $envArgs += @("--env-file", ".env")
}

Write-Host "Starting container $Container..."
docker run -d `
    --name $Container `
    -p "$($Port):8000" `
    -v "$($RootDir)/db:/app/db" `
    @envArgs `
    $Image | Out-Null

# Wait for the health endpoint before declaring success / opening the browser.
Write-Host -NoNewline "Waiting for $Url/api/health "
for ($i = 0; $i -lt 30; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri "$Url/api/health" -UseBasicParsing -TimeoutSec 2
        if ($resp.StatusCode -eq 200) {
            Write-Host " ready."
            Write-Host "FinAlly is running at $Url"
            if (-not $NoOpen) { Start-Process $Url }
            exit 0
        }
    } catch {
        # not ready yet
    }
    Write-Host -NoNewline "."
    Start-Sleep -Seconds 1
}

Write-Host ""
Write-Warning "Container started but health check did not pass in time."
Write-Warning "Check logs with: docker logs $Container"
exit 1
