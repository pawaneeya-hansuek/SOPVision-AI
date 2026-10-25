'use strict';
const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const A={busy:false,offset:0,limit:50,total:0,revision:0,selected:null,detailKey:null};
const states={active:'กำลังทำ',passed:'ผ่านสเตชั่น',blocked:'แยกพัก',interrupted:'หยุดกลางงาน'};
const steps={passed:'ผ่าน',pending:'รอตรวจ',missing:'ขาดขั้นตอน',out_of_order:'ผิดลำดับ',uncertain:'ลำดับไม่ชัด'};
const date=s=>s?new Date(/(?:Z|[+-]\d\d:\d\d)$/.test(s)?s:s.replace(' ','T')+'Z').toLocaleString('th-TH',{timeZone:'Asia/Bangkok'}):'—';
async function api(url){const r=await fetch(url,{cache:'no-store',signal:AbortSignal.timeout(15000)});const data=await r.json();if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'อ่านข้อมูลไม่สำเร็จ');return data;}
const badge=r=>`<span class="admin-tag ${esc(r.state)}">${esc(states[r.state]||r.state)}${!r.ended_at&&r.state==='blocked'?' · กำลังปิดงาน':''}</span>`;
const bytes=n=>n==null?'ไม่ระบุขนาด':`${(Number(n)/1024/1024).toFixed(2)} MB`;
const chunks=n=>n==null?'ไม่ระบุจำนวนส่วน':`${n} ส่วน`;
function render(data){
  const s=data.filtered_stats||data.stats;
  $('stats').innerHTML=[['รอบงานทั้งหมด',s.total_attempts],['ชิ้นงานทั้งหมด',s.total_jobs],['กำลังทำ / กำลังปิดงาน',s.running],['รอบงานผ่านสเตชั่น',s.passed],['รอบงานแยกพัก / หยุด',s.quarantined],['ชิ้นงานผ่านครบทุกสเตชั่น',s.completed_jobs]].map(([label,n])=>`<div class="admin-stat"><span>${esc(label)}</span><strong>${Number(n).toLocaleString('th-TH')}</strong></div>`).join('');
  $('stations').innerHTML=data.stations.map(st=>`<article class="admin-station"><h3>${esc(st.name)}</h3>${st.running.length?st.running.map(r=>`<div class="admin-running">${r.frame_url?`<img src="${esc(r.frame_url)}?v=${encodeURIComponent(r.updated_at||'')}" alt="ภาพล่าสุดของ ${esc(r.source_qr||r.qr)}" onerror="this.hidden=true">`:'<div class="admin-empty-video">รอภาพแรกจากพนักงาน</div>'}<strong>${esc(r.source_qr||r.qr)}</strong><small>พนักงาน ${esc(r.operator)} · ${date(r.started_at)}</small><div>${badge(r)} · ${r.result.verified||0}/${r.result.total||r.station.steps.length} ขั้นตอน</div><div class="admin-progress"><i style="width:${Math.min(100,100*(r.result.verified||0)/(r.result.total||1))}%"></i></div><small>ข้อมูลล่าสุด ${date(r.updated_at)} · วิดีโอ ${bytes(r.recorded_bytes)}</small><button class="btn btn-outline" data-detail="${esc(r.id)}">ดูงานนี้</button></div>`).join(''):'<div class="admin-idle">ไม่มีชิ้นงานที่กำลังทำในขณะนี้</div>'}</article>`).join('');
  $('rows').innerHTML=data.attempts.length?data.attempts.map(r=>`<tr><td>${esc(r.source_qr||r.qr)}<small>${esc(r.id)}</small></td><td>${r.station_id}</td><td>${esc(r.operator)}</td><td>${badge(r)}<small>${r.result.verified||0}/${r.result.total||r.station.steps.length} ขั้นตอน</small></td><td>${date(r.started_at)}</td><td>${bytes(r.recorded_bytes)}<small>${chunks(r.recorded_chunks)} · ${r.video_url?(r.recording_available?'มีวิดีโอ':'ไม่พบไฟล์วิดีโอ'):r.ended_at?'ไม่มีวิดีโอสำเร็จ':'กำลังรับข้อมูล'}</small></td><td><button class="btn btn-outline" data-detail="${esc(r.id)}">ดูรายละเอียด</button></td></tr>`).join(''):'<tr><td colspan="7" class="empty-table">ไม่พบรายการงานที่ตรงกับตัวกรอง</td></tr>';
  A.total=data.total;$('rowCount').textContent=`${data.total} รายการที่ตรงกับตัวกรอง`;
  $('page').textContent=data.total?`${A.offset+1}–${Math.min(A.offset+A.limit,data.total)} / ${data.total}`:'0 รายการ';
  $('prev').disabled=A.offset===0;$('next').disabled=A.offset+A.limit>=data.total;
  $('sync').className='worker-message good';$('sync').textContent='เชื่อมต่อฐานข้อมูลแล้ว · ข้อมูลล่าสุด '+date(data.generated_at);
}
async function detail(id,force=false){
  try{
    const d=await api('/api/flow/attempts/'+encodeURIComponent(id));
    if(A.selected!==id)return;
    const key=JSON.stringify(d);if(!force&&key===A.detailKey)return;A.detailKey=key;
    const r=d.result||{};
    $('detailContent').innerHTML=`<div class="admin-detail-grid"><div><dl><dt>QR ชิ้นงาน</dt><dd>${esc(d.source_qr||d.qr)}</dd><dt>รหัสรายการ</dt><dd>${esc(d.id)}</dd><dt>สเตชั่น</dt><dd>${esc(d.station.name)}</dd><dt>พนักงาน</dt><dd>${esc(d.operator)}</dd><dt>ผล</dt><dd>${badge(d)}</dd><dt>เริ่มงาน</dt><dd>${date(d.started_at)}</dd><dt>ปิดงาน</dt><dd>${date(d.ended_at)}</dd><dt>วิดีโอที่รับ</dt><dd>${bytes(d.recorded_bytes)} · ${chunks(d.recorded_chunks)}</dd></dl>${(r.steps||[]).map((s,i)=>`<div class="admin-step">${i+1}. ${esc(s.name)}<span>${esc(steps[s.status]||s.status)}</span>${s.status!=='passed'?`<p>${esc(s.reason||'ยังยืนยันขั้นตอนนี้ไม่ได้')}</p>`:''}</div>`).join('')}${r.error||r.recording_error||r.completion_error?`<p class="admin-note">${esc(r.error||r.recording_error||r.completion_error)}</p>`:''}</div><div>${d.video_url&&d.recording_available?`<video controls playsinline preload="metadata" src="${esc(d.video_url)}"></video><p><a href="${esc(d.video_url)}" target="_blank" rel="noopener">เปิดวิดีโอของรายการนี้ ↗</a></p>`:'<div class="admin-empty-video">'+(d.ended_at?'ไม่มีวิดีโอที่บันทึกสำเร็จ':'กำลังรับวิดีโอ รอปิดงานเพื่อเปิดดู')+'</div>'}<div class="admin-evidence">${Object.entries(r.evidence||{}).map(([key,url])=>`<a href="${esc(url)}" target="_blank" rel="noopener"><img src="${esc(url)}" alt="${key==='final'?'ภาพสรุปกรอบและผลตรวจ':`หลักฐาน ${esc(key)}`}">${key==='final'?'ภาพสรุปกรอบและผลตรวจ':`หลักฐาน ${esc(key)}`}</a>`).join('')}</div><div class="admin-ai-review"><h3>ตรวจภาพเพิ่มเติมด้วย Gemini</h3><p>ส่งภาพให้ Gemini ช่วยตรวจเพิ่มเติม ผลตรวจนี้ไม่เปลี่ยนสถานะงาน</p><button class="btn btn-outline" data-review-attempt="${esc(d.id)}">ให้ Gemini ตรวจภาพ</button><div class="admin-ai-output" hidden></div></div></div></div><div class="admin-audit"><h3>ประวัติเหตุการณ์ของรายการนี้</h3><ul>${d.audit.map(e=>`<li><time>${date(e.event_at)}</time><b>${esc(({started:'เริ่มงาน',quarantined:'ตรวจพบผิดขั้นตอน',passed:'ผ่านสเตชั่น',blocked:'แยกพัก',interrupted:'หยุดกลางงาน',server_interrupted:'เซิร์ฟเวอร์หยุด'})[e.event]||e.event)}</b> · ${esc(e.detail)}</li>`).join('')}</ul></div>`;
  }catch(e){if(A.selected===id){A.detailKey=null;$('detailContent').innerHTML=`<p class="admin-detail-error">อ่านรายละเอียดไม่สำเร็จ: ${esc(e.message)}</p>`;}}
}
document.addEventListener('click',async e=>{
  const btn=e.target.closest('[data-review-attempt]');
  if(!btn)return;
  const output=btn.parentElement.querySelector('.admin-ai-output');
  btn.disabled=true;output.hidden=false;output.textContent='กำลังตรวจภาพด้วย Gemini...';
  try{
    const response=await fetch(`/api/flow/attempts/${encodeURIComponent(btn.dataset.reviewAttempt)}/ai-review`,{
      method:'POST',cache:'no-store',signal:AbortSignal.timeout(60000),
    });
    const result=await response.json();
    if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:'ตรวจภาพไม่สำเร็จ');
    output.textContent=result.text+(result.note?`\n\n${result.note}`:'');
  }catch(error){output.textContent='ไม่สำเร็จ: '+error.message;}
  finally{btn.disabled=false;}
});
async function refresh(){
  if(A.busy)return;A.busy=true;const revision=A.revision;
  try{
    const params=productionFilters();params.set('limit',A.limit);params.set('offset',A.offset);
    const data=await api('/api/flow/admin?'+params);
    if(revision!==A.revision)return;
    if(A.offset&&A.offset>=data.total){A.offset=0;A.revision++;return;}
    render(data);if(A.selected)await detail(A.selected);
  }catch(e){if(revision===A.revision){$('sync').className='worker-message bad';$('sync').textContent='ขาดการเชื่อมต่อ · ข้อมูลบนหน้าจออาจเก่า: '+e.message;}}
  finally{A.busy=false;if(revision!==A.revision)refresh();}
}
let searchTimer;
function filter(){A.offset=0;A.revision++;clearTimeout(searchTimer);searchTimer=setTimeout(refresh,250);}
$('search').oninput=filter;$('stationFilter').onchange=filter;$('stateFilter').onchange=filter;
$('scopeFilter').onchange=filter;$('sinceFilter').onchange=filter;$('untilFilter').onchange=filter;
$('refresh').onclick=refresh;
$('prev').onclick=()=>{A.offset=Math.max(0,A.offset-A.limit);A.revision++;refresh();};
$('next').onclick=()=>{if(A.offset+A.limit<A.total){A.offset+=A.limit;A.revision++;refresh();}};
document.addEventListener('click',e=>{const b=e.target.closest('[data-detail]');if(!b)return;A.selected=b.dataset.detail;A.detailKey=null;$('detail').hidden=false;$('detailContent').textContent='กำลังอ่านรายละเอียด…';detail(A.selected,true);$('detail').scrollIntoView({behavior:'smooth',block:'start'});});
$('closeDetail').onclick=()=>{A.selected=null;A.detailKey=null;$('detail').hidden=true;};
refresh();setInterval(refresh,2000);


function productionFilters(){
  const params=new URLSearchParams({q:$('search').value,state:$('stateFilter').value,scope:$('scopeFilter').value});
  if($('stationFilter').value)params.set('station_id',$('stationFilter').value);
  for(const [id,key] of [['sinceFilter','since'],['untilFilter','until']]){
    if($(id).value)params.set(key,new Date($(id).value+($(id).value.length===16?':00':'')+'+07:00').toISOString());
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
