param(
  [ValidateSet("html","js","both")]
  [string]$Tests = "both",
  [int]$TimeoutSec = 180
)

function Log([string]$Message) {
  $ts = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
  Write-Host "[$ts] $Message"
}

function Load-Dotenv([string]$Path) {
  if (-not (Test-Path $Path)) {
    return
  }
  Log "Loading environment defaults from $Path"
  Get-Content -Path $Path | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) {
      continue
    }
    if ($line.StartsWith("export ")) {
      $line = $line.Substring(7).TrimStart()
    }
    if (-not ($line -match "=")) {
      continue
    }
    $parts = $line -split "=", 2
    $key = $parts[0].Trim()
    $value = $parts[1].Trim()
    if (-not $key) {
      continue
    }
    if (-not (Test-Path "Env:$key")) {
      Set-Item -Path "Env:$key" -Value $value
    }
  }
}

function Resolve-Python([string]$Override) {
  if ($Override) {
    return $Override
  }
  if ($env:VIRTUAL_ENV) {
    $candidate = Join-Path $env:VIRTUAL_ENV "Scripts\python.exe"
    if (Test-Path $candidate) {
      return $candidate
    }
  }
  foreach ($candidate in "python","python3") {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
      return $candidate
    }
  }
  throw "Python interpreter not found; install python or set FORGE_PYTHON."
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$dotenvPath = Join-Path $repoRoot ".env"
Load-Dotenv $dotenvPath

$workspace = $env:FORGE_WORKSPACE
if (-not $workspace) { $workspace = "poc" }

$models = $env:FORGE_MODEL_MATRIX
if (-not $models) {
  Log "FORGE_MODEL_MATRIX is empty. Set it before running."
  exit 1
}

$pythonPath = $null
try {
  $pythonPath = Resolve-Python $env:FORGE_PYTHON
} catch {
  Log $_.Exception.Message
  exit 1
}
Log "Using Python interpreter: $pythonPath"

$runnerPath = Join-Path $repoRoot "scripts\forge_runner.py"

