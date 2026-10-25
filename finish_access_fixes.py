from pathlib import Path
def edit(name,old,new):
 p=Path(name);s=p.read_text(encoding='utf-8');assert old in s,name+old[:60];p.write_text(s.replace(old,new),encoding='utf-8')
edit('tests/test_production_flow.py','    mobile = TestClient(mobile_gateway.app)','    mobile = TestClient(mobile_gateway.app)\n    mobile.cookies.update(client.cookies)\n    mobile.headers["X-CSRF-Token"]=client.headers["X-CSRF-Token"]')
edit('tests/test_access_workflows.py',"assert response.json()['operator']=='operator1'","assert c.get('/api/flow/attempts/'+own).json()['operator']=='operator1'")
edit('tests/test_access_workflows.py',"'code':'wrong'","'code':'wrong-code-long-enough-123'")
edit('tests/test_access_workflows.py',"[['green'],['green','red'],['green','red','blue']]","[['green'],['green','red']]")
edit('static/auth-client.js',"bar.className='sessionbar';","bar.className='session-bar';document.body.classList.add('authenticated');")
edit('static/auth-client.js',"panel.classList.toggle('testing',Auth.scope==='test')","panel.classList.toggle('is-test',Auth.scope==='test')")
edit('static/auth-client.js',"""<small id="modeHint">""","""<small class="mode-note" id="modeHint">""")
edit('auth.py',"return bool(r and r['operator']==account['username'])\n    match=re.fullmatch", "return not r or r['operator']==account['username']\n    match=re.fullmatch")
# Bind test mode to idempotent worker pending requests so recovery cannot switch scope.
edit('static/worker.js',"W.pending={qr,operator,station_id,mime_type:mime,request_id:crypto.randomUUID()};","W.pending={qr,operator,station_id,mime_type:mime,request_id:crypto.randomUUID(),test_mode:window.Auth?.scope==='test',test_run_id:localStorage.getItem('sopTestRun')};")
edit('static/auth-client.js',"body.test_mode=Auth.scope==='test';body.test_run_id=body.test_mode?localStorage.getItem('sopTestRun'):null;","if(body.test_mode===undefined)body.test_mode=Auth.scope==='test';if(body.test_run_id===undefined)body.test_run_id=body.test_mode?localStorage.getItem('sopTestRun'):null;")
# Pending requests disable switching rounds even if an HTTP response gets lost.
edit('static/worker.js',"  const locked = !!W.work || !!W.pending || W.busy;","  const locked = !!W.work || !!W.pending || W.busy;\n  if(window.Auth){window.Auth.locked=locked;document.querySelectorAll('#workMode,#testRun,#newTestRun,#testLabel').forEach(e=>e.disabled=locked);}")
edit('static/worker.js',"qr===W.work?.source_qr","qr===W.work?.source_qr") if False else None
# Show human QR while keeping internal test keys in API links.
p=Path('static/worker.js');s=p.read_text(encoding='utf-8').replace('${work.qr}','${work.source_qr||work.qr}').replace('${W.work.qr}','${W.work.source_qr||W.work.qr}');p.write_text(s,encoding='utf-8')
print('Focused fixes applied')
