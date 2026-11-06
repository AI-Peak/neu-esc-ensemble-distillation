function Test-FeedbackProcessIdentity {
    param($Entry)
    if (-not $Entry) { return $false }
    $candidate = Get-Process -Id $Entry.id -ErrorAction SilentlyContinue
    if (-not $candidate) { return $false }
    # PowerShell 7 may deserialize ISO JSON dates as DateTime; Windows PS5 keeps strings.
    $expectedStart = ([datetime]$Entry.started_at).ToUniversalTime()
    return $candidate.StartTime.ToUniversalTime().Ticks -eq $expectedStart.Ticks
}

function Stop-FeedbackProcessTree {
    param($Entry)
    if (Test-FeedbackProcessIdentity $Entry) {
        # venv python.exe is a launcher on Windows: stop its verified child tree as well.
        & taskkill.exe /PID $Entry.id /T /F | Out-Null
    }
}
