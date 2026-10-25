from pathlib import Path
p=Path(__file__).resolve().parent/'reporting.py';s=p.read_text(encoding='utf-8')
s=s.replace("def conditions(q='', station_id=None, state='all', operator=None, since=None, until=None):","def conditions(q='', station_id=None, state='all', operator=None, since=None, until=None,scope='production'):")
s=s.replace("    where, params = [], []","""    where, params = [], []
    if scope not in ('production','test','all'):raise HTTPException(400,'โหมดข้อมูลไม่ถูกต้อง')
    if scope!='all':
        where.append('qr IN (SELECT qr FROM flow_jobs WHERE is_test=?)')
        params.append(int(scope=='test'))""",1)
s=s.replace("             limit=50, offset=0):","             limit=50, offset=0,scope='production'):")
s=s.replace('conditions(q, station_id, state, operator, since, until)','conditions(q, station_id, state, operator, since, until,scope)')
s=s.replace('global_stats = count_attempts(c)',"""production_clause,production_params=conditions()
        global_stats = count_attempts(c,production_clause,production_params)""")
s=s.replace("SELECT count(*) FROM flow_jobs'","SELECT count(*) FROM flow_jobs WHERE is_test=0'")
s=s.replace("SELECT qr FROM flow_attempts GROUP BY qr\n            HAVING","SELECT qr FROM flow_attempts WHERE qr IN (SELECT qr FROM flow_jobs WHERE is_test=0) GROUP BY qr\n            HAVING",1)
s=s.replace("sum(state IN ('blocked','interrupted'))=0","""sum(state IN ('blocked','interrupted') AND id NOT IN (
                SELECT attempt_id FROM supervisor_reviews WHERE decision='rework_approved'))=0""")
s=s.replace("'operator':operator, 'since':since, 'until':until}","'operator':operator, 'since':since, 'until':until,'scope':scope}")
s=s.replace('SELECT * FROM reports ORDER BY created_at DESC LIMIT ?',
            'SELECT * FROM reports WHERE qr IS NULL OR qr IN (SELECT qr FROM flow_jobs WHERE is_test=0) ORDER BY created_at DESC LIMIT ?')
s=s.replace('SELECT * FROM flow_attempts ORDER BY started_at DESC,rowid DESC LIMIT ?',
            'SELECT * FROM flow_attempts WHERE qr IN (SELECT qr FROM flow_jobs WHERE is_test=0) ORDER BY started_at DESC,rowid DESC LIMIT ?')
s=s.replace("yield [r['qr'],r['id']","yield [r.get('source_qr') or r['qr'],r['id']")
s=s.replace("r['video_url'] or '',reason(r)]","r['video_url'] or '',reason(r),r['qr'],'ทดสอบ' if r.get('test_mode') else 'ผลิตจริง',r.get('test_run_id') or '']")
s=s.replace("'ลิงก์วิดีโอ','เหตุผล/ข้อสังเกต']","'ลิงก์วิดีโอ','เหตุผล/ข้อสังเกต','รหัสงานภายใน','โหมด','รอบทดสอบ']")
s=s.replace("since: str | None = None, until: str | None = None):","since: str | None = None, until: str | None = None,scope: str = 'production'):")
s=s.replace('data=snapshot(q,station_id,state,operator,since,until,limit=None)','data=snapshot(q,station_id,state,operator,since,until,limit=None,scope=scope)')
s=s.replace("'until':'ถึง'}","'until':'ถึง','scope':'โหมด'}")
p.write_text(s,encoding='utf-8')
print('Reports exclude test work by default; explicit production/test/all filters share one model')
