[CmdletBinding()]
param([string]$RuntimeDirectory)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'local-process.ps1')
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $RuntimeDirectory) { $RuntimeDirectory = Join-Path $repoRoot 'runtime' }
$statePath = Join-Path ([IO.Path]::GetFullPath($RuntimeDirectory)) 'local-processes.json'
if (-not (Test-Path -LiteralPath $statePath)) { Write-Host 'Khong co process state cua ung dung.'; exit 0 }
$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
foreach ($entry in @($state.api, $state.worker)) {
    if (Test-FeedbackProcessIdentity $entry) {
        Stop-FeedbackProcessTree $entry
        Write-Host "Da dung process cua ung dung: $($entry.id)"
    }
}
Remove-Item -LiteralPath $statePath
