$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
  $env:NEXT_PUBLIC_API_URL = 'http://127.0.0.1:8000'
  npx next dev --hostname 127.0.0.1 --port 3000
}
finally {
  Pop-Location
}
