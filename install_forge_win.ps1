# Windows Installer for Forge & Agent CLI
# Creates batch wrappers and adds to PATH

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "=== Forge Windows Installer ===" -ForegroundColor Cyan
Write-Host "Target Directory: $ScriptDir"

# === Step 1: Create Batch Wrappers ===
Write-Host ""
Write-Host "Creating batch wrappers..."

$PythonPath = "python"
if (Test-Path "venv\Scripts\python.exe") {
    $PythonPath = "%~dp0venv\Scripts\python.exe"
}

# 1. forge.bat
$ForgeBatContent = @"
@echo off
setlocal
set "PYTHON=$PythonPath"
if exist "%~dp0venv\Scripts\python.exe" set "PYTHON=%~dp0venv\Scripts\python.exe"

"%PYTHON%" "%~dp0forge\cli.py" %*
endlocal
"@

$ForgeBatPath = Join-Path $ScriptDir "forge.bat"
Set-Content -Path $ForgeBatPath -Value $ForgeBatContent -Encoding ASCII
Write-Host "  [+] Created forge.bat" -ForegroundColor Green

# 2. agent.bat - Skipping for now as user requested forge only.
# Future todo: Implement agent.bat calling python module directly.

# Reading agent.sh to be sure about agent.bat content
$AgentShPath = Join-Path $ScriptDir "agent.sh"
if (Test-Path $AgentShPath) {
    # If agent.sh is a python wrapper, we can mimic it.
    # For now, let's create a placeholder or simple wrapper if we know the python entry point.
    # The user principally asked for forge.
    # I will add agent.bat that runs "python -m agent" which is a common pattern, 
    # OR better, if agent.sh executes a python file, I'll do that.
    
    # Update: I will create agent.bat to run forge's agent cli if it exists, or just skipping for now to strictly follow "register forge".
    # User asked: "register forge ... so i can run forge -p ...".
    $null
}

# === Step 2: Update PATH ===
Write-Host ""
Write-Host "Checking PATH environment variable..."

$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$CleanPath = $ScriptDir.TrimEnd("\")

if ($UserPath -split ";" -contains $CleanPath) {
    Write-Host "  [v] $CleanPath is already in User PATH" -ForegroundColor Green
} else {
    Write-Host "  [+] Adding $CleanPath to User PATH..."
    $NewPath = $UserPath + ";$CleanPath"
    [Environment]::SetEnvironmentVariable("Path", $NewPath, "User")
    Write-Host "  [!] PATH updated." -ForegroundColor Yellow
    Write-Host "      You may need to restart your terminal to use 'forge' from other directories." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Installation Complete ===" -ForegroundColor Green
Write-Host "Try running: .\forge.bat --help"
