$ErrorActionPreference='Stop'
$projectDir=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectDir
$pythonExe='C:\Users\USER\AppData\Local\Python\pythoncore-3.15-64\python.exe'
$backendId=(Get-NetTCPConnection -LocalPort 8000 -State Listen | Select-Object -First 1).OwningProcess
$backend=Get-CimInstance Win32_Process -Filter ("ProcessId="+$backendId)
if(!$backend -or $backend.CommandLine -notmatch 'uvicorn main:app.*--port 8000'){throw 'Unexpected backend process; nothing stopped'}
& $pythonExe prepare_stability_update.py
if($LASTEXITCODE -ne 0){throw 'Update deferred; nothing stopped'}
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$logDir=Join-Path $projectDir 'backups/stability-logs'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
Stop-Process -Id $backendId
$updated=Start-Process -FilePath $pythonExe -ArgumentList '-m uvicorn main:app --host 127.0.0.1 --port 8000 --timeout-graceful-shutdown 5 --no-access-log' -WorkingDirectory $projectDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir "$stamp.out.log") -RedirectStandardError (Join-Path $logDir "$stamp.err.log")
$ready=$false
for($n=0;$n -lt 40;$n++){
    try{$health=Invoke-RestMethod 'http://127.0.0.1:8000/api/health' -TimeoutSec 2;if($health.ok){$ready=$true;break}}catch{}
    Start-Sleep -Milliseconds 250
}
if(!$ready){throw 'Backend not ready; see backups/stability-logs'}
if(!(Get-NetTCPConnection -LocalPort 8443 -State Listen -ErrorAction SilentlyContinue)){
    Start-Process -FilePath $pythonExe -ArgumentList 'run_mobile_gateway.py' -WorkingDirectory $projectDir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir "$stamp.mobile.out.log") -RedirectStandardError (Join-Path $logDir "$stamp.mobile.err.log") | Out-Null
}
Write-Output ("Updated backend ready, PID "+$updated.Id)
