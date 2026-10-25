(()=>{'use strict';
const original=window.fetch.bind(window);
const stationPage=location.pathname==='/worker';
const Auth=window.Auth={csrf:'',account:null,scope:'production',locked:false};
Auth.ready=(async()=>{const r=await original(stationPage?'/api/worker/session':'/api/auth/me',{cache:'no-store'});if(!r.ok){location.replace('/login'+'?next='+encodeURIComponent(location.pathname));throw Error('กรุณาเข้าสู่ระบบ');}const a=await r.json();Auth.account=a;Auth.csrf=a.csrf_token;const previous=sessionStorage.getItem('sopUserId');if(previous&&previous!==String(a.id)){sessionStorage.removeItem('workerPending');sessionStorage.removeItem('workerActive');}sessionStorage.setItem('sopUserId',String(a.id));return a;})();
let modeReady=Promise.resolve();
window.fetch=async(input,options={})=>{
 const url=new URL(typeof input==='string'?input:input.url,location.href);
 if(url.origin!==location.origin||!url.pathname.startsWith('/api/'))return original(input,options);
 await Auth.ready;
 const opts={...options},method=(opts.method||(input instanceof Request?input.method:'GET')).toUpperCase();
 const headers=new Headers(opts.headers||(input instanceof Request?input.headers:undefined));
 if(stationPage)headers.set('X-Worker-Mode','station');
 if(!['GET','HEAD','OPTIONS'].includes(method))headers.set('X-CSRF-Token',Auth.csrf);
 if(['/api/flow/start','/api/flow/lookup'].includes(url.pathname)&&typeof opts.body==='string'){
  await modeReady;const body=JSON.parse(opts.body);if(body.test_mode===undefined)body.test_mode=Auth.scope==='test';if(body.test_run_id===undefined)body.test_run_id=body.test_mode?localStorage.getItem('sopTestRun'):null;
  if(body.test_mode&&!body.test_run_id)throw Error('สร้างหรือเลือกรอบทดสอบก่อนสแกน');
  opts.body=JSON.stringify(body);
 }
 opts.headers=headers;
 const response=await original(input,opts);
 if(response.status===401&&!stationPage)location.assign('/login'+'?next='+encodeURIComponent(location.pathname));
 if(response.ok&&url.pathname==='/api/flow/start'){Auth.locked=true;lock();}
 if(response.ok&&/\/api\/flow\/(finish|abort)\//.test(url.pathname)){Auth.locked=false;lock();}
 return response;
};
function lock(){document.querySelectorAll('#workMode,#testRun,#newTestRun,#testLabel').forEach(e=>e.disabled=Auth.locked);}
const e=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
Auth.ready.then(async a=>{
 const bar=document.createElement('div');bar.className='session-bar';document.body.classList.add('authenticated');bar.innerHTML='<span><b>'+e(a.display_name||a.username)+'</b> · '+e(({admin:'ผู้ดูแลระบบ',supervisor:'หัวหน้างาน',qc:'ตรวจคุณภาพ',operator:'พนักงาน'})[a.role])+'</span><nav><a href="/worker">ตรวจงาน</a>'+(a.role!=='operator'?'<a href="/admin">รายงาน</a><a href="/access">พิจารณางาน / ผู้ใช้</a>':'')+'<button id="authLogout" type="button">ออกจากระบบ</button></nav>';document.body.prepend(bar);
 if(a.guest)bar.innerHTML='<span><b>หน้าพนักงาน</b> · เลือกสเตชั่นเพื่อเริ่มงาน</span><nav><a href="/login">แอดมิน / หัวหน้างาน ↗</a></nav>';
 if(!a.guest)document.getElementById('authLogout').onclick=async()=>{if(Auth.locked&&!confirm('มีงานกำลังตรวจอยู่ ออกจากระบบแล้วงานจะถูกแยกพักเมื่อขาดการเชื่อมต่อ ต้องการออกหรือไม่?'))return;await fetch('/api/auth/logout',{method:'POST'});location.assign('/login');};
 if(!a.guest)for(const id of ['operator','flowOperator']){const field=document.getElementById(id);if(field){field.value=a.username;field.readOnly=true;field.addEventListener('change',()=>field.value=a.username);}}
 if(a.role==='supervisor'){
  const nav=bar.querySelector('nav');nav.querySelectorAll('a').forEach(link=>link.remove());
  const link=document.createElement('a');link.href='/supervisor';link.textContent='หน้าหัวหน้างาน';nav.prepend(link);
 }
 if(a.role==='admin'){
  const link=document.createElement('a');link.href='/supervisor';link.textContent='หน้าหัวหน้างาน';bar.querySelector('nav').prepend(link);
 }
 if(!a.guest)localStorage.setItem('workerOperator',a.username);
 if(!['/worker','/'].includes(location.pathname))return;
 const panel=document.createElement('section');panel.className='mode-panel';panel.innerHTML='<label>โหมดงาน <select id="workMode"><option value="production">ผลิตจริง</option><option value="test">ทดสอบ · ไม่รวมยอดผลิต</option></select></label><div id="testOptions" hidden><label>รอบทดสอบ <select id="testRun"></select></label><input id="testLabel" maxlength="80" placeholder="ชื่อรอบทดสอบ"><button id="newTestRun" type="button">＋ สร้างรอบใหม่</button></div><small class="mode-note" id="modeHint">ไม่นับรอบทดสอบรวมกับยอดผลิต</small>';
 const target=document.querySelector('.worker-shell')||document.querySelector('main')||document.body;target.prepend(panel);
 const mode=document.getElementById('workMode'),run=document.getElementById('testRun'),opts=document.getElementById('testOptions'),hint=document.getElementById('modeHint');
 Auth.scope=localStorage.getItem('sopWorkMode')==='test'?'test':'production';mode.value=Auth.scope;
 const apply=()=>{Auth.scope=mode.value;localStorage.setItem('sopWorkMode',Auth.scope);opts.hidden=Auth.scope!=='test';panel.classList.toggle('is-test',Auth.scope==='test');hint.textContent=Auth.scope==='test'?'ทุกสเตชั่นต้องเลือกรอบเดียวกัน สร้างรอบใหม่เพื่อทดสอบ QR เดิมอีกครั้ง':'ไม่นับรอบทดสอบรวมกับยอดผลิต';window.dispatchEvent(new Event('workmodechange'));};
 async function runs(){const response=await fetch('/api/test-runs');if(!response.ok)throw Error('โหลดรอบทดสอบไม่สำเร็จ');const list=await response.json(),selected=localStorage.getItem('sopTestRun');run.innerHTML='<option value="">เลือกรอบทดสอบ</option>'+list.map(r=>'<option value="'+e(r.id)+'">'+e(r.label)+'</option>').join('');if(list.some(r=>r.id===selected))run.value=selected;else localStorage.removeItem('sopTestRun');}
 mode.onchange=apply;run.onchange=()=>localStorage.setItem('sopTestRun',run.value);
 document.getElementById('newTestRun').onclick=async()=>{try{const label=document.getElementById('testLabel').value.trim()||'ทดสอบ '+new Date().toLocaleString('th-TH');const response=await fetch('/api/test-runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({label})});if(!response.ok)throw Error('สร้างรอบไม่สำเร็จ');const created=await response.json();localStorage.setItem('sopTestRun',created.id);await runs();hint.textContent='สร้างรอบแล้ว เริ่มทดสอบที่สเตชั่น 1 ได้';}catch(err){hint.textContent=err.message;}};
 modeReady=runs().catch(err=>hint.textContent=err.message);apply();lock();
}).catch(()=>{});
})();
