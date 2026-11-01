$repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repositoryRoot

$runId = $env:NSAJ_E2E_RUN_ID
if (-not $runId) {
    throw "NSAJ_E2E_RUN_ID must be set by Playwright."
}

$runData = Join-Path $repositoryRoot ".local\e2e-$runId"
$env:APP_ENV = "test"
# Browser requests run concurrently. A per-run file gives each request its own
# SQLite connection instead of sharing one in-memory connection across threads.
$localRoot = Join-Path $repositoryRoot ".local"
New-Item -ItemType Directory -Path $localRoot -Force | Out-Null
$databasePath = (Join-Path $localRoot "e2e-db-$runId.sqlite3").Replace('\', '/')
$env:DATABASE_URL = "sqlite+pysqlite:///$databasePath"
$env:DB_PASSWORD = "test-only-password"
$env:NSAJ_MFA_ENCRYPTION_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
$env:PRIVATE_STORAGE_PATH = Join-Path $runData "files"
$env:MAIL_CAPTURE_PATH = Join-Path $runData "mail"
$env:PUBLIC_BASE_URL = "http://127.0.0.1:3123"

& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8123
