from pathlib import Path
p=Path('static/auth-client.js');s=p.read_text(encoding='utf-8')
old="Auth.account=a;Auth.csrf=a.csrf_token;return a;"
new="Auth.account=a;Auth.csrf=a.csrf_token;const previous=sessionStorage.getItem('sopUserId');if(previous&&previous!==String(a.id)){sessionStorage.removeItem('workerPending');sessionStorage.removeItem('workerActive');}sessionStorage.setItem('sopUserId',String(a.id));return a;"
assert old in s;s=s.replace(old,new);p.write_text(s,encoding='utf-8')
p=Path('deploy_access.ps1');s=p.read_text(encoding='utf-8')
s=s.replace('$mainProc=Get-CimInstance Win32_Process -Filter "ProcessId=31960"','$mainId=(Get-NetTCPConnection -LocalPort 8000 -State Listen | Select-Object -First 1).OwningProcess\n$mainProc=Get-CimInstance Win32_Process -Filter ("ProcessId="+$mainId)')
s=s.replace("import db;print(db.connect().execute('SELECT count(*) FROM flow_attempts WHERE ended_at IS NULL').fetchone()[0])","import db,sqlite3;connection=sqlite3.connect(db.DB);print(connection.execute('SELECT count(*) FROM flow_attempts WHERE ended_at IS NULL').fetchone()[0]);connection.close()")
s=s.replace('if([int]$openCount -ne 0)',"if($LASTEXITCODE -ne 0){throw 'Could not check open work'}\nif([int]$openCount -ne 0)")
s=s.replace('Stop-Process -Id 31960 -Force','Stop-Process -Id $mainId -Force')
s=s.replace("@{Id=27992;Pattern='run_desktop_gateway.py'},@{Id=348;Pattern='start_mobile.py'}","@{Port=8001;Pattern='run_desktop_gateway.py'},@{Port=8443;Pattern='run_mobile_gateway.py|start_mobile.py'}")
s=s.replace('$proc=Get-CimInstance Win32_Process -Filter ("ProcessId="+$entry.Id)','$gatewayId=(Get-NetTCPConnection -LocalPort $entry.Port -State Listen | Select-Object -First 1).OwningProcess\n $proc=Get-CimInstance Win32_Process -Filter ("ProcessId="+$gatewayId)')
s=s.replace('Stop-Process -Id $entry.Id -Force','Stop-Process -Id $gatewayId -Force')
p.write_text(s,encoding='utf-8')
print('Final UI/session guard and reusable deployment check saved')
