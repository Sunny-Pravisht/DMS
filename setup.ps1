<#
  Document Manager Setup Script (Windows PowerShell)
  Usage:
    .\setup.ps1 dev     # Start development environment with hot reload
    .\setup.ps1 prod    # Start production environment (uses locally built image)
    .\setup.ps1 build   # Build Docker image locally
    .\setup.ps1 stop    # Stop and remove containers
    .\setup.ps1 status  # Show container status
    .\setup.ps1 logs    # Follow logs
#>

param(
  [Parameter(Position=0)] [string]$Command = 'help'
)

$ErrorActionPreference = 'Stop'

$ContainerName = 'documentmanager'
$ImageName = 'documentmanager'

function Info($msg) { Write-Host "[INFO] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Err($msg)  { Write-Host "[ERROR] $msg" -ForegroundColor Red }

function Require-Docker() {
  if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Err 'Docker is not installed or not on PATH.'
    exit 1
  }
}

function New-EnvFile() {
  if (-not (Test-Path .env)) {
    Info 'Creating .env file...'
    $secret = 'change-me-in-production'
    $pythonCommand = Get-Command python3, python -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pythonCommand) {
      try {
        $generatedSecret = & $pythonCommand.Source -c 'import secrets; print(secrets.token_urlsafe(32))'
        if ($LASTEXITCODE -eq 0 -and $generatedSecret) {
          $secret = $generatedSecret.Trim()
        }
      } catch {
        Warn 'Could not generate a random secret with Python; update SECRET_KEY manually.'
      }
    }

    @"
# Security - CHANGE THIS IN PRODUCTION!
SECRET_KEY=$secret

# Database
DATABASE_URL=sqlite:///./data/documents.db

# AI Provider (groq | openai | azure). Model names live in config/models.json.
AI_PROVIDER=groq
GROQ_API_KEY=
GROQ_BASE_URL=https://api.groq.com/openai/v1

# Groq has no embeddings endpoint; embeddings run locally on the CPU.
EMBEDDING_PROVIDER=local
OCR_ENGINE=auto

# Application
ENVIRONMENT=production
LOG_LEVEL=INFO
"@ | Set-Content -NoNewline .env
    Warn 'Created .env file. Please update with your settings!'
  }
}

function Invoke-Dev() {
  Require-Docker
  Info 'Building development image...'
  docker build -f Dockerfile.dev -t "$ImageName:dev" .

  Info 'Starting development environment...'
  $pwdPath = (Get-Location).Path
  docker run -d `
    --name "$ContainerName-dev" `
    -p 8000:8000 `
    -v "$pwdPath/app:/app/app" `
    -v "$pwdPath/frontend:/app/frontend" `
    -v "$pwdPath/config:/app/config" `
    -v "$pwdPath/data:/app/data" `
    -v "$pwdPath/staging:/app/staging" `
    -v "$pwdPath/storage:/app/storage" `
    -v "$pwdPath/uploads:/app/uploads" `
    -v "$pwdPath/logs:/app/logs" `
    -v "$pwdPath/backups:/app/backups" `
    -v "$pwdPath/chroma:/app/chroma" `
    "$ImageName:dev"

  Info 'Development environment started! Navigate to http://localhost:8000'
}

function Invoke-Prod() {
  Require-Docker
  New-EnvFile
  Info 'Starting production environment...'

  # Ensure local image exists
  $image = "$ImageName:latest"
  $exists = docker images --format '{{.Repository}}:{{.Tag}}' | Select-String -SimpleMatch $image
  if (-not $exists) {
    Err "Local image not found. Run '.\\setup.ps1 build' first."
    exit 1
  }

  $pwdPath = (Get-Location).Path
  # Pass the whole .env rather than enumerating keys, so provider-specific
  # values (GROQ_API_KEY, EMBEDDING_PROVIDER, OCR_ENGINE, ...) are not dropped.
  docker run -d `
    --name "$ContainerName" `
    -p 8000:8000 `
    --env-file .env `
    -v "$pwdPath/config:/app/config" `
    -v "$pwdPath/data:/app/data" `
    -v "$pwdPath/staging:/app/staging" `
    -v "$pwdPath/storage:/app/storage" `
    -v "$pwdPath/uploads:/app/uploads" `
    -v "$pwdPath/logs:/app/logs" `
    -v "$pwdPath/backups:/app/backups" `
    -v "$pwdPath/chroma:/app/chroma" `
    --restart unless-stopped `
    $image

  Info 'Production environment started! Navigate to http://localhost:8000'
}

function Invoke-Build() {
  Require-Docker
  Info 'Building production Docker image...'
  docker build -t "$ImageName:latest" .
  Info 'Build complete!'
}

function Invoke-Stop() {
  Require-Docker
  Info 'Stopping containers...'
  docker ps -a --format '{{.Names}}' | ForEach-Object {
    if ($_ -eq "$ContainerName-dev" -or $_ -eq "$ContainerName") {
      docker stop $_ | Out-Null
      docker rm $_ | Out-Null
      Info "Stopped and removed $_"
    }
  }
}

function Invoke-Status() {
  Require-Docker
  Info 'Container status:'
  $names = docker ps -a --format '{{.Names}}'
  $filtered = $names | Where-Object { $_ -like "$ContainerName*" }
  if ($filtered) { docker ps -a | Select-String -SimpleMatch $ContainerName } else { Warn 'No DocumentManager containers found.' }
}

function Invoke-Logs() {
  Require-Docker
  $running = docker ps --format '{{.Names}}'
  if ($running -contains "$ContainerName-dev") { docker logs -f "$ContainerName-dev" }
  elseif ($running -contains "$ContainerName") { docker logs -f "$ContainerName" }
  else { Err 'No running DocumentManager container found.' }
}

switch ($Command) {
  'dev'    { Invoke-Dev }
  'prod'   { Invoke-Prod }
  'build'  { Invoke-Build }
  'stop'   { Invoke-Stop }
  'status' { Invoke-Status }
  'logs'   { Invoke-Logs }
  default {
    Write-Host @"
Document Manager Setup Script (Windows)

Usage: .\setup.ps1 [dev|prod|build|stop|status|logs]
Examples:
  .\setup.ps1 dev
  .\setup.ps1 build
"@
  }
}
