from pathlib import Path
from datetime import datetime, timezone
import shutil
root=Path(__file__).resolve().parent
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
backup=root/'backups'/('reporting-'+stamp)
backup.mkdir(parents=True)
for name in ['production.py','main.py','static/admin.html','static/admin.js','static/app.js','static/index.html','static/worker.js','reporting.py']:
    target=backup/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/name,target)
def edit(name,fn):
    path=root/name;old=path.read_text(encoding='utf-8');new=fn(old)
    if old==new:raise RuntimeError('No change: '+name)
    path.write_text(new,encoding='utf-8')
def once(s,old,new):
    if s.count(old)!=1:raise RuntimeError('Expected one match: '+old[:90])
    return s.replace(old,new,1)
def production(s):
    pos=s.index("@router.get('/admin')\n")
    return s[:pos]+'''@router.get('/admin')
def admin_snapshot(response: Response, q: str = Query(default='', max_length=300),
                   station_id: int | None = None, state: str = 'all',
                   limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
                   operator: str | None = Query(default=None, max_length=80),
                   since: str | None = None, until: str | None = None):
    from reporting import snapshot
    response.headers['Cache-Control'] = 'no-store'
    return snapshot(q,station_id,state,operator,since,until,limit,offset)
'''
edit('production.py',production)
def main(s):
    s=once(s,'app.include_router(production_router)',"app.include_router(production_router)\nfrom reporting import router as reporting_router\napp.include_router(reporting_router)")
    s=once(s,"def stats(): return {'stats':db.stats(), 'reports':db.get_reports(6)}",'''def stats():
    from reporting import snapshot, inspection_records
    data=snapshot(limit=6)
    return {'stats':db.stats(), 'reports':inspection_records()[:6],
            'production':data['stats'], 'generated_at':data['generated_at']}

@app.get('/api/records')
def unified_records():
    from reporting import inspection_records
    return inspection_records()
''')
    return s
edit('main.py',main)
def reporting(s):
    s=once(s,'def inspection_records(limit=1000):','def inspection_records(limit=50000):')
    s=s.replace('(limit,))]', '(limit+1,))]')
    s=once(s,"    return sorted(rows,key=lambda r:r['created_at'],reverse=True)[:limit]","    if len(rows)>limit:raise HTTPException(413,'ประวัติเกิน 50,000 รายการ กรุณาใช้หน้าแอดมินกรองช่วงเวลา')\n    return sorted(rows,key=lambda r:r['created_at'],reverse=True)")
    return s
edit('reporting.py',reporting)
def adminhtml(s):
    s=once(s,'<button class="btn btn-outline" id="refresh">รีเฟรชข้อมูล</button>','<div class="hero-actions"><button class="btn btn-outline" id="refresh">รีเฟรชข้อมูล</button><button class="btn btn-accent" id="exportCsv">ส่งออก CSV / Excel</button><button class="btn btn-outline" id="exportPrint">รายงาน / PDF</button></div>')
    anchor='<select id="stateFilter"'
    i=s.index(anchor);end=s.index('</select>',i)+len('</select>')
    s=s[:end]+'''<label>ตั้งแต่ (เวลาไทย)<input id="sinceFilter" class="flow-input" type="datetime-local"></label><label>ถึง (เวลาไทย)<input id="untilFilter" class="flow-input" type="datetime-local"></label>'''+s[end:]
    s=once(s,'<div id="stats" class="admin-stats"></div>','<p class="admin-note" id="productionScope">ยอดงานผลิตและรายงานใช้ตัวกรองเดียวกัน · ส่งออกครบทุกหน้าของรายการที่ตรงตัวกรอง</p><div id="stats" class="admin-stats"></div>')
    s=s.replace('v=traceability-3','v=reports-4')
    return s