function Run-Forge([string]$Prompt, [string]$Model) {
  $promptFile = [System.IO.Path]::GetTempFileName()
  Set-Content -Path $promptFile -Value $Prompt -Encoding UTF8

  Log "Forge run (model=$Model, timeout=${TimeoutSec}s, python=$pythonPath)"

  $escapedModel = $Model -replace '"','`"'
  $escapedWorkspace = $workspace -replace '"','`"'

  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $pythonPath
  $psi.Arguments = "`"$runnerPath`" --prompt-file `"$promptFile`" --model `"$escapedModel`" --workspace `"$escapedWorkspace`""
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true

  $proc = New-Object System.Diagnostics.Process
  $proc.StartInfo = $psi
  $proc.add_OutputDataReceived({
    if ($_.Data) { Log "[forge stdout] $($_.Data)" }
  })
  $proc.add_ErrorDataReceived({
    if ($_.Data) { Log "[forge stderr] $($_.Data)" }
  })
  $null = $proc.Start()
  $proc.BeginOutputReadLine()
  $proc.BeginErrorReadLine()

  if (-not $proc.WaitForExit($TimeoutSec * 1000)) {
    Log "Forge timed out; killing process"
    $proc.Kill()
    Remove-Item -Force $promptFile -ErrorAction SilentlyContinue
    return $false
  }
  Log "Forge exit code: $($proc.ExitCode)"
  Remove-Item -Force $promptFile -ErrorAction SilentlyContinue
  return $proc.ExitCode -eq 0
}

function Check-Html([string]$File) {
  $content = Get-Content -Path $File -Raw
  if ($content -notmatch "<!doctype html") { return $false }
  if ($content -notmatch "<html") { return $false }
  if ($content -notmatch "<head") { return $false }
  if ($content -notmatch "<body") { return $false }
  if (([regex]::Matches($content, "@keyframes", "IgnoreCase")).Count -lt 2) { return $false }
  if (([regex]::Matches($content, "animation\s*:", "IgnoreCase")).Count -lt 2) { return $false }
  if ($content -notmatch "background") { return $false }
  return $true
}

function Check-JsCreate([string]$File) {
  $content = Get-Content -Path $File -Raw
  if ($content -notmatch "hello world") { return $false }
  if ($content -notmatch "document\.body") { return $false }
  return $true
}

function Check-JsImprove([string]$File) {
  $content = Get-Content -Path $File -Raw
  if ($content -notmatch "domcontentloaded") { return $false }
  if ($content -notmatch "createElement") { return $false }
  if ($content -notmatch "append") { return $false }
  if ($content -notmatch "console\.log") { return $false }
  return $true
}

$modelList = $models.Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ }
foreach ($model in $modelList) {
  $slug = ($model -replace "[^a-zA-Z0-9_-]+", "-").ToLower()

  if ($Tests -eq "html" -or $Tests -eq "both") {
    $htmlFile = Join-Path "workspaces\$workspace" "hello-world-$slug.html"
    Log "=== HTML test for $model ==="
    $prompt = "You are Forge, a system-agnostic coding agent. Create a new file named hello-world-$slug.html in the workspace root. The file must be valid HTML5 with <!doctype html>, <html>, <head>, <body>. Include inline CSS and JS. Add at least two CSS animations: one for the background and one for text. Use write_file to create the file; if it already exists, use read_file then apply_patch to update it. Do not create any other files."
    Run-Forge $prompt $model
    if (-not (Test-Path $htmlFile)) {
      Log "Missing $htmlFile; retrying with strict tool-call prompt"
      $strict = "You are Forge. Output ONLY a JSON tool call for write_file with keys {`"name`":`"write_file`",`"arguments`":{`"path`":`"hello-world-$slug.html`",`"content`":`"...`"}}. The content must be valid HTML5 with two @keyframes animations. Do not include prose."
      Run-Forge $strict $model
    }
    if (Check-Html $htmlFile) {
      Log "HTML checks passed: $htmlFile"
    } else {
      Log "HTML checks failed; requesting Forge to improve HTML"
      $improve = "You are Forge, a system-agnostic coding agent. Improve the existing file hello-world-$slug.html so it has at least two distinct @keyframes animations (background + text) and those animations are applied to elements. Use read_file first, then apply_patch. Do not change the filename."
      Run-Forge $improve $model
      if (Check-Html $htmlFile) {
        Log "HTML checks passed after improve: $htmlFile"
      } else {
        Log "HTML checks failed after improve: $htmlFile"
        exit 1
      }
    }
  }

  if ($Tests -eq "js" -or $Tests -eq "both") {
    $jsFile = Join-Path "workspaces\$workspace" "function-$slug.js"
    Log "=== JS test for $model ==="
    $create = "You are Forge, a system-agnostic coding agent. Create a new file named function-$slug.js in the workspace root. The file should only contain JavaScript that displays 'hello world' by setting document.body.textContent and logging to the console. Use write_file to create the file; if it already exists, use read_file then apply_patch to update it. Do not create any other files."
    Run-Forge $create $model
    if (-not (Test-Path $jsFile)) {
      Log "Missing $jsFile; retrying with strict tool-call prompt"
      $strictJs = "You are Forge. Output ONLY a JSON tool call for write_file with keys {`"name`":`"write_file`",`"arguments`":{`"path`":`"function-$slug.js`",`"content`":`"...`"}}. The content must set document.body text to 'hello world' and log it. Do not include prose."
      Run-Forge $strictJs $model
    }
    if (-not (Check-JsCreate $jsFile)) {
      Log "JS create checks failed: $jsFile"
      exit 1
    }
    $improveJs = "You are Forge, a system-agnostic coding agent. Improve the existing file function-$slug.js without changing the filename. Keep the console log and hello world text. Wrap the logic in DOMContentLoaded and avoid overwriting the entire body. Create a dedicated element and append it to the body. Use read_file first, then apply_patch to update the file."
    Run-Forge $improveJs $model
    if (Check-JsImprove $jsFile) {
      Log "JS improve checks passed: $jsFile"
    } else {
      Log "JS improve checks failed: $jsFile"
      exit 1
    }
  }
}

Log "Forge matrix run complete."
