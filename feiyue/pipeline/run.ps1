param(
  [string]$Term = "2026 Fall",
  [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $ProjectDir ".venv"
$Python = Join-Path $VenvDir "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
  py -3 -m venv $VenvDir
}

& $Python -c "import requests, dotenv, reportlab, PIL, pypdf" 2>$null
if ($LASTEXITCODE -ne 0) {
  & $Python -m pip install -r (Join-Path $ProjectDir "requirements.txt")
}

$Arguments = @(
  (Join-Path $ProjectDir "pipeline.py"),
  "--config", (Join-Path $ProjectDir "config.json"),
  "--term", $Term
)
if ($ValidateOnly) {
  $Arguments += "--validate-only"
}

& $Python @Arguments
