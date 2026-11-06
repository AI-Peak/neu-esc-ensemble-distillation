[CmdletBinding()]
param([ValidateRange(1024, 65535)][int]$Port = 8765, [string]$RuntimeDirectory)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'local-process.ps1')
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $RuntimeDirectory) { $RuntimeDirectory = Join-Path $repoRoot 'runtime' }
$runtimePath = [IO.Path]::GetFullPath($RuntimeDirectory)
$pythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Chay .\scripts\setup-local.ps1 truoc.' }
if (-not (Test-Path -LiteralPath (Join-Path $repoRoot 'apps\web\dist\index.html'))) {
    throw 'Chua co frontend build. Chay .\scripts\setup-local.ps1 truoc.'
}
New-Item -ItemType Directory -Force -Path $runtimePath | Out-Null
$logsPath = Join-Path $runtimePath 'logs'
New-Item -ItemType Directory -Force -Path $logsPath | Out-Null
$statePath = Join-Path $runtimePath 'local-processes.json'
$hashProvider = [Security.Cryptography.SHA256]::Create()
try { $lockHash = [BitConverter]::ToString($hashProvider.ComputeHash([Text.Encoding]::UTF8.GetBytes($runtimePath.ToLowerInvariant()))).Replace('-', '') }
finally { $hashProvider.Dispose() }
$startupMutex = [Threading.Mutex]::new($false, "Local\FeedbackStartup-$lockHash")
$ownsStartupMutex = $false
try {
try { $ownsStartupMutex = $startupMutex.WaitOne(0) }
catch [Threading.AbandonedMutexException] { $ownsStartupMutex = $true }
if (-not $ownsStartupMutex) { throw 'Mot script khoi dong khac dang chay cho runtime nay.' }
if (Test-Path -LiteralPath $statePath) {
    $previousState = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    $previousApiAlive = Test-FeedbackProcessIdentity $previousState.api
    $previousWorkerAlive = Test-FeedbackProcessIdentity $previousState.worker
    if ($previousApiAlive -and $previousWorkerAlive) {
        try {
            $existingHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$($previousState.port)/api/v1/health" -TimeoutSec 2
        } catch { $existingHealth = $null }
        if ($existingHealth -and $existingHealth.status -eq 'ok' -and $existingHealth.worker.alive) {
            Write-Host "Ung dung da chay (PID $($previousState.api.id)). URL: http://127.0.0.1:$($previousState.port)"
            Write-Host 'Dung scripts\stop-local.ps1 neu can khoi dong lai.'
            exit 0
        }
    }
    # Recover only processes whose recorded PID and start time still match this app.
    Stop-FeedbackProcessTree $previousState.api
    Stop-FeedbackProcessTree $previousState.worker
    Remove-Item -LiteralPath $statePath
}
if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw "Cong $Port dang duoc su dung. Chon -Port khac; khong dung process khac tu dong."
}
$env:FEEDBACK_RUNTIME = $runtimePath
$env:PYTHONUTF8 = '1'
$apiArguments = @('-m', 'uvicorn', 'services.api.main:app', '--app-dir', ('"' + $repoRoot + '"'),
                 '--host', '127.0.0.1', '--port', "$Port", '--no-access-log')
$workerArguments = @('-m', 'services.worker', '--runtime-dir', ('"' + $runtimePath + '"'))
$apiProcess = $null
$workerProcess = $null
try {
    $workerProcess = Start-Process -FilePath $pythonExe -ArgumentList $workerArguments -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logsPath 'worker.stdout.log') -RedirectStandardError (Join-Path $logsPath 'worker.stderr.log')
    $apiProcess = Start-Process -FilePath $pythonExe -ArgumentList $apiArguments -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logsPath 'api.stdout.log') -RedirectStandardError (Join-Path $logsPath 'api.stderr.log')
    $ready = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        Start-Sleep -Milliseconds 500
        $apiProcess.Refresh()
        $workerProcess.Refresh()
        if ($apiProcess.HasExited -or $workerProcess.HasExited) { throw "Process dung som. Xem log trong $logsPath" }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/health" -TimeoutSec 2
            if ($health.status -eq 'ok') { $ready = $true; break }
        } catch { }
    }
    if (-not $ready) { throw "API khong san sang. Xem log trong $logsPath" }
    $state = @{
        port = $Port; runtime = $runtimePath; repo = $repoRoot
        api = @{id = $apiProcess.Id; started_at = $apiProcess.StartTime.ToUniversalTime().ToString('o')}
        worker = @{id = $workerProcess.Id; started_at = $workerProcess.StartTime.ToUniversalTime().ToString('o')}
    }
    $state | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath -Encoding utf8
    Write-Host "Da chay: http://127.0.0.1:$Port"
    Write-Host "Du lieu local: $runtimePath"
    Write-Host 'Dung: .\scripts\stop-local.ps1'
} catch {
    foreach ($launchedProcess in @($apiProcess, $workerProcess)) {
        if ($launchedProcess -and -not $launchedProcess.HasExited) {
            Stop-FeedbackProcessTree @{id=$launchedProcess.Id;started_at=$launchedProcess.StartTime.ToUniversalTime().ToString('o')}
        }
    }
    throw
}
} finally {
    if ($ownsStartupMutex) { $startupMutex.ReleaseMutex() }
    $startupMutex.Dispose()
}
