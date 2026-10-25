$ErrorActionPreference='Stop'
$projectDir=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectDir
$pythonExe=Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.15-64\python.exe'
& $pythonExe .brand-refresh/check_idle.py
if($LASTEXITCODE -ne 0){throw 'Work/camera active; stop deployment'}
& $pythonExe backup_before_station_access.py
if($LASTEXITCODE -ne 0){throw 'Backup failed'}
$backendId=(Get-NetTCPConnection -LocalPort 8000 -State Listen | Select-Object -First 1).OwningProcess
$backend=Get-CimInstance Win32_Process -Filter ("ProcessId="+$backendId)
if(!$backend -or $backend.CommandLine -notmatch 'uvicorn main:app.*--port 8000'){throw 'Unexpected backend process'}
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$logDir=Join-Path $projectDir 'backups/access-logs'
Stop-Process -Id $backendId -Force
$updated=Start-Process -FilePath $pythonExe -ArgumentList '-m uvicorn main:app --host 127.0.0.1 --port 8000 --timeout-graceful-shutdown 5 --no-access-log' -WorkingDirectory $projectDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir "station-$stamp.out.log") -RedirectStandardError (Join-Path $logDir "station-$stamp.err.log")
$ready=$false
for($n=0;$n -lt 30;$n++){
 try{$health=Invoke-RestMethod 'http://127.0.0.1:8000/api/health' -TimeoutSec 2;if($health.ok){$ready=$true;break}}catch{}
 Start-Sleep -Milliseconds 250
}
if(!$ready){throw 'Backend did not become ready'}
Write-Output ("Station access backend ready: "+$updated.Id)
& $pythonExe -c "import webbrowser;webbrowser.open('http://127.0.0.1:8000/worker')"
