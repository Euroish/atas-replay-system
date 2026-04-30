$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    python -m venv (Join-Path $Root ".venv")
}

& $VenvPython -m pip install --upgrade pip setuptools wheel
& $VenvPython -m pip install -r (Join-Path $Backend "requirements.txt")

Push-Location $Frontend
npm install
Pop-Location

Write-Host "Environment ready."
Write-Host "Backend Python: $VenvPython"
Write-Host "Frontend: $Frontend"
