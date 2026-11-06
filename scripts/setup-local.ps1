[CmdletBinding()]
param(
    [switch]$WithModelRuntime,
    [switch]$WithTests,
    [switch]$ReuseInstalledPackages
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $repoRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        $venvArguments = @('-m', 'venv', '.venv')
        if ($ReuseInstalledPackages) { $venvArguments += '--system-site-packages' }
        & python @venvArguments
        if ($LASTEXITCODE -ne 0) { throw 'Khong tao duoc Python venv. Can Python 3.10 hoac moi hon.' }
    }
    $pythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'
    & $pythonExe -m pip install -r requirements-api.lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Cai dependency API that bai.' }
    if ($WithModelRuntime) {
        & $pythonExe -m pip install --upgrade pip==26.3
        if ($LASTEXITCODE -ne 0) { throw 'Cap nhat pip that bai.' }
        & $pythonExe -m pip install -r requirements-model.lock.txt --extra-index-url https://download.pytorch.org/whl/cpu
        if ($LASTEXITCODE -ne 0) { throw 'Cai dependency model that bai.' }
    }
    if ($WithTests) {
        & $pythonExe -m pip install -r requirements-test.lock.txt
        if ($LASTEXITCODE -ne 0) { throw 'Cai dependency test that bai.' }
        & $pythonExe -m playwright install chromium
        if ($LASTEXITCODE -ne 0) { throw 'Cai Chromium cho E2E that bai.' }
    }
    Push-Location -LiteralPath (Join-Path $repoRoot 'apps\web')
    try {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw 'npm ci that bai.' }
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Build frontend that bai.' }
    } finally { Pop-Location }
    @('runtime', 'runtime\models', 'runtime\exports', 'runtime\logs') | ForEach-Object {
        New-Item -ItemType Directory -Force -Path (Join-Path $repoRoot $_) | Out-Null
    }
    Write-Host 'Setup hoan tat. Chay: .\scripts\start-local.ps1'
    Write-Host 'Model phai duoc cai rieng theo docs\MODEL_WORKFLOW.md. Khong co model gia.'
} finally { Pop-Location }
