from pathlib import Path
root=Path(__file__).resolve().parent
p=root/'static/app.js';s=p.read_text(encoding='utf-8')
old="api(`/api/reports/${btn.dataset.review}/ai-review`,{method:'POST'})"
new="api(btn.dataset.review.startsWith('flow:')?`/api/flow/attempts/${encodeURIComponent(btn.dataset.review.slice(5))}/ai-review`:`/api/reports/${encodeURIComponent(btn.dataset.review)}/ai-review`,{method:'POST'})"
assert s.count(old)==1
s=s.replace(old,new)
s+="""
setInterval(()=>{if(document.hidden)return;if($('view-overview').classList.contains('active'))refreshStats();if($('view-reports').classList.contains('active'))refreshReports();},3000);
"""
p.write_text(s,encoding='utf-8')
p=root/'static/worker.js';s=p.read_text(encoding='utf-8')
start=s.index('function addHistory(');end=s.index('async function endWork(',start)
s=s[:start]+"""let historyBusy=false,historyRevision=0;
async function refreshWorkerHistory(){
  const operator=$('operator').value.trim(),station=$('station').value;
  if(!operator||!station){$('history').textContent='ระบุพนักงานและสถานีเพื่อดูประวัติจากฐานข้อมูล';$('counts').textContent='—';return;}
  if(historyBusy)return;
  historyBusy=true;const revision=historyRevision;
  try{
    const params=new URLSearchParams({operator,station_id:station,limit:15});
    const data=await api('/api/flow/admin?'+params);
    if(revision!==historyRevision||operator!==$('operator').value.trim()||station!==$('station').value)return;
    const s=data.filtered_stats;
    $('counts').textContent='พนักงาน '+operator+' · สถานี '+station+' · ผ่าน '+s.passed+' · แยกพัก/หยุด '+s.quarantined+' · กำลังทำ/ปิดงาน '+s.running;
    $('history').innerHTML=data.attempts.filter(r=>r.ended_at).map(r=>{
      const inspection=r.result||{},passed=r.state==='passed';
      const concerns=(inspection.steps||[]).filter(step=>step.status!=='passed');
      const summary=inspection.completion_error||inspection.recording_error||inspection.error;
      const screenshot=r.frame_url||inspection.frame_url;
      const date=new Date(/(?:Z|[+-]\\d\\d:\\d\\d)$/.test(r.started_at)?r.started_at:r.started_at+'Z').toLocaleString('th-TH',{timeZone:'Asia/Bangkok'});
      return `<div class="worker-history-row"><span>${esc(date)}</span><strong>${esc(r.qr)}</strong><span class="${passed?'good':'bad'}">${passed?'✓ ผ่าน / ส่งต่อ':r.state==='interrupted'?'⛔ หยุดกลางงาน':'⛔ แยกพัก / ล็อก QR'}</span>${r.video_url&&r.recording_available?`<a href="${esc(r.video_url)}" target="_blank" rel="noopener">ดูวิดีโอ ↗</a>`:''}${screenshot?`<a href="${esc(screenshot)}" target="_blank" rel="noopener">ภาพสรุปผล ↗</a>`:''}${concerns.length||summary?`<details><summary>เหตุผลที่ยังไม่ผ่าน</summary>${summary?`<p>${esc(summary)}</p>`:''}${concerns.map(step=>`<p>${esc(step.name)}: ${esc(step.reason||labels[step.status]||step.status)}</p>`).join('')}</details>`:''}</div>`;
    }).join('')||'ยังไม่มีรอบงานที่ปิดแล้ว · แสดง 15 รอบล่าสุดจากฐานข้อมูล';
  }catch(e){$('counts').textContent='อ่านประวัติไม่สำเร็จ · ข้อมูลอาจเก่า: '+e.message;}
  finally{historyBusy=false;}
}
function addHistory(){historyRevision++;refreshWorkerHistory();}
$('operator').addEventListener('change',()=>{historyRevision++;refreshWorkerHistory();});
$('station').addEventListener('change',()=>{historyRevision++;refreshWorkerHistory();});
setInterval(()=>{if(!document.hidden)refreshWorkerHistory();},3000);
""" +s[end:]
s=s.replace('controls();setInterval(tick,100);','controls();refreshWorkerHistory();setInterval(tick,100);')
p.write_text(s,encoding='utf-8')
p=root/'static/worker.html';s=p.read_text(encoding='utf-8');s=s.replace('src="/static/worker.js','src="/static/worker.js') # preserve existing cache token below
import re
s=re.sub(r'src="/static/worker\.js(?:\?[^"]*)?"','src="/static/worker.js?v=reports-4"',s)
p.write_text(s,encoding='utf-8')
print('Worker history now comes from the database; unified history refreshes automatically')
