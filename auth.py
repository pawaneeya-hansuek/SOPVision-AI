"""Password/session authentication and server-side authorization. No default passwords."""
from __future__ import annotations
import contextvars
import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
import db

ROOT=Path(__file__).resolve().parent
router=APIRouter(tags=['Authentication'])
ROLE_NAMES={'admin':'ผู้ดูแลระบบ','supervisor':'หัวหน้างาน','qc':'ผู้ตรวจคุณภาพ','operator':'พนักงาน'}
CURRENT=contextvars.ContextVar('sopvision_user',default=None)
COOKIE='sopvision_session'

def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def user():return CURRENT.get()
def setup_path():return Path(db.DB).with_suffix('.admin-setup-code')
def digest(token):return hashlib.sha256(token.encode()).hexdigest()
def password_hash(password):
    salt=secrets.token_bytes(16)
    value=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,600000)
    return 'pbkdf2_sha256$600000$'+salt.hex()+'$'+value.hex()
def verify_password(password,encoded):
    try:
        _,iterations,salt,value=encoded.split('$')
        actual=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),int(iterations)).hex()
        return hmac.compare_digest(actual,value)
    except (ValueError,TypeError):return False

def initialize_schema(c):
    import station_access
    station_access.initialize_schema(c)
    c.execute("""CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
      password_hash TEXT NOT NULL, role TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS auth_sessions(
      token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
      csrf_token TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS auth_login_failures(
      bucket TEXT NOT NULL, happened_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS security_audit(
      id INTEGER PRIMARY KEY, actor_id INTEGER, event TEXT NOT NULL,
      target TEXT, detail TEXT, happened_at TEXT NOT NULL)""")
    if not c.execute('SELECT 1 FROM users WHERE role=?',('admin',)).fetchone() and not setup_path().exists():
        setup_path().write_text(secrets.token_urlsafe(32),encoding='utf-8')

def audit(c,event,target='',detail=''):
    actor=user()
    c.execute('INSERT INTO security_audit(actor_id,event,target,detail,happened_at) VALUES(?,?,?,?,?)',
              (actor['id'] if actor else None,event,str(target),detail,now()))

def session(request):
    token=request.cookies.get(COOKIE)
    if not token:return None
    with db.connect() as c:
        row=c.execute("""SELECT u.id,u.username,u.display_name,u.role,u.enabled,
          s.csrf_token,s.expires_at FROM auth_sessions s JOIN users u ON u.id=s.user_id
          WHERE s.token_hash=? AND s.expires_at>? AND u.enabled=1""",(digest(token),now())).fetchone()
    return dict(row) if row else None

def create_session(response,request,account):
    token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
    expires=(datetime.now(timezone.utc)+timedelta(hours=8)).isoformat(timespec='seconds')
    with db.connect() as c:
        c.execute('DELETE FROM auth_sessions WHERE expires_at<=?',(now(),))
        c.execute('INSERT INTO auth_sessions VALUES(?,?,?,?,?)',(digest(token),account['id'],csrf,expires,now()))
    secure=request.url.scheme=='https' or request.headers.get('x-forwarded-proto')=='https'
    response.set_cookie(COOKIE,token,max_age=28800,httponly=True,secure=secure,samesite='strict',path='/')
    return csrf

class Credentials(BaseModel):
    username:str=Field(min_length=1,max_length=80)
    password:str=Field(min_length=1,max_length=200)
class Setup(Credentials):
    code:str=Field(min_length=20,max_length=100)
    display_name:str=Field(default='ผู้ดูแลระบบ',min_length=1,max_length=100)
class NewUser(Credentials):
    display_name:str=Field(min_length=1,max_length=100)
    role:str
class UserState(BaseModel):
    enabled:bool

def validate_new(username,password):
    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,80}',username):
        raise HTTPException(400,'ชื่อบัญชีใช้ A–Z, 0–9, จุด ขีด หรือขีดล่าง 3–80 ตัว')
    if len(password)<10:raise HTTPException(400,'ใช้รหัสผ่านอย่างน้อย 10 ตัวอักษร')
def public_account(row):
    return {k:row[k] for k in ('id','username','display_name','role')}

