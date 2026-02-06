# v2 Startup Script - Windows PowerShell
# Self-contained coding agent stack
#
# Usage:
#   .\start.ps1                          # Start with default workspace (poc)
#   .\start.ps1 -Workspace beatbridge    # Start with specific workspace
#   .\start.ps1 -NoBrowser               # Don't open browser at end

param(
    [Alias("w")]
    [string]$Workspace = "",
    [switch]$NoBrowser,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

if ($Help) {
    Write-Host "Usage: .\start.ps1 [OPTIONS]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Workspace, -w NAME   Set the default workspace (e.g., poc, beatbridge_app)"
    Write-Host "  -NoBrowser            Don't open browser at end"
    Write-Host "  -Help                 Show this help message"
    Write-Host ""
    Write-Host "Workspaces are located in: $ScriptDir\workspaces\"
    exit 0
}

Write-Host "=== v2 Coding Agent Stack ===" -ForegroundColor Cyan
Write-Host ""

# === Check Prerequisites ===
# Python (needed for file opener service)
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "Python not found in PATH." -ForegroundColor Yellow
    Write-Host "Install Python for file-opener service:"
    Write-Host "  winget install 9NQ7512CXL7T" -ForegroundColor Cyan
    Write-Host ""
}

# VS Code (for file opening)
$codeCmd = Get-Command code -ErrorAction SilentlyContinue
if (-not $codeCmd) {
    Write-Host "VS Code not found. Install with:" -ForegroundColor Yellow
    Write-Host "  winget install Microsoft.VisualStudioCode" -ForegroundColor Cyan
    Write-Host ""
}

# Load environment from .env file
$EnvFile = Join-Path $ScriptDir ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim()
            # Remove quotes if present
            $value = $value -replace '^["'']|["'']$', ''
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
}

# Get config from env or defaults
$DefaultWorkspace = if ($env:DEFAULT_WORKSPACE) { $env:DEFAULT_WORKSPACE } else { "poc" }
$AgentModel = if ($env:AGENT_MODEL) { $env:AGENT_MODEL } else { "qwen3:1.7b" }
$VisionModel = if ($env:VISION_MODEL) { $env:VISION_MODEL } else { "qwen2.5vl:7b" }
$AiderApiPort = if ($env:AIDER_API_PORT) { $env:AIDER_API_PORT } else { "8001" }
$V2OllamaPort = "11435"

# Override workspace if specified via CLI
if ($Workspace) {
    $WorkspacePath = Join-Path $ScriptDir "workspaces\$Workspace"
    if (-not (Test-Path $WorkspacePath)) {
        Write-Host "ERROR: Workspace not found: $WorkspacePath" -ForegroundColor Red
        Write-Host ""
        Write-Host "Available workspaces:"
        Get-ChildItem "$ScriptDir\workspaces" -Directory | ForEach-Object { Write-Host "  - $($_.Name)" }
        exit 1
    }
    $DefaultWorkspace = $Workspace
    Write-Host "Workspace: $Workspace (from CLI)"
} else {
    Write-Host "Workspace: $DefaultWorkspace (from .env or default)"
}
Write-Host ""

