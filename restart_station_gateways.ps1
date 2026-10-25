$ErrorActionPreference='Stop'
$projectDir=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectDir
$pythonExe=Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.15-64\python.exe'
& $pythonExe .brand-refresh/check_idle.py
if($LASTEXITCODE -ne 0){throw 'Work/camera active; do not restart gateways'}
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$logDir=Join-Path $projectDir 'backups/access-logs'
foreach($entry in @(@{Port=8001;Pattern='run_desktop_gateway.py';Script='run_desktop_gateway.py'},@{Port=8443;Pattern='run_mobile_gateway.py|start_mobile.py';Script='run_mobile_gateway.py'})){
 $gatewayId=(Get-NetTCPConnection -LocalPort $entry.Port -State Listen | Select-Object -First 1).OwningProcess
 $gateway=Get-CimInstance Win32_Process -Filter ("ProcessId="+$gatewayId)
 if(!$gateway -or $gateway.CommandLine -notmatch $entry.Pattern){throw 'Unexpected gateway process'}
 Stop-Process -Id $gatewayId -Force
 $updated=Start-Process -FilePath $pythonExe -ArgumentList $entry.Script -WorkingDirectory $projectDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir ("gateway-"+$entry.Port+"-$stamp.out.log")) -RedirectStandardError (Join-Path $logDir ("gateway-"+$entry.Port+"-$stamp.err.log"))
 Write-Output ("Updated gateway "+$entry.Port+": "+$updated.Id)
}
