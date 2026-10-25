from pathlib import Path
from datetime import datetime
import shutil
root=Path(__file__).parent
backup=root/'backups'/('station-access-'+datetime.now().strftime('%Y%m%d-%H%M%S'));backup.mkdir(parents=True)
for file in ('auth.py','production.py','cameras.py','workflows.py','static/auth-client.js','static/worker.js','static/worker.html','static/login.html'):
    dst=backup/file;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/file,dst)
def edit(file,old,new,count=1):
    p=root/file;s=p.read_text(encoding='utf-8')
    assert s.count(old)==count,(file,old[:60],s.count(old))
    p.write_text(s.replace(old,new),encoding='utf-8')
edit('auth.py',"def initialize_schema(c):","def initialize_schema(c):\n    import station_access\n    station_access.initialize_schema(c)")
edit('auth.py',"def owner_attempt(account,sid):","""@router.get('/api/worker/session')
def worker_session(request:Request):
    import station_access
    return station_access.bootstrap(request)

def owns_operator(account,operator):
    import station_access
    return station_access.owns(account,operator)

def owner_attempt(account,sid):""")
edit('auth.py',"return bool(r and r['operator']==account['username'])","return bool(r and owns_operator(account,r['operator']))")
edit('auth.py',"return not r or r['operator']==account['username']","return not r or owns_operator(account,r['operator'])")
edit('auth.py',"""attempts=c.execute('SELECT id,video_url,frame_url,result_json FROM flow_attempts WHERE operator=?',(account['username'],)).fetchall()""","""if account.get('guest'):
                from station_access import operator_for
                attempts=c.execute('SELECT id,video_url,frame_url,result_json FROM flow_attempts WHERE operator IN (?,?,?)',tuple(operator_for(account,n) for n in (1,2,3))).fetchall()
            else:
                attempts=c.execute('SELECT id,video_url,frame_url,result_json FROM flow_attempts WHERE operator=?',(account['username'],)).fetchall()""")
edit('auth.py',"'publicplaceholder'","'publicplaceholder'") if False else None
edit('auth.py',"('/login','/setup','/api/auth/login','/api/auth/setup','/api/auth/status','/api/health')","('/worker','/api/worker/session','/login','/setup','/api/auth/login','/api/auth/setup','/api/auth/status','/api/health')")
edit('auth.py',"        account=None if public else session(request)","""        account=None if public else session(request)
        station_mode=request.headers.get('x-worker-mode')=='station'
        beacon=bool(re.fullmatch(r'/api/flow/abort/[^/]+',path) or re.fullmatch(r'/api/cameras/[^/]+/close',path))
        if not station_mode and beacon and method=='POST':
            try:station_mode=(await request.json()).get('worker_mode')=='station'
            except (ValueError,TypeError):pass
        if not public and (station_mode or not account):
            import station_access
            guest=station_access.session(request)
            if guest:account=guest
            elif station_mode:account=None
        if account and account.get('guest') and path in ('/api/auth/me','/api/auth/logout'):
            return JSONResponse({'detail':'เฉพาะบัญชีที่เข้าสู่ระบบ'},status_code=403)""")
edit('production.py',"if actor and actor['role']!='admin':operator=actor['username']","""if actor and actor['role']!='admin':
        from station_access import operator_for
        operator=operator_for(actor,body.station_id)""")
edit('cameras.py',"if actor and actor['role']!='admin':body=body.model_copy(update={'operator':actor['username']})","""if actor and actor['role']!='admin':
        from station_access import operator_for
        body=body.model_copy(update={'operator':operator_for(actor,body.station_id)})""")
edit('workflows.py',"actor['id'] if actor else None","actor['id'] if actor and not actor.get('guest') else None")
edit('workflows.py',"data=snapshot(operator=actor['username'],station_id=station_id,limit=15,scope=scope)","""from station_access import operator_for
    data=snapshot(operator=operator_for(actor,station_id),station_id=station_id,limit=15,scope=scope)""")
edit('static/auth-client.js',"const Auth=window.Auth=","const stationPage=location.pathname==='/worker';\nconst Auth=window.Auth=")
edit('static/auth-client.js',"original('/api/auth/me',{cache:'no-store'})","original(stationPage?'/api/worker/session':'/api/auth/me',{cache:'no-store'})")
edit('static/auth-client.js',"if(!['GET','HEAD','OPTIONS'].includes(method))headers.set","if(stationPage)headers.set('X-Worker-Mode','station');\n if(!['GET','HEAD','OPTIONS'].includes(method))headers.set")
edit('static/auth-client.js',"if(response.status===401)location.assign","if(response.status===401&&!stationPage)location.assign")
edit('static/auth-client.js'," document.getElementById('authLogout').onclick=",""" if(a.guest)bar.innerHTML='<span><b>หน้าพนักงาน</b> · เลือกสเตชั่นแล้วเริ่มตรวจงานได้เลย</span><nav><a href="/login">แอดมิน / หัวหน้างาน ↗</a></nav>';
 if(!a.guest)document.getElementById('authLogout').onclick=""")
edit('static/auth-client.js'," for(const id of ['operator','flowOperator'])"," if(!a.guest)for(const id of ['operator','flowOperator'])")
edit('static/auth-client.js'," localStorage.setItem('workerOperator',a.username);"," if(!a.guest)localStorage.setItem('workerOperator',a.username);")
edit('static/worker.js',"  $('stationTitle').textContent=station.name;","  $('stationTitle').textContent=station.name;\n  if(window.Auth?.account?.guest){$('operator').value='STATION-'+station.id;localStorage.setItem('workerOperator',$('operator').value);}")
edit('static/worker.js',"'พนักงาน '+operator+' · สถานี '","'สถานี '")
# Previous replacement removes the operator segment but preserves the station expression.
edit('static/worker.js',"csrf:window.Auth?.csrf||''","csrf:window.Auth?.csrf||'',worker_mode:'station'")
edit('static/camera-share.js',"csrf:window.Auth?.csrf||'',error:","csrf:window.Auth?.csrf||'',worker_mode:location.pathname==='/worker'?'station':undefined,error:",2)
edit('static/worker.html','<label>รหัสพนักงาน<input','<label hidden>รหัสสถานี<input')
edit('static/worker.html','เลือกสถานี ระบุพนักงาน แล้วเปิดกล้องเพื่อรอสแกน QR','เลือกสถานี แล้วเปิดกล้องเพื่อรอสแกน QR')
edit('static/worker.html','<a href="/">กลับหน้าหลัก ↗</a>','<a href="/login">เข้าสำหรับแอดมิน ↗</a>')
for file in ('index.html','worker.html','admin.html','access.html'):
    edit('static/'+file,'auth-client.js?v=access-1','auth-client.js?v=station-5')
edit('static/worker.html','worker.js?v=reports-4','worker.js?v=station-5')
edit('static/worker.html','camera-share.js?v=traceability-3','camera-share.js?v=station-5')
edit('static/index.html','camera-share.js?v=traceability-3','camera-share.js?v=station-5')
edit('static/login.html','<form id="loginForm"','<a class="auth-link worker-entry" href="/worker">หน้าพนักงาน · เลือกสเตชั่นแล้วเริ่มงาน ↗</a><form id="loginForm"')
print('Station access and worker UI updated.')