# === Check and Start Docker ===
function Test-DockerRunning {
    try {
        $null = docker info 2>&1
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Start-DockerDesktop {
    Write-Host "Docker is not running. Attempting to start Docker Desktop..."

    $DockerPaths = @(
        "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe",
        "${env:ProgramFiles(x86)}\Docker\Docker\Docker Desktop.exe"
    )

    foreach ($path in $DockerPaths) {
        if (Test-Path $path) {
            Write-Host "Starting Docker Desktop..."
            Start-Process $path
            return $true
        }
    }

    return $false
}

function Wait-ForDocker {
    param([int]$MaxWait = 60)

    Write-Host -NoNewline "Waiting for Docker to be ready... "
    for ($i = 1; $i -le $MaxWait; $i++) {
        if (Test-DockerRunning) {
            Write-Host "ready (${i}s)" -ForegroundColor Green
            return $true
        }
        Start-Sleep -Seconds 1
    }
    Write-Host "timeout after ${MaxWait}s" -ForegroundColor Red
    return $false
}

if (-not (Test-DockerRunning)) {
    if (Start-DockerDesktop) {
        if (-not (Wait-ForDocker)) {
            Write-Host "ERROR: Docker Desktop started but not responding." -ForegroundColor Red
            Write-Host "Please ensure Docker Desktop is fully started and try again."
            exit 1
        }
    } else {
        Write-Host "ERROR: Could not start Docker Desktop automatically." -ForegroundColor Red
        Write-Host "Please start Docker Desktop manually and try again."
        exit 1
    }
}
Write-Host "Docker: running" -ForegroundColor Green

# === Start v2 Services ===
Write-Host ""
Write-Host "--- Starting v2 Services ---" -ForegroundColor Yellow
docker compose --env-file .env -f docker/docker-compose.yml up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to start Docker services" -ForegroundColor Red
    exit 1
}

# === Wait for v2 Ollama ===
Write-Host ""
Write-Host "--- v2 Ollama Setup ---" -ForegroundColor Yellow
Write-Host -NoNewline "Waiting for v2 Ollama... "
for ($i = 1; $i -le 60; $i++) {
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:${V2OllamaPort}/api/tags" -TimeoutSec 2 -ErrorAction SilentlyContinue
        Write-Host "ready" -ForegroundColor Green
        break
    } catch {
        if ($i -eq 60) {
            Write-Host "timeout" -ForegroundColor Red
            Write-Host "Check logs: docker logs wfhub-v2-ollama"
            exit 1
        }
        Start-Sleep -Seconds 1
    }
}

# Check available models
try {
    $AvailableModels = Invoke-RestMethod -Uri "http://localhost:${V2OllamaPort}/api/tags" -ErrorAction SilentlyContinue
} catch {
    $AvailableModels = @{ models = @() }
}

function Ensure-Model {
    param([string]$Model, [string]$Label)

    if (-not $Model) { return }

    Write-Host -NoNewline "Checking model ($Label`: $Model)... "
    $found = $AvailableModels.models | Where-Object { $_.name -eq $Model }

    if ($found) {
        Write-Host "OK" -ForegroundColor Green
    } else {
        Write-Host "NOT FOUND" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Pulling model $Model into v2 Ollama..."
        docker exec wfhub-v2-ollama ollama pull $Model
        Write-Host "Model ready" -ForegroundColor Green
        # Refresh available models
        $script:AvailableModels = Invoke-RestMethod -Uri "http://localhost:${V2OllamaPort}/api/tags" -ErrorAction SilentlyContinue
    }
}

Ensure-Model -Model $AgentModel -Label "agent"
if ($VisionModel -ne $AgentModel) {
    Ensure-Model -Model $VisionModel -Label "vision"
}

# Show v2 Ollama models
Write-Host ""
Write-Host "v2 Ollama models:"
try {
    $models = Invoke-RestMethod -Uri "http://localhost:${V2OllamaPort}/api/tags"
    $models.models | ForEach-Object { Write-Host "  - $($_.name)" }
} catch {
    Write-Host "  (none yet)"
}

# === Wait for Main API ===
$FastApiPort = if ($env:FASTAPI_PORT) { $env:FASTAPI_PORT } else { "8002" }
Write-Host ""
Write-Host "--- Main API ---" -ForegroundColor Yellow
Write-Host -NoNewline "Waiting for Main API... "
for ($i = 1; $i -le 30; $i++) {
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:${FastApiPort}/health" -TimeoutSec 2 -ErrorAction SilentlyContinue
        Write-Host "ready" -ForegroundColor Green
        break
    } catch {
        if ($i -eq 30) {
            Write-Host "timeout" -ForegroundColor Red
            Write-Host "Check logs: docker logs wfhub-v2-main-api"
            exit 1
        }
        Start-Sleep -Seconds 1
    }
}

