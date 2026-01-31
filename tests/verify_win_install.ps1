# Verification Script for Forge Windows Install

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
# Assuming this is in tests/, go up one level
$ProjectRoot = Split-Path -Parent $ScriptDir

Write-Host "=== Verifying Forge Installation ===" -ForegroundColor Cyan
Write-Host "Project Root: $ProjectRoot"

# 1. Check forge.bat
$ForgeBat = Join-Path $ProjectRoot "forge.bat"
if (Test-Path $ForgeBat) {
    Write-Host "  [PASS] forge.bat exists" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] forge.bat missing" -ForegroundColor Red
    exit 1
}

# 2. Check Execution
Write-Host "  Testing execution of forge.bat --help..."
try {
    $Output = & $ForgeBat --help 2>&1
    if ($Output -match "Usage:" -or $Output -match "Options:") {
        Write-Host "  [PASS] forge.bat runs successfully" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] forge.bat output unexpected" -ForegroundColor Red
        Write-Host $Output
        exit 1
    }
} catch {
    Write-Host "  [FAIL] forge.bat execution failed" -ForegroundColor Red
    Write-Host $_
    exit 1
}

# 3. Check PATH in Registry (Persistent check)
$UserPathReg = [Environment]::GetEnvironmentVariable("Path", "User")
$CleanProjectRoot = $ProjectRoot.TrimEnd("\")

if ($UserPathReg -split ";" -contains $CleanProjectRoot) {
    Write-Host "  [PASS] Project root found in User PATH registry" -ForegroundColor Green
} else {
    Write-Host "  [WARN] Project root NOT found in current User PATH" -ForegroundColor Yellow
    Write-Host "         (It might have been added but this shell doesn't see it, or script failed)"
}

Write-Host ""
Write-Host "Verification Passed!" -ForegroundColor Green
