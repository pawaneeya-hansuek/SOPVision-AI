from pathlib import Path
ROOT=Path(__file__).parent
def change(name,old,new,count=1):
 p=ROOT/name;s=p.read_text(encoding='utf-8');n=s.count(old)
 if n!=count:raise RuntimeError(f'{name}: expected {count}, found {n}: {old[:70]}')
 p.write_text(s.replace(old,new),encoding='utf-8')
change('static/camera-share.js',"JSON.stringify({token:this.token,error:","JSON.stringify({token:this.token,csrf:window.Auth?.csrf||'',error:",2)
change('mobile_gateway.py','headers = httpx.Headers(request.headers.raw)','headers = httpx.Headers(request.headers.raw)\n    headers[\'x-forwarded-proto\'] = request.url.scheme')
# QC reads evidence and may reject a review; only admin/supervisor can operate production outside worker.
change('auth.py',"            if method not in ('GET','HEAD','OPTIONS'):\n","            if role=='qc' and method not in ('GET','HEAD','OPTIONS') and path!='/api/auth/logout' and not re.fullmatch(r'/api/reviews/[^/]+/decision',path) and not re.fullmatch(r'/api/flow/attempts/[^/]+/ai-review',path):\n                return JSONResponse({'detail':'QC อ่านผลและพิจารณาแยกพักได้เท่านั้น'},status_code=403)\n            if method not in ('GET','HEAD','OPTIONS'):\n")
# Whitespace-only reasons are not audit evidence.
change('workflows.py',"    actor=staff()\n    if body.decision","    actor=staff()\n    if len(body.reason.strip())<10:raise HTTPException(400,'กรุณาระบุเหตุผลอย่างน้อย 10 ตัวอักษร')\n    if body.decision")
# Put the selected report scope in queries and exports using the same filters.
change('static/admin.html','<select id="stateFilter"','<select id="scopeFilter" aria-label="ประเภทงาน"><option value="production">ผลิตจริง</option><option value="test">ทดสอบ</option><option value="all">ทั้งหมด</option></select><select id="stateFilter"')
change('static/admin.js',"$('sinceFilter').onchange=filter;","$('scopeFilter').onchange=filter;$('sinceFilter').onchange=filter;")
change('static/admin.js',"const params=new URLSearchParams({q:$('search').value,state:$('stateFilter').value});","const params=new URLSearchParams({q:$('search').value,state:$('stateFilter').value,scope:$('scopeFilter').value});")
p=ROOT/'static/admin.js';s=p.read_text(encoding='utf-8').replace('esc(r.qr)','esc(r.source_qr||r.qr)').replace('esc(d.qr)','esc(d.source_qr||d.qr)');p.write_text(s,encoding='utf-8')
print('UI and security wiring complete')
