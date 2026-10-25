$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$pythonExe = 'C:\Users\USER\AppData\Local\Python\pythoncore-3.15-64\python.exe'
Set-Location -LiteralPath $projectDir
$listeners = @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)
if ($listeners.Count -gt 0) {
    $backendId = $listeners[0].OwningProcess
    $backend = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $backendId)
    if (!$backend -or $backend.CommandLine -notmatch 'uvicorn main:app.*--port 8000') {
        throw 'Unexpected process on backend port; nothing stopped'
    }
    if ($backend.ExecutablePath -ne $pythonExe) { throw 'Unexpected backend executable' }
}
& $pythonExe tools/reset_trial_data.py
if ($LASTEXITCODE -ne 0) { throw 'Reset preview failed; nothing stopped' }
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$logDir = Join-Path $projectDir 'backups/reset-logs'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
try {
    if ($listeners.Count -gt 0) {
        Stop-Process -Id $backendId
        Wait-Process -Id $backendId -Timeout 15 -ErrorAction SilentlyContinue
    }
    & $pythonExe tools/reset_trial_data.py --apply
    if ($LASTEXITCODE -ne 0) { throw 'Reset failed; backup retained' }
} finally {
    $updated = Start-Process -FilePath $pythonExe -ArgumentList '-m uvicorn main:app --host 127.0.0.1 --port 8000 --timeout-graceful-shutdown 5 --no-access-log' -WorkingDirectory $projectDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir "$stamp.out.log") -RedirectStandardError (Join-Path $logDir "$stamp.err.log")
    $ready = $false
    for ($n = 0; $n -lt 40; $n++) {
        try {
            $health = Invoke-RestMethod 'http://127.0.0.1:8000/api/health' -TimeoutSec 2
            if ($health.ok) { $ready = $true; break }
        } catch {}
        Start-Sleep -Milliseconds 250
    }
    if (!$ready) { throw 'Backend restart failed; see backups/reset-logs' }
    Write-Output ("Backend ready, PID " + $updated.Id)
}
