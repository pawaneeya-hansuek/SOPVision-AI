"""Canonical production read model and exports; never changes inspection results."""
from __future__ import annotations
import csv
import io
from datetime import datetime, timezone, timedelta
from html import escape
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import HTMLResponse
import db

router = APIRouter(prefix='/api/flow', tags=['Production reports'])
STATES = {'active':'กำลังทำ', 'passed':'ผ่านสเตชั่น', 'blocked':'แยกพัก', 'interrupted':'หยุดกลางงาน'}
TH = timezone(timedelta(hours=7))

def timestamp(value):
    if value is None or value == '':
        return None
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            raise ValueError()
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        raise HTTPException(400, 'วันเวลาต้องมีเขตเวลา เช่น +07:00 หรือ Z')

def conditions(q='', station_id=None, state='all', operator=None, since=None, until=None,scope='production'):
    from production import station_for
    if station_id is not None: station_for(station_id)
    if state not in ('all', *STATES): raise HTTPException(400, 'สถานะไม่ถูกต้อง')
    since, until = timestamp(since), timestamp(until)
    if since and until and datetime.fromisoformat(since) > datetime.fromisoformat(until):
        raise HTTPException(400, 'เวลาเริ่มต้องไม่เกินเวลาสิ้นสุด')
    where, params = [], []
    if scope not in ('production','test','all'):raise HTTPException(400,'โหมดข้อมูลไม่ถูกต้อง')
    if scope!='all':
        where.append('qr IN (SELECT qr FROM flow_jobs WHERE is_test=?)')
        params.append(int(scope=='test'))
    if q.strip():
        literal = q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        where.append("(qr LIKE ? ESCAPE '\\' OR operator LIKE ? ESCAPE '\\' OR id LIKE ? ESCAPE '\\' OR qr IN (SELECT qr FROM flow_jobs WHERE source_qr LIKE ? ESCAPE '\\'))")
        params.extend(['%' + literal + '%'] * 4)
    if station_id is not None: where.append('station_id=?'); params.append(station_id)
    if state != 'all': where.append('state=?'); params.append(state)
    if operator is not None: where.append('operator=?'); params.append(operator)
    if since: where.append('julianday(started_at)>=julianday(?)'); params.append(since)
    if until: where.append('julianday(started_at)<=julianday(?)'); params.append(until)
    return (' WHERE ' + ' AND '.join(where) if where else ''), params

def count_attempts(c, clause='', params=()):
    return dict(c.execute("""SELECT count(*) total_attempts,
        coalesce(sum(ended_at IS NULL),0) running,
        coalesce(sum(state='passed'),0) passed,
        coalesce(sum(state IN ('blocked','interrupted')),0) quarantined,
        count(DISTINCT qr) total_jobs FROM flow_attempts""" + clause, params).fetchone())

def snapshot(q='', station_id=None, state='all', operator=None, since=None, until=None,
             limit=50, offset=0,scope='production'):
    from production import STATIONS, station_for, display_attempt
    clause, params = conditions(q, station_id, state, operator, since, until,scope)
    with db.connect() as c:
        c.execute('BEGIN')
        production_clause,production_params=conditions()
        global_stats = count_attempts(c,production_clause,production_params)
        global_stats['total_jobs'] = c.execute('SELECT count(*) FROM flow_jobs WHERE is_test=0').fetchone()[0]
        global_stats['completed_jobs'] = c.execute("""SELECT count(*) FROM (
            SELECT qr FROM flow_attempts WHERE qr IN (SELECT qr FROM flow_jobs WHERE is_test=0) GROUP BY qr
            HAVING count(DISTINCT CASE WHEN state='passed' THEN station_id END)=?
            AND sum(state IN ('blocked','interrupted') AND id NOT IN (
                SELECT attempt_id FROM supervisor_reviews WHERE decision='rework_approved'))=0)""", (len(STATIONS),)).fetchone()[0]
        filtered_stats = count_attempts(c, clause, params)
        filtered_stats['completed_jobs'] = c.execute("""SELECT count(*) FROM (
            SELECT DISTINCT f.qr FROM flow_attempts f JOIN (
                SELECT qr FROM flow_attempts GROUP BY qr
                HAVING count(DISTINCT CASE WHEN state='passed' THEN station_id END)=?
                AND sum(state IN ('blocked','interrupted') AND id NOT IN (
                SELECT attempt_id FROM supervisor_reviews WHERE decision='rework_approved'))=0
            ) done ON done.qr=f.qr WHERE f.id IN (
                SELECT id FROM flow_attempts""" + clause + '))',
            [len(STATIONS), *params]).fetchone()[0]
        suffix = ' ORDER BY started_at DESC, rowid DESC'
        if limit is not None:
            suffix += ' LIMIT ? OFFSET ?'
            query_params = [*params, limit, offset]
        else:
            # Never silently truncate an export.
            suffix += ' LIMIT 50001'
            query_params = params
        rows = [dict(r) for r in c.execute('SELECT * FROM flow_attempts' + clause + suffix, query_params)]
        if limit is None and len(rows) > 50000:
            raise HTTPException(413, 'รายงานเกิน 50,000 รายการ กรุณาจำกัดช่วงเวลา')
        running_clause = clause + (' AND ' if clause else ' WHERE ') + 'ended_at IS NULL'
        running = [dict(r) for r in c.execute('SELECT * FROM flow_attempts' + running_clause + ' ORDER BY started_at DESC, rowid DESC', params)]
    return {'generated_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'stats':global_stats, 'filtered_stats':filtered_stats,
            'total':filtered_stats['total_attempts'], 'offset':offset, 'limit':limit,
            'filters':{'q':q.strip(), 'station_id':station_id, 'state':state,
                       'operator':operator, 'since':since, 'until':until,'scope':scope},
            'attempts':[display_attempt(r) for r in rows],
            'stations':[{**station_for(s['id']),
                         'running':[display_attempt(dict(r)) for r in running if r['station_id']==s['id']]}
                        for s in STATIONS]}