edit('static/admin.html',adminhtml)
def adminjs(s):
    s=once(s,'const s=data.stats;','const s=data.filtered_stats||data.stats;')
    s=once(s,"[['ชิ้นงานทั้งหมด',s.total_jobs]","[['รอบงานทั้งหมด',s.total_attempts],['ชิ้นงานทั้งหมด',s.total_jobs]")
    start=s.index('    const params=new URLSearchParams({q:')
    end=s.index("    const data=await api('/api/flow/admin?'+params);",start)
    s=s[:start]+"    const params=productionFilters();params.set('limit',A.limit);params.set('offset',A.offset);\n"+s[end:]
    s=once(s,"$('search').oninput=filter;$('stationFilter').onchange=filter;$('stateFilter').onchange=filter;","$('search').oninput=filter;$('stationFilter').onchange=filter;$('stateFilter').onchange=filter;\n$('sinceFilter').onchange=filter;$('untilFilter').onchange=filter;")
    s+='''

function productionFilters(){
  const params=new URLSearchParams({q:$('search').value,state:$('stateFilter').value});
  if($('stationFilter').value)params.set('station_id',$('stationFilter').value);
  for(const [id,key] of [['sinceFilter','since'],['untilFilter','until']]){
    if($(id).value)params.set(key,new Date($(id).value+':00+07:00').toISOString());
  }
  return params;
}
let exporting=false;
async function exportProduction(format){
  if(exporting)return;
  const params=productionFilters();params.set('format',format);
  const since=params.get('since'),until=params.get('until');
  if(since&&until&&since>until){$('sync').textContent='เวลาเริ่มต้องไม่เกินเวลาสิ้นสุด';return;}
  // Open synchronously to avoid popup blockers; HTML is generated by the backend.
  if(format==='html'){
    window.open('/api/flow/admin/export?'+params,'_blank','noopener');
    return;
  }
  exporting=true;$('exportCsv').disabled=true;
  try{
    const response=await fetch('/api/flow/admin/export?'+params,{cache:'no-store',signal:AbortSignal.timeout(60000)});
    if(!response.ok){const error=await response.json();throw Error(error.detail||'ส่งออกไม่สำเร็จ');}
    const blob=await response.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');
    a.href=url;a.download='SOPVision-production-'+new Date().toISOString().slice(0,10)+'.csv';
    document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
    $('sync').textContent='ส่งออกแล้ว '+response.headers.get('X-Report-Total')+' รอบงาน ครบทุกหน้าที่ตรงกับตัวกรอง';
  }catch(e){$('sync').className='worker-message bad';$('sync').textContent='ส่งออกไม่สำเร็จ: '+e.message;}
  finally{exporting=false;$('exportCsv').disabled=false;}
}
$('exportCsv').onclick=()=>exportProduction('csv');
$('exportPrint').onclick=()=>exportProduction('html');
'''
    return s
edit('static/admin.js',adminjs)
def index(s):
    for old,new in [('การตรวจทั้งหมด</span>','ชิ้นงานทั้งหมด</span>'),('ผ่านลำดับ SOP</span>','รอบงานผ่านสถานี</span>'),('ต้องตรวจสอบ</span>','รอบงานแยกพัก / หยุด</span>'),('อัตราผ่าน</span>','ชิ้นงานจบครบ</span>'),('<small>%</small>',''),('TOTAL INSPECTIONS','PRODUCTION JOBS'),('VERIFIED ASSEMBLIES','PASSED STATION ATTEMPTS'),('FLAGGED INSPECTIONS','QUARANTINED ATTEMPTS'),('PASS RATE','COMPLETED JOBS')]:
        s=once(s,old,new)
    s=once(s,'placeholder="ค้นหารหัสรายงาน…"','placeholder="ค้น QR / พนักงาน / รหัสรายงาน…"')
    s=once(s,'<option value="review">ต้องตรวจสอบ</option></select><select id="reportMode"','<option value="review">ต้องตรวจสอบ</option><option value="running">กำลังทำ</option></select><select id="reportMode"')
    s=once(s,'<option value="upload">วิดีโอย้อนหลัง</option>','<option value="upload">วิดีโอย้อนหลัง</option><option value="flow">งานผลิต QR</option>')
    s=once(s,'<th>ID</th><th>วันที่ตรวจ','<th>QR / รหัสรายงาน</th><th>วันที่ตรวจ')
    s=once(s,'<div class="stats-grid" id="statsGrid">','<p class="subtitle">ยอดงานผลิตรวมทุกสถานี ตรงกับหน้าแอดมินเมื่อไม่ใช้ตัวกรอง · ประวัติด้านล่างแยกรอบงาน QR กับการตรวจอิสระ</p><div class="stats-grid" id="statsGrid">')
    s=s.replace('src="/static/app.js"','src="/static/app.js?v=reports-4"')
    return s
