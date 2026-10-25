"""Password-free worker browser sessions, limited to owned station work."""
from __future__ import annotations
import secrets
from datetime import datetime,timedelta,timezone
from fastapi import Request,HTTPException
from fastapi.responses import JSONResponse
import db

COOKIE='sopvision_worker'
def initialize_schema(c):
    c.execute("""CREATE TABLE IF NOT EXISTS worker_browser_sessions(
      token_hash TEXT PRIMARY KEY, owner_id INTEGER NOT NULL UNIQUE,
      operator_key TEXT NOT NULL UNIQUE, csrf_token TEXT NOT NULL, expires_at TEXT NOT NULL)""")
def session(request):
    import auth
    token=request.cookies.get(COOKIE)
    if not token:return None
    with db.connect() as c:
        row=c.execute('SELECT * FROM worker_browser_sessions WHERE token_hash=? AND expires_at>?',
                      (auth.digest(token),auth.now())).fetchone()
    if not row:return None
    return {'id':row['owner_id'],'username':row['operator_key'],'display_name':'หน้าพนักงาน',
            'role':'operator','guest':True,'csrf_token':row['csrf_token'],'expires_at':row['expires_at']}
def operator_for(actor,station_id):
    if actor.get('guest'):
        if station_id not in (1,2,3):raise HTTPException(400,'เลือกสเตชั่น 1–3 ก่อนเปิดกล้องหรือเริ่มงาน')
        return actor['username']+'-S'+str(station_id)
    return actor['username']
def owns(actor,operator):
    if actor.get('guest'):return operator in [operator_for(actor,n) for n in (1,2,3)]
    return operator==actor['username']
def bootstrap(request:Request):
    import auth
    account=session(request)
    if account:return JSONResponse(account,headers={'Cache-Control':'no-store'})
    token=secrets.token_urlsafe(32);key='STATION-'+secrets.token_hex(8)
    csrf=secrets.token_urlsafe(32);owner=-(secrets.randbits(60)+1)
    expires=(datetime.now(timezone.utc)+timedelta(hours=24)).isoformat(timespec='seconds')
    with db.connect() as c:
        c.execute('DELETE FROM worker_browser_sessions WHERE expires_at<=?',(auth.now(),))
        c.execute('INSERT INTO worker_browser_sessions VALUES(?,?,?,?,?)',(auth.digest(token),owner,key,csrf,expires))
    response=JSONResponse({'id':owner,'username':key,'display_name':'หน้าพนักงาน','role':'operator',
                           'guest':True,'csrf_token':csrf,'expires_at':expires})
    secure=request.url.scheme=='https' or request.headers.get('x-forwarded-proto')=='https'
    response.set_cookie(COOKIE,token,max_age=86400,httponly=True,samesite='strict',secure=secure,path='/')
    response.headers['Cache-Control']='no-store'
    return response