def inspection_records(limit=50000):
    """Independent inspections and production attempts stay distinct; links are explicit."""
    from production import display_attempt
    with db.connect() as c:
        c.execute('BEGIN')
        reports = [dict(r) for r in c.execute('SELECT * FROM reports WHERE qr IS NULL OR qr NOT IN (SELECT qr FROM flow_jobs WHERE is_test=1) ORDER BY created_at DESC LIMIT ?', (limit+1,))]
        attempts = [display_attempt(dict(r)) for r in c.execute(
            'SELECT * FROM flow_attempts WHERE qr IN (SELECT qr FROM flow_jobs WHERE is_test=0) ORDER BY started_at DESC,rowid DESC LIMIT ?', (limit+1,))]
    rows = []
    for r in reports:
        r['source']='inspection'; r['record_key']=r['id']
        r['result'] = __import__('json').loads(r.pop('result_json') or '{}')
        rows.append(r)
    for r in attempts:
        result=r['result']
        status='pass' if r['state']=='passed' else ('running' if r['state']=='active' else 'review')
        rows.append({'id':r['id'], 'record_key':'flow:'+r['id'], 'source':'production',
            'mode':'flow', 'created_at':r['started_at'], 'status':status, 'state':r['state'],
            'qr':r['qr'], 'station_id':r['station_id'], 'operator':r['operator'],
            'verified':result.get('verified',0), 'total':result.get('total',len(r['station']['steps']))})
    if len(rows)>limit:raise HTTPException(413,'ประวัติเกิน 50,000 รายการ กรุณาใช้หน้าแอดมินกรองช่วงเวลา')
    return sorted(rows,key=lambda r:r['created_at'],reverse=True)

def thai_time(value):
    if not value:return ''
    dt=datetime.fromisoformat(value.replace('Z','+00:00'))
    if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TH).strftime('%Y-%m-%d %H:%M:%S +07:00')

def reason(r):
    result=r['result']
    messages=[result.get(k) for k in ('error','recording_error','completion_error') if result.get(k)]
    messages.extend(s.get('name','')+': '+s.get('reason',s.get('status',''))
                    for s in result.get('steps',[]) if s.get('status')!='passed')
    return ' | '.join(dict.fromkeys(messages))

def export_rows(data):
    for r in data['attempts']:
        result=r['result']
        yield [r.get('source_qr') or r['qr'],r['id'],r['station_id'],r['station']['name'],r['operator'],
               STATES[r['state']],r['state'],thai_time(r['started_at']),thai_time(r['ended_at']),
               result.get('verified',0),result.get('total',len(r['station']['steps'])),
               r['station'].get('version',0),r['recorded_bytes'],r['recorded_chunks'],
               'มีไฟล์' if r['recording_available'] else 'ไม่มีไฟล์',r['video_url'] or '',reason(r),r['qr'],'ทดสอบ' if r.get('test_mode') else 'ผลิตจริง',r.get('test_run_id') or '',r.get('rework_of') or '',(r.get('review') or {}).get('decision') or '',(r.get('review') or {}).get('reviewer') or '',(r.get('review') or {}).get('reason') or '']

