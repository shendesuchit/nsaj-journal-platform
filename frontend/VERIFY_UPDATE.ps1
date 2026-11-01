$ErrorActionPreference = 'Stop'
$required = @('src/components/admin-case-panel.tsx','src/app/journal-control.css','src/app/admin/overview/page.tsx')
foreach ($file in $required) { if (!(Test-Path $file)) { throw "Missing update file: $file. Run from the frontend project root." } }
if (!(Select-String -Path 'src/app/editorial/page.tsx' -Pattern 'manual_transitions' -Quiet)) { throw 'Editorial workflow update missing.' }
Write-Host 'Updated source files found. Run npm run build and restart the frontend. Apply backendCode.zip as well.'
