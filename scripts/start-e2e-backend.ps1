$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $root 'backend'
$dbPath = Join-Path $backendDir 'kitchen_os_e2e.db'
$python = Join-Path $backendDir 'venv\Scripts\python.exe'

if (-not (Test-Path $python)) {
  throw "Missing backend Python interpreter at $python"
}

if (Test-Path $dbPath) {
  Remove-Item $dbPath -Force
}

Push-Location $backendDir
try {
  $env:DATABASE_URL = 'sqlite:///./kitchen_os_e2e.db'
  $env:JWT_SECRET_KEY = 'kitchenos-e2e-jwt-secret'
  $env:BOOTSTRAP_ENABLED = 'true'
  $env:ADMIN_BOOTSTRAP_TOKEN = 'kitchenos-e2e-bootstrap-token'
  $env:ALLOWED_ORIGINS = 'http://127.0.0.1:3000'

  & $python .\init_e2e_db.py
  & $python -m uvicorn main:app --host 127.0.0.1 --port 8000
}
finally {
  Pop-Location
}
