$ErrorActionPreference='Stop'
$project='C:\Users\USER\Downloads\SOPVision-AI-QR-Production-Flow\SOPVision-AI'
Set-Location -LiteralPath $project
$python='C:\Users\USER\AppData\Local\Python\pythoncore-3.15-64\python.exe'
$health=Invoke-RestMethod 'http://127.0.0.1:8000/api/flow/admin'
if($health.stats.running -gt 0){throw 'Inspection is running. Deployment paused.'}
$processes=Get-CimInstance Win32_Process
$oldBackend=$processes|Where-Object {$_.ProcessId -eq 16776 -and $_.CommandLine -match 'uvicorn main:app' -and $_.CommandLine -match '--port 8000'}
if(-not $oldBackend){throw 'Backend process changed; inspect it before restarting.'}
# Only stop the known SOPVision uvicorn reloaders on the compatibility port.
$reloaders=@($processes|Where-Object {$_.Name -eq 'python.exe' -and $_.CommandLine -match '-m uvicorn main:app' -and $_.CommandLine -match '--port 8001'})
$parentIds=@($reloaders|ForEach-Object {$_.ProcessId})
$children=@($processes|Where-Object {$parentIds -contains $_.ParentProcessId})
foreach($p in $reloaders){Stop-Process -Id $p.ProcessId -ErrorAction SilentlyContinue}
foreach($p in $children){Stop-Process -Id $p.ProcessId -ErrorAction SilentlyContinue}
Stop-Process -Id $oldBackend.ProcessId
$logFolder=Join-Path $project 'backups\reporting-logs'
New-Item -ItemType Directory -Path $logFolder -Force|Out-Null
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$backend=Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','main:app','--host','127.0.0.1','--port','8000','--timeout-graceful-shutdown','5','--no-access-log') -WorkingDirectory $project -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logFolder "$stamp-backend.out.log") -RedirectStandardError (Join-Path $logFolder "$stamp-backend.err.log")
$ready=$false
for($i=0;$i -lt 30;$i++){
    try{$d=Invoke-RestMethod 'http://127.0.0.1:8000/api/stats';if($d.production){$ready=$true;break}}catch{}
    Start-Sleep -Milliseconds 200
}
if(-not $ready){throw 'New backend did not become ready; inspect the deployment log.'}
$gateway=Start-Process -FilePath $python -ArgumentList 'run_desktop_gateway.py' -WorkingDirectory $project -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logFolder "$stamp-gateway.out.log") -RedirectStandardError (Join-Path $logFolder "$stamp-gateway.err.log")
Write-Output "Updated backend PID $($backend.Id), compatibility gateway PID $($gateway.Id). HTTPS gateway was kept running."
