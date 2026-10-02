# One-command start on Windows: sets up dependencies on first run, then serves on http://127.0.0.1:8000
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "Creating Python environment..."
    python -m venv backend\.venv
    & $py -m pip install -q -r backend\requirements.txt
}
if (-not (Test-Path "frontend\dist\index.html")) {
    Write-Host "Building the analyst console..."
    Push-Location frontend
    if (-not (Test-Path "node_modules")) { npm install --no-audit --no-fund }
    npm run build
    Pop-Location
}
& $py run.py --open @args
