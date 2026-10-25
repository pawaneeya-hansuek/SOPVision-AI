"""Export and UI data parity through real HTTP routes and isolated SQLite."""
import csv
import io
import json
from datetime import datetime, timezone, timedelta
import pytest
import db
import production
from test_production_flow import client

def seed(count=125, operator='EMP-REPORT'):
    start=datetime(2026,10,20,tzinfo=timezone.utc)
    with db.connect() as c:
        for n in range(count):
            qr=f'REPORT-{n:03}'
            state=['passed','blocked','interrupted','active'][n%4]
            at=(start+timedelta(minutes=n)).isoformat()
            result={'status':'pass' if state=='passed' else 'review','elapsed':1,
                    'verified':2 if state=='passed' else 0,'total':2,'issues':0 if state=='passed' else 2,
                    'steps':[], 'events':[], 'evidence':{}}
            station=production.station_for(1+n%3)
            c.execute('INSERT INTO flow_jobs(qr,created_at) VALUES(?,?)',(qr,at))
            c.execute("""INSERT INTO flow_attempts(id,qr,station_id,operator,state,started_at,ended_at,result_json,station_json,mime_type)
                         VALUES(?,?,?,?,?,?,?,?,?,?)""",
                      (f'id-{n:03}',qr,station['id'],operator,state,at,
                       None if state=='active' else at,json.dumps(result),json.dumps(station),'video/webm'))

def rows(response):
    assert response.status_code==200,response.text
    assert response.content.startswith(b'\xef\xbb\xbf')
    return list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))))

def test_exports_all_pages_and_has_matching_filtered_stats(client):
    seed()
    admin=client.get('/api/flow/admin',params={'limit':50}).json()
    data=rows(client.get('/api/flow/admin/export'))
    assert len(admin['attempts'])==50 and admin['total']==len(data)==125
    assert {r['รหัสรอบงาน'] for r in data}=={f'id-{n:03}' for n in range(125)}
    assert sum(r['state']=='passed' for r in data)==admin['filtered_stats']['passed']
    assert client.get('/api/stats').json()['production']==admin['stats']
    records=client.get('/api/records').json()
    assert len(records)==125
    assert sum(r['status']=='pass' for r in records)==admin['stats']['passed']
    for params in [{'station_id':2},{'state':'blocked'},{'q':'REPORT-01'},
                   {'operator':'EMP-REPORT','station_id':1,'state':'passed'}]:
        screen=client.get('/api/flow/admin',params=params).json()
        export=rows(client.get('/api/flow/admin/export',params=params))
        assert screen['total']==len(export)
        assert {r['id'] for r in screen['attempts']}=={r['รหัสรอบงาน'] for r in export}

def test_thai_dates_and_filters_are_shared_and_inclusive(client):
    seed(30)
    params={'since':'2026-10-20T07:10:00+07:00','until':'2026-10-20T07:20:00+07:00'}
    screen=client.get('/api/flow/admin',params=params).json()
    export=rows(client.get('/api/flow/admin/export',params=params))
    assert screen['total']==len(export)==11
    assert all(' +07:00' in r['เวลาเริ่ม (ไทย)'] for r in export)
    assert export[0]['เวลาเริ่ม (ไทย)']=='2026-10-20 07:20:00 +07:00'
    html=client.get('/api/flow/admin/export',params={**params,'format':'html'})
    assert html.status_code==200
    assert 'รอบงาน 11' in html.text
    assert '+07:00' in html.text and 'window.print()' in html.text
    assert html.headers['cache-control']=='no-store'

def test_export_sanitizes_excel_formulas_and_escapes_html(client):
    seed(1,operator='<script>alert(1)</script>')
    with db.connect() as c:c.execute("UPDATE flow_attempts SET operator=?",
                                                  ('=HYPERLINK("https://invalid.example")',))
    export=rows(client.get('/api/flow/admin/export'))
    assert export[0]['รหัสพนักงาน'].startswith("'=")
    with db.connect() as c:c.execute("UPDATE flow_attempts SET operator=?",('<script>alert(1)</script>',))
    html=client.get('/api/flow/admin/export',params={'format':'html'}).text
    assert '<script>alert(1)</script>' not in html
    assert '&lt;script&gt;' in html

def test_exact_worker_history_and_literal_search(client):
    seed(2,'EMP_1')
    with db.connect() as c:c.execute("UPDATE flow_attempts SET operator='EMP_10' WHERE id='id-001'")
    data=client.get('/api/flow/admin',params={'operator':'EMP_1','station_id':1}).json()
    assert data['total']==1 and data['attempts'][0]['id']=='id-000'
    assert len(rows(client.get('/api/flow/admin/export',params={'q':'%'})))==0

def test_invalid_filters_do_not_produce_misleading_exports(client):
    for params in [{'state':'no'},{'since':'not-a-date'},
                   {'since':'2026-10-21T00:00:00Z','until':'2026-10-20T00:00:00Z'},
                   {'since':'2026-10-21T00:00:00'}]:
        assert client.get('/api/flow/admin',params=params).status_code==400
        assert client.get('/api/flow/admin/export',params=params).status_code==400
    assert client.get('/api/flow/admin/export',params={'format':'xlsx'}).status_code==400
    assert client.get('/api/flow/admin/export',params={'station_id':999}).status_code==404

def test_empty_report_and_unified_modes_are_explicit(client):
    assert rows(client.get('/api/flow/admin/export'))==[]
    db.save_report('independent','upload','2026-10-20T00:00:00Z',
                   {'status':'pass','elapsed':1,'verified':2,'total':2,'issues':0,'steps':[]})
    data=client.get('/api/records').json()
    assert len(data)==1 and data[0]['source']=='inspection' and data[0]['mode']=='upload'
    assert client.get('/api/stats').json()['production']['total_attempts']==0