# === Run Database Migrations ===
Write-Host ""
Write-Host "--- Database Migrations ---" -ForegroundColor Yellow
Write-Host -NoNewline "Running Alembic migrations... "
$prevErrorAction = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$migrationOutput = & docker exec wfhub-v2-main-api alembic upgrade head 2>&1
$migrationExitCode = $LASTEXITCODE
$ErrorActionPreference = $prevErrorAction

if ($migrationExitCode -eq 0) {
    Write-Host "done" -ForegroundColor Green
} else {
    Write-Host "failed (checking status...)" -ForegroundColor Yellow
}

if ($migrationOutput) {
    Write-Host "Migration output:" -ForegroundColor DarkYellow
    $migrationOutput | ForEach-Object { Write-Host "  $_" }
}

if ($migrationExitCode -ne 0) {
    docker exec wfhub-v2-main-api alembic current 2>&1 | Select-Object -First 5
}

# === Wait for Aider API ===
Write-Host ""
Write-Host "--- Aider API ---" -ForegroundColor Yellow
Write-Host -NoNewline "Waiting for Aider API... "
for ($i = 1; $i -le 30; $i++) {
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:${AiderApiPort}/health" -TimeoutSec 2 -ErrorAction SilentlyContinue
        Write-Host "ready" -ForegroundColor Green
        break
    } catch {
        if ($i -eq 30) {
            Write-Host "timeout" -ForegroundColor Red
            Write-Host "Check logs: docker logs wfhub-v2-aider-api"
            exit 1
        }
        Start-Sleep -Seconds 1
    }
}

# === Status ===
Write-Host ""
Write-Host "=== v2 Stack Status ===" -ForegroundColor Cyan
docker compose --env-file .env -f docker/docker-compose.yml ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

Write-Host ""
Write-Host "=== Config ===" -ForegroundColor Cyan
try {
    $health = Invoke-RestMethod -Uri "http://localhost:${AiderApiPort}/health"
    $health | ConvertTo-Json
} catch {
    Write-Host "(Could not fetch config)"
}

Write-Host ""
Write-Host "=== Quick Test ===" -ForegroundColor Cyan
Write-Host "  # Health check"
Write-Host "  curl http://localhost:${AiderApiPort}/health"
Write-Host ""
Write-Host "  # Run POC game tests"
Write-Host "  pytest tests/test_poc_game.py -v -s"
Write-Host ""

# === Start File Opener Service ===
Write-Host ""
Write-Host "--- File Opener Service ---" -ForegroundColor Yellow
$FileOpenerPort = 8888
$FileOpenerScript = Join-Path $ScriptDir "scripts\file-opener.py"

# Check if already running
$existingProcess = Get-NetTCPConnection -LocalPort $FileOpenerPort -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -First 1

if ($existingProcess) {
    Write-Host "file-opener: already running (pid $existingProcess)" -ForegroundColor Green
} else {
    if (Test-Path $FileOpenerScript) {
        $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
        if ($pythonCmd) {
            Start-Process -FilePath python -ArgumentList $FileOpenerScript -WindowStyle Hidden
            Write-Host "file-opener: started on http://localhost:${FileOpenerPort}" -ForegroundColor Green
        } else {
            Write-Host "file-opener: python not found, skipping" -ForegroundColor Yellow
        }
    } else {
        Write-Host "file-opener: script not found at $FileOpenerScript" -ForegroundColor Yellow
    }
}

# === Open Browser ===
if (-not $NoBrowser) {
    Write-Host ""
    Write-Host "Opening browser..."
    try {
        Start-Process "https://wfhub.localhost"
    } catch {
        try {
            Start-Process "http://localhost:8002"
        } catch {
            Write-Host "Could not open browser automatically"
        }
    }
}

Write-Host ""
Write-Host "Ready!" -ForegroundColor Green
