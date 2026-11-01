$frontendRoot = $PSScriptRoot | Split-Path -Parent
Set-Location $frontendRoot
$env:API_BACKEND_URL = "http://127.0.0.1:8123"
if (-not $env:NSAJ_E2E_RUN_ID) {
    $env:NSAJ_E2E_RUN_ID = [guid]::NewGuid().ToString()
}
if ($env:NSAJ_E2E_DEMO_CONTENT -eq "true") {
    $env:NEXT_PUBLIC_NSAJ_DEMO_CONTENT = "true"
} else {
    $env:NEXT_PUBLIC_NSAJ_DEMO_CONTENT = "false"
}

npm run build
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

npx playwright test
$testExitCode = $LASTEXITCODE
$repositoryRoot = Split-Path -Parent $frontendRoot
$databasePath = Join-Path $repositoryRoot ".local\e2e-db-$env:NSAJ_E2E_RUN_ID.sqlite3"
if ($env:NSAJ_E2E_RUN_ID -match '^[0-9a-f-]{36}$' -and (Test-Path -LiteralPath $databasePath)) {
    Remove-Item -LiteralPath $databasePath
}
exit $testExitCode