@router.get('/login')
def login_page():return FileResponse(ROOT/'static/login.html')
@router.get('/supervisor/login')
def old_supervisor_login():return RedirectResponse('/login',status_code=303)
@router.get('/setup')
def setup_page():return FileResponse(ROOT/'static/login.html')
@router.get('/api/auth/status')
def status():
    with db.connect() as c:configured=bool(c.execute("SELECT 1 FROM users WHERE role='admin'").fetchone())
    return {'configured':configured}
@router.get('/api/auth/me')
def me(request:Request):
    account=session(request)
    if not account:raise HTTPException(401,'กรุณาเข้าสู่ระบบ')
    return {**public_account(account),'csrf_token':account['csrf_token'],'expires_at':account['expires_at']}

@router.post('/api/auth/setup')
def setup(body:Setup,request:Request):
    validate_new(body.username,body.password)
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():raise HTTPException(409,'ตั้งค่าบัญชีผู้ดูแลแล้ว')
        if not setup_path().is_file() or not hmac.compare_digest(body.code,setup_path().read_text(encoding='utf-8').strip()):
            raise HTTPException(403,'รหัสตั้งค่าไม่ถูกต้อง')
        c.execute('INSERT INTO users(username,display_name,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                  (body.username,body.display_name,password_hash(body.password),'admin',now()))
        account=dict(c.execute('SELECT * FROM users WHERE username=?',(body.username,)).fetchone())
        audit(c,'first_admin_created',account['id'])
    setup_path().unlink(missing_ok=True)
    response=JSONResponse(public_account(account))
    create_session(response,request,account)
    return response

@router.post('/api/auth/login')
def login(body:Credentials,request:Request):
    bucket=digest((request.client.host if request.client else '')+'|'+body.username.lower())
    cutoff=(datetime.now(timezone.utc)-timedelta(minutes=15)).isoformat(timespec='seconds')
    with db.connect() as c:
        c.execute('DELETE FROM auth_login_failures WHERE happened_at<?',(cutoff,))
        failures=c.execute('SELECT count(*) FROM auth_login_failures WHERE bucket=?',(bucket,)).fetchone()[0]
        if failures>=10:raise HTTPException(429,'ลองเข้าสู่ระบบมากเกินไป กรุณารอ 15 นาที')
        row=c.execute('SELECT * FROM users WHERE username=?',(body.username,)).fetchone()
    valid=verify_password(body.password,row['password_hash']) if row else verify_password(body.password,
        'pbkdf2_sha256$600000$'+'00'*16+'$'+'00'*32)
    if not row or not row['enabled'] or not valid:
        with db.connect() as c:c.execute('INSERT INTO auth_login_failures VALUES(?,?)',(bucket,now()))
        raise HTTPException(401,'ชื่อบัญชีหรือรหัสผ่านไม่ถูกต้อง')
    with db.connect() as c:
        c.execute('DELETE FROM auth_login_failures WHERE bucket=?',(bucket,))
        audit(c,'login',row['id'])
    home='/supervisor' if row['role']=='supervisor' else '/worker' if row['role']=='operator' else '/admin'
    response=JSONResponse({**public_account(row),'home':home});create_session(response,request,row)
    return response

@router.post('/api/auth/logout')
def logout(request:Request):
    with db.connect() as c:
        c.execute('DELETE FROM auth_sessions WHERE token_hash=?',(digest(request.cookies.get(COOKIE,'')),))
        audit(c,'logout')
    response=JSONResponse({'ok':True});response.delete_cookie(COOKIE,path='/')
    return response

@router.get('/api/users')
def users():
    with db.connect() as c:return [dict(r) for r in c.execute('SELECT id,username,display_name,role,enabled,created_at FROM users ORDER BY id')]
@router.post('/api/users')
def add_user(body:NewUser):
    validate_new(body.username,body.password)
    if body.role not in ROLE_NAMES:raise HTTPException(400,'บทบาทไม่ถูกต้อง')
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT 1 FROM users WHERE username=?',(body.username,)).fetchone():raise HTTPException(409,'ชื่อบัญชีนี้มีแล้ว')
        cur=c.execute('INSERT INTO users(username,display_name,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                      (body.username,body.display_name,password_hash(body.password),body.role,now()))
        audit(c,'user_created',cur.lastrowid,body.role)
    return {'id':cur.lastrowid,'username':body.username,'role':body.role}
@router.patch('/api/users/{uid}')
def user_state(uid:int,body:UserState):
    actor=user()
    if actor and actor['id']==uid and not body.enabled:raise HTTPException(409,'ปิดบัญชีตนเองไม่ได้')
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        target=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
        if not target:raise HTTPException(404,'ไม่พบบัญชี')
        if target['role']=='admin' and not body.enabled and c.execute("SELECT count(*) FROM users WHERE role='admin' AND enabled=1").fetchone()[0]<=1:
            raise HTTPException(409,'ต้องเหลือบัญชีแอดมินที่เปิดใช้งานอย่างน้อยหนึ่งบัญชี')
        c.execute('UPDATE users SET enabled=? WHERE id=?',(body.enabled,uid))
        if not body.enabled:c.execute('DELETE FROM auth_sessions WHERE user_id=?',(uid,))
        audit(c,'user_enabled' if body.enabled else 'user_disabled',uid)
    return {'ok':True}

@router.get('/api/worker/session')
def worker_session(request:Request):
    import station_access
    return station_access.bootstrap(request)

def owns_operator(account,operator):
    import station_access
    return station_access.owns(account,operator)

def owner_attempt(account,sid):
    if account['role']!='operator':return True
    with db.connect() as c:r=c.execute('SELECT operator FROM flow_attempts WHERE id=?',(sid,)).fetchone()
    return bool(r and owns_operator(account,r['operator']))

def operator_allowed(path,method,account):
    if path in ('/worker','/api/auth/me','/api/auth/logout','/api/health','/api/flow/stations',
                '/api/flow/lookup','/api/flow/start','/api/flow/my-history','/api/qr/decode','/api/test-runs'):
        return True
    if path.startswith('/api/flow/requests/'):
        with db.connect() as c:r=c.execute('SELECT operator FROM flow_attempts WHERE request_id=?',(path.rsplit('/',1)[-1],)).fetchone()
        return not r or owns_operator(account,r['operator'])
    match=re.fullmatch(r'/api/flow/(?:frame|recording|finish|abort|attempts)/([^/]+)(?:/\d+)?',path)
    if match:return owner_attempt(account,match.group(1))
    if path=='/api/cameras/open':return method=='POST'
    match=re.match(r'/api/cameras/([^/]+)(?:/|$)',path)
    if match and match.group(1) not in ('archive','events'):
        with db.connect() as c:r=c.execute('SELECT owner_id FROM camera_sessions WHERE id=?',(match.group(1),)).fetchone()
        return bool(r and r['owner_id']==account['id'])
    if path.startswith('/media/'):
        name=path.rsplit('/',1)[-1]
        with db.connect() as c:
            if account.get('guest'):
                from station_access import operator_for
                attempts=c.execute('SELECT id,video_url,frame_url,result_json FROM flow_attempts WHERE operator IN (?,?,?)',tuple(operator_for(account,n) for n in (1,2,3))).fetchall()
            else:
                attempts=c.execute('SELECT id,video_url,frame_url,result_json FROM flow_attempts WHERE operator=?',(account['username'],)).fetchall()
        for r in attempts:
            if name and (name==Path(r['video_url'] or '').name or name==Path(r['frame_url'] or '').name):return True
            evidence=json.loads(r['result_json'] or '{}').get('evidence',{})
            if name in [Path(v).name for v in evidence.values() if isinstance(v,str)]:return True
        return False
    return False

def supervisor_allowed(path, method):
    if method in ('GET','HEAD'):
        if path in ('/supervisor','/api/auth/me','/api/health','/api/reviews',
                    '/api/supervisor/recordings','/api/cameras/archive'):
            return True
        if re.fullmatch(r'/api/cameras/[a-zA-Z0-9_-]+/segments/\d+/video',path):
            return True
        if path.startswith('/media/'):
            # Permit only actual archived video URLs, never images or arbitrary files.
            with db.connect() as c:
                return bool(c.execute('''SELECT 1 FROM flow_attempts WHERE video_url=? AND ended_at IS NOT NULL
                    UNION ALL SELECT 1 FROM reports WHERE video_url=? LIMIT 1''',(path,path)).fetchone())
    return method=='POST' and (path in ('/api/auth/logout','/api/supervisor/qr/decode') or bool(re.fullmatch(r'/api/reviews/[^/]+/decision',path)))


def install(app):
    app.include_router(router)
    @app.middleware('http')
    async def authentication(request,call_next):
        path=request.url.path;method=request.method
        public=path in ('/worker','/api/worker/session','/login','/supervisor/login','/setup','/api/auth/login','/api/auth/setup','/api/auth/status','/api/health') or path.startswith('/static/')
        account=None if public else session(request)
        if path in ('/worker','/api/worker/session'):
            signed_in=session(request)
            if signed_in and signed_in['role']=='supervisor':
                if path=='/worker':return RedirectResponse('/supervisor',status_code=303)
                return JSONResponse({'detail':'บัญชีหัวหน้างานใช้หน้าหัวหน้างานเท่านั้น'},status_code=403)
        station_mode=request.headers.get('x-worker-mode')=='station'
        beacon=bool(re.fullmatch(r'/api/flow/abort/[^/]+',path) or re.fullmatch(r'/api/cameras/[^/]+/close',path))
        if not station_mode and beacon and method=='POST':
            try:station_mode=(await request.json()).get('worker_mode')=='station'
            except (ValueError,TypeError):pass
        if not public and (station_mode or not account) and not (account and account['role']=='supervisor'):
            import station_access
            guest=station_access.session(request)
            if guest:account=guest
            elif station_mode:account=None
        if account and account.get('guest') and path in ('/api/auth/me','/api/auth/logout'):
            return JSONResponse({'detail':'เฉพาะบัญชีที่เข้าสู่ระบบ'},status_code=403)
        if not public and not account:
            if path.startswith('/api/') or path.startswith('/media/'):return JSONResponse({'detail':'กรุณาเข้าสู่ระบบ'},status_code=401)
            return RedirectResponse('/login?next='+__import__('urllib.parse',fromlist=['quote']).quote(path),status_code=303)
        if account:
            role=account['role']
            if role=='supervisor':
                if path in ('/','/admin','/access'):
                    return RedirectResponse('/supervisor',status_code=303)
                if not supervisor_allowed(path,method):
                    return JSONResponse({'detail':'หัวหน้างานอนุญาตสแกนซ้ำและดูวิดีโอย้อนหลังได้เท่านั้น'},status_code=403)
            if account.get('guest') and path in ('/admin','/access'):
                return RedirectResponse('/login?next='+path,status_code=303)
            if role=='operator' and path=='/':return RedirectResponse('/worker',status_code=303)
            if path.startswith('/api/users') and role!='admin':return JSONResponse({'detail':'เฉพาะผู้ดูแลระบบ'},status_code=403)
            if path in ('/access',) and role not in ('admin','supervisor','qc'):return RedirectResponse('/worker',status_code=303)
            if role=='operator' and not operator_allowed(path,method,account):
                return JSONResponse({'detail':'ไม่มีสิทธิ์เข้าถึงข้อมูลนี้'},status_code=403)
            if role=='qc' and method not in ('GET','HEAD','OPTIONS') and path!='/api/auth/logout' and not re.fullmatch(r'/api/reviews/[^/]+/decision',path) and not re.fullmatch(r'/api/flow/attempts/[^/]+/ai-review',path):
                return JSONResponse({'detail':'QC อ่านผลและพิจารณาแยกพักได้เท่านั้น'},status_code=403)
            if method not in ('GET','HEAD','OPTIONS'):
                if ('/config' in path or path=='/api/steps') and role!='admin':
                    return JSONResponse({'detail':'เฉพาะแอดมินแก้ไข SOP ได้'},status_code=403)
                csrf=request.headers.get('x-csrf-token','')
                # Unload beacons cannot attach custom headers; accept JSON body token.
                if not csrf and (re.fullmatch(r'/api/flow/abort/[^/]+',path) or re.fullmatch(r'/api/cameras/[^/]+/close',path)):
                    try:csrf=(await request.json()).get('csrf','')
                    except (ValueError,TypeError):pass
                if not hmac.compare_digest(csrf,account['csrf_token']):
                    return JSONResponse({'detail':'คำขอหมดอายุหรือไม่มี CSRF token กรุณาโหลดหน้าใหม่'},status_code=403)
        token=CURRENT.set(account)
        try:
            response=await call_next(request)
            if not path.startswith('/static/'):response.headers['Cache-Control']='no-store'
            response.headers['X-Content-Type-Options']='nosniff'
            response.headers['X-Frame-Options']='SAMEORIGIN'
            response.headers['Referrer-Policy']='same-origin'
            return response
        finally:CURRENT.reset(token)
