$ErrorActionPreference='Stop'
$projectDir=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectDir
$pythonExe=Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.15-64\python.exe'
$mainId=(Get-NetTCPConnection -LocalPort 8000 -State Listen | Select-Object -First 1).OwningProcess
$mainProc=Get-CimInstance Win32_Process -Filter ("ProcessId="+$mainId)
if(!$mainProc -or $mainProc.CommandLine -notmatch 'uvicorn main:app.*--port 8000'){throw 'Main process changed; inspect before restarting'}
$openCount=& $pythonExe -c "import db,sqlite3;connection=sqlite3.connect(db.DB);print(connection.execute('SELECT count(*) FROM flow_attempts WHERE ended_at IS NULL').fetchone()[0]);connection.close()"
if($LASTEXITCODE -ne 0){throw 'Could not check open work'}
if([int]$openCount -ne 0){throw 'Work is active; deployment stopped'}
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$logDir=Join-Path $projectDir 'backups\access-logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Stop-Process -Id $mainId -Force
$mainNew=Start-Process -FilePath $pythonExe -ArgumentList '-m uvicorn main:app --host 127.0.0.1 --port 8000 --timeout-graceful-shutdown 5 --no-access-log' -WorkingDirectory $projectDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir "main-$stamp.out.log") -RedirectStandardError (Join-Path $logDir "main-$stamp.err.log")
$ready=$false
for($n=0;$n -lt 30;$n++){try{$health=Invoke-RestMethod 'http://127.0.0.1:8000/api/auth/status' -TimeoutSec 2;if($null -ne $health.configured){$ready=$true;break}}catch{};Start-Sleep -Milliseconds 250}
if(!$ready){throw 'New backend did not become ready; inspect logs'}
foreach($entry in @(@{Port=8001;Pattern='run_desktop_gateway.py'},@{Port=8443;Pattern='run_mobile_gateway.py|start_mobile.py'})){
 $gatewayId=(Get-NetTCPConnection -LocalPort $entry.Port -State Listen | Select-Object -First 1).OwningProcess
 $proc=Get-CimInstance Win32_Process -Filter ("ProcessId="+$gatewayId)
 if(!$proc -or $proc.CommandLine -notmatch $entry.Pattern){throw 'Gateway process changed; inspect before restarting'}
 Stop-Process -Id $gatewayId -Force
}
$desktopNew=Start-Process -FilePath $pythonExe -ArgumentList 'run_desktop_gateway.py' -WorkingDirectory $projectDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir "desktop-$stamp.out.log") -RedirectStandardError (Join-Path $logDir "desktop-$stamp.err.log")
$mobileNew=Start-Process -FilePath $pythonExe -ArgumentList 'run_mobile_gateway.py' -WorkingDirectory $projectDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir "mobile-$stamp.out.log") -RedirectStandardError (Join-Path $logDir "mobile-$stamp.err.log")
Write-Output ("Backend PID "+$mainNew.Id+"; Desktop gateway PID "+$desktopNew.Id+"; Mobile gateway PID "+$mobileNew.Id)