edit('static/index.html',index)
def app(s):
    s=once(s,"let r=await fetch(url,opt)","let r=await fetch(url,{cache:'no-store',...opt})")
    start=s.index('async function refreshStats(){');end=s.index('function renderReports(){',start)
    s=s[:start]+'''async function refreshStats(){try{
 const {production,reports}=await api('/api/stats');
 $('statTotal').textContent=thaiNum(production.total_jobs);
 $('statPass').textContent=thaiNum(production.passed);
 $('statReview').textContent=thaiNum(production.quarantined);
 $('statRate').textContent=thaiNum(production.completed_jobs);
 $('recentList').innerHTML=reports.length?reports.map(r=>`<div class="recent-item" data-open-report="${escapeHTML(r.record_key||r.id)}"><div class="mode-icon blue">${ICON(r.mode==='flow'?'zap':r.mode==='live'?'camera':'upload')}</div><div><b>${escapeHTML(r.mode==='flow'?'งานผลิต QR · '+r.qr:r.mode==='live'?'ตรวจสดอิสระ':'วิดีโออิสระ')}</b><small>${timeDate(r.created_at)}</small></div><span class="mini-status ${r.status==='pass'?'pass':'review'}">${r.status==='pass'?'ผ่าน':r.status==='running'?'กำลังทำ':'ต้องตรวจสอบ'}</span></div>`).join(''):'<div class="empty-mini">ยังไม่มีประวัติ</div>';
 }catch(e){toast(e.message,true)}}
''' +s[end:]
    start=s.index('function renderReports(){');end=s.index('async function refreshReports()',start)
    s=s[:start]+'''function renderReports(){
 const query=$('reportSearch').value.trim().toLowerCase(),status=$('reportStatus').value,mode=$('reportMode').value;
 const rows=APP.results.filter(r=>[r.id,r.qr,r.operator].some(v=>String(v||'').toLowerCase().includes(query))&&(status==='all'||r.status===status)&&(mode==='all'||r.mode===mode));
 $('reportCount').textContent='แสดง '+rows.length+' / '+APP.results.length+' รายการ (งาน QR และการตรวจอิสระ)';
 $('reportRows').innerHTML=rows.length?rows.map(r=>`<tr data-open-report="${escapeHTML(r.record_key||r.id)}" tabindex="0" role="button" aria-label="เปิดรายงาน ${escapeHTML(r.id)}"><td>${escapeHTML(r.qr||'ไม่ผูก QR')}<small style="display:block">${escapeHTML(r.id.slice(0,8))}</small></td><td>${escapeHTML(timeDate(r.created_at))}</td><td>${r.mode==='flow'?'งาน QR · สถานี '+r.station_id:r.mode==='live'?'ตรวจสดอิสระ':'วิดีโออิสระ'}</td><td><span class="mini-status ${r.status==='pass'?'pass':'review'}">${r.status==='pass'?'ผ่าน':r.status==='running'?'กำลังทำ':'ต้องตรวจสอบ'}</span></td><td>${r.verified}/${r.total}</td><td>${ICON('chevron')}</td></tr>`).join(''):'<tr><td colspan="6" class="empty-table">ไม่พบรายงาน</td></tr>';
}
''' +s[end:]
    s=once(s,"APP.results=await api('/api/reports')","APP.results=await api('/api/records')")
    s=once(s,"async function openReport(id){try{const r=await api('/api/reports/'+id);","""async function openReport(id){try{let r;if(id.startsWith('flow:')){const d=await api('/api/flow/attempts/'+encodeURIComponent(id.slice(5)));r={...d,mode:'flow',created_at:d.started_at,status:d.state==='passed'?'pass':'review',video_url:d.recording_available?d.video_url:null};}else{r=await api('/api/reports/'+encodeURIComponent(id));}""")
    s=once(s,"r.mode==='live'?'กล้องสด':'ไฟล์วิดีโอ'","r.mode==='flow'?'งานผลิต QR · '+escapeHTML(r.qr)+' · สถานี '+r.station_id:r.mode==='live'?'กล้องสด':'ไฟล์วิดีโอ'")
    s=once(s,'<button class="btn btn-outline" id="reviewAI" data-review="${escapeHTML(id)}">','<button class="btn btn-outline" id="reviewAI" data-review="${escapeHTML(id)}">')
    return s
# The unchanged review button is intentionally handled by its route below.
# Drop the no-op replacement above before applying the transform.
import inspect
# app() contains a no-op once() that is harmless: replace() preserves the text.
edit('static/app.js',app)
print('Updated reporting sources; backups:',backup)