HEADERS=['QR งาน','รหัสรอบงาน','สเตชั่น','ชื่อสเตชั่น','รหัสพนักงาน','สถานะ','state',
         'เวลาเริ่ม (ไทย)','เวลาจบ (ไทย)','ขั้นตอนผ่าน','ขั้นตอนทั้งหมด','SOP version',
         'ขนาดวิดีโอ (bytes)','จำนวนส่วนวิดีโอ','ไฟล์วิดีโอ','ลิงก์วิดีโอ','เหตุผล/ข้อสังเกต','รหัสงานภายใน','โหมด','รอบทดสอบ','ตรวจซ้ำจากรอบงาน','ผลพิจารณา','ผู้พิจารณา','เหตุผลการพิจารณา']

def safe_cell(value):
    if value is None:return ''
    if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')):
        return "'" + value
    if isinstance(value,str) and value.startswith(('\t','\r','\n')):
        return "'" + value
    return value

@router.get('/admin/export')
def export_report(format: str = 'csv', q: str = Query(default='',max_length=300),
                  station_id: int | None = None, state: str = 'all',
                  operator: str | None = Query(default=None,max_length=80),
                  since: str | None = None, until: str | None = None,scope: str = 'production'):
    if format not in ('csv','html'):raise HTTPException(400,'รองรับ csv หรือ html')
    data=snapshot(q,station_id,state,operator,since,until,limit=None,scope=scope)
    filename='SOPVision-production-'+datetime.now(TH).strftime('%Y%m%d-%H%M%S')
    headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
             'X-Report-Total':str(data['total'])}
    if format=='csv':
        buf=io.StringIO(newline='');writer=csv.writer(buf)
        writer.writerow(HEADERS)
        for row in export_rows(data):writer.writerow([safe_cell(v) for v in row])
        headers['Content-Disposition']='attachment; filename="'+filename+'.csv"'
        return Response(content=('\ufeff'+buf.getvalue()).encode('utf-8'),
                        media_type='text/csv; charset=utf-8',headers=headers)
    e=lambda v:escape(str(v if v is not None else ''),quote=True)
    labels={'q':'คำค้น','station_id':'สเตชั่น','state':'สถานะ','operator':'พนักงาน','since':'ตั้งแต่','until':'ถึง','scope':'โหมด'}
    filters=' · '.join(e(labels[k])+': '+e(v) for k,v in data['filters'].items() if v not in (None,'','all')) or 'ทั้งหมด'
    s=data['filtered_stats']
    body=''.join('<tr>'+''.join('<td>'+e(v)+'</td>' for v in row)+'</tr>' for row in export_rows(data))
    # Embed the current logo so saved/printed reports retain the same brand offline.
    from pathlib import Path
    from base64 import b64encode
    logo_data=b64encode((Path(__file__).parent/'static/brand/sopvision-logo-current.png').read_bytes()).decode('ascii')
    report_brand='<img alt="SOPVision AI — Intelligent Inspection" width="220" height="73" style="display:block;object-fit:contain;margin:0 0 16px" src="data:image/png;base64,'+logo_data+'">'
    html='''<!doctype html><html lang="th"><meta charset="utf-8">
    <title>รายงานงานผลิต SOPVision</title><style>
    body{font:14px Tahoma,sans-serif;color:#20324a;margin:28px}h1{font-size:24px}
    table{border-collapse:collapse;width:100%;font-size:10px;overflow-wrap:anywhere}
    th,td{border:1px solid #ccd5df;padding:6px;text-align:left}th{background:#edf3ff}
    thead{display:table-header-group}tr{break-inside:avoid}button{padding:10px 18px}
    @page{size:A4 landscape;margin:10mm}@media print{button{display:none}body{margin:0}}
    </style><button onclick="window.print()">พิมพ์ / บันทึก PDF</button>
    <h1>SOPVision · รายงานงานผลิต</h1>'''
    html=html.replace('<h1>',report_brand+'<h1>',1)
    html+='<p>สร้างเมื่อ '+e(thai_time(data['generated_at']))+'</p><p>ตัวกรอง: '+filters+'</p>'
    html+='<p>รอบงาน '+str(data['total'])+' · ผ่านสเตชั่น '+str(s['passed'])+' · แยกพัก/หยุด '+str(s['quarantined'])+' · กำลังทำ/ปิดงาน '+str(s['running'])+'</p>'
    html+='<p>เป็นผลตรวจที่บันทึกไว้ ข้อมูลใหม่หลังเวลาสร้างรายงานไม่เปลี่ยนรายงานฉบับนี้</p>'
    html+='<table><thead><tr>'+''.join('<th>'+e(h)+'</th>' for h in HEADERS)+'</tr></thead><tbody>'+body+'</tbody></table></html>'
    return HTMLResponse(html,headers=headers)
