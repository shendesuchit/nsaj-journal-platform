$frontendRoot = $PSScriptRoot | Split-Path -Parent
Set-Location $frontendRoot
$env:API_BACKEND_URL = "http://127.0.0.1:8123"
npm run start -- --hostname 127.0.0.1 --port 3123
