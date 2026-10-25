'use strict';
(() => {
  const el=id=>document.getElementById(id);
  const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const date=value=>value?new Date(value).toLocaleString('th-TH',{timeZone:'Asia/Bangkok'}):'—';
  const source={worker:'หน้าพนักงาน',flow:'QR Flow',live:'ตรวจสด',qr:'สแกน QR'};
  const cards=new Map(), state={busy:false,archiveBusy:false,offset:0,total:0,revision:0,segments:[]};
  const connection=new EventSource('/api/cameras/events');
  connection.onmessage=event=>{
    try{
      const data=JSON.parse(event.data);
      for(const frame of data.frames){
        const card=cards.get(frame.id);if(!card)continue;
        card.img.src='data:image/jpeg;base64,'+frame.jpeg;card.lastArrival=Date.now();
        card.tag.textContent='● LIVE · ส่งภาพสด / บันทึกย้อนหลัง';card.tag.classList.remove('offline');
      }
    }catch{el('cameraLiveStatus').textContent='อ่านข้อมูลภาพสดไม่สำเร็จ';}
  };
  connection.onerror=()=>{for(const card of cards.values()){card.tag.textContent='ภาพสดขาดการเชื่อมต่อ · กำลังเชื่อมใหม่';card.tag.classList.add('offline');card.lastArrival=0;}};
  async function get(url){const r=await fetch(url,{cache:'no-store',signal:AbortSignal.timeout(12000)});const d=await r.json();if(!r.ok)throw Error(d.detail||'เชื่อมต่อไม่สำเร็จ');return d;}
  async function live(){
    if(state.busy)return;state.busy=true;
    try{
      const data=await get('/api/cameras');
      const ids=new Set(data.cameras.map(c=>c.id));
      for(const [id,card] of cards)if(!ids.has(id)){card.node.remove();cards.delete(id);}
      el('cameraLiveGrid').querySelector('.camera-no-live')?.remove();
      let onlineCount=0;
      for(const c of data.cameras){
        let card=cards.get(c.id);
        if(!card){
          const node=document.createElement('article');node.className='admin-station camera-card';
          node.innerHTML='<h3></h3><div class="camera-live-picture"><img alt="กล้องสด"><span class="camera-live-tag"></span></div><div class="camera-live-meta"></div>';
          card={node,img:node.querySelector('img'),tag:node.querySelector('span'),meta:node.querySelector('.camera-live-meta'),lastArrival:0};
          card.img.onerror=()=>{card.tag.textContent='อ่านภาพสดไม่สำเร็จ';card.tag.classList.add('offline');};
          cards.set(c.id,card);el('cameraLiveGrid').appendChild(node);
        }
        card.node.querySelector('h3').textContent=(c.station_id?'สเตชั่น '+c.station_id+' · ':'')+(source[c.source]||c.source);
        card.meta.innerHTML=`<b>${escape(c.operator||'ไม่ระบุพนักงาน')}</b><small>${escape(c.device_label)}</small><small>${c.linked_qr?'QR งาน '+escape(c.linked_qr):'ยังไม่ได้เชื่อมกับ QR งาน'}</small><small>เปิด ${date(c.started_at)} · ภาพล่าสุด ${date(c.frame_at)}</small><small>รหัส ${escape(c.id)}</small>`;
        const online=c.online&&connection.readyState===1&&Date.now()-card.lastArrival<5000;
        if(online)onlineCount++;
        card.tag.textContent=online?'● LIVE · ส่งภาพสด / บันทึกย้อนหลัง':c.frame_at?'ออฟไลน์ / รอภาพใหม่ · ภาพค้างไม่ใช่ภาพสด':'รอภาพแรกจากกล้อง';
        card.tag.classList.toggle('offline',!online);
      }
      if(!data.cameras.length){const empty=document.createElement('div');empty.className='camera-no-live admin-idle';empty.textContent='ยังไม่มีกล้องเปิดอยู่ · เปิดกล้องในระบบแล้วจะปรากฏที่นี่อัตโนมัติ';el('cameraLiveGrid').appendChild(empty);}
      el('cameraLiveStatus').textContent=`${onlineCount} กล้องออนไลน์ · อัปเดต ${date(data.generated_at)}`;
    }catch(e){el('cameraLiveStatus').textContent='ขาดการเชื่อมต่อ: '+e.message;for(const card of cards.values()){card.tag.textContent='ขาดการเชื่อมต่อ · ภาพอาจเก่า';card.tag.classList.add('offline');card.lastArrival=0;}}
    finally{state.busy=false;}
  }
  async function archive(){
    if(state.archiveBusy)return;state.archiveBusy=true;const revision=state.revision;
    try{
      const params=new URLSearchParams({q:el('cameraSearch').value,source:el('cameraSource').value,offset:state.offset,limit:30});
      if(el('cameraStation').value)params.set('station_id',el('cameraStation').value);
      if(el('cameraSince').value)params.set('since',new Date(el('cameraSince').value).toISOString());
      if(el('cameraUntil').value)params.set('until',new Date(el('cameraUntil').value).toISOString());
      const data=await get('/api/cameras/archive?'+params);
      if(revision!==state.revision)return;
      if(state.offset&&state.offset>=data.total){state.offset=0;state.revision++;return;}
      state.total=data.total;state.segments=data.segments;
      el('cameraArchiveRows').innerHTML=data.segments.length?data.segments.map((r,i)=>`<tr><td>${date(r.started_at)}<small>${r.ended_at?'ถึง '+date(r.ended_at):'กำลังบันทึก'}</small></td><td>${escape(r.operator||'ไม่ระบุพนักงาน')}<small>${escape(r.device_label)} · คลิป ${r.segment_index+1}</small></td><td>${r.station_id?'สเตชั่น '+r.station_id:'ไม่ระบุสเตชั่น'}<small>${escape(source[r.source])}</small><small>${r.related_qrs?'QR '+escape(r.related_qrs):'ไม่เชื่อม QR'}</small></td><td><span class="admin-tag ${r.state==='complete'?'passed':r.state==='recording'?'active':'blocked'}">${r.state==='complete'?'บันทึกครบ':r.state==='recording'?'กำลังบันทึก':'คลิปไม่ครบ / หยุดกลางคัน'}</span><small>${(r.bytes/1024/1024).toFixed(2)} MB</small></td><td>${r.available?`<button class="btn btn-outline" data-camera-play="${i}">ดูย้อนหลัง</button>`:r.state==='recording'?'รอปิดคลิป':'ไม่พบไฟล์'}</td></tr>`).join(''):'<tr><td colspan="5" class="empty-table">ยังไม่มีคลิปที่ตรงกับตัวกรอง</td></tr>';
      el('cameraArchiveCount').textContent=data.total+' คลิป';
      el('cameraPage').textContent=data.total?`${state.offset+1}–${Math.min(state.offset+30,data.total)} / ${data.total}`:'0 คลิป';
      el('cameraPrev').disabled=state.offset===0;el('cameraNext').disabled=state.offset+30>=data.total;
      el('cameraArchiveStatus').textContent='คลิปใหม่พร้อมดูทุก 30 วินาที · อัปเดตล่าสุด '+date(new Date().toISOString());
    }catch(e){if(revision===state.revision)el('cameraArchiveStatus').textContent='อ่านคลิปย้อนหลังไม่สำเร็จ: '+e.message;}
    finally{state.archiveBusy=false;if(revision!==state.revision)archive();}
  }
  let filterTimer;
  function filter(){state.offset=0;state.revision++;clearTimeout(filterTimer);filterTimer=setTimeout(archive,250);}
  for(const id of ['cameraSearch','cameraStation','cameraSource','cameraSince','cameraUntil'])el(id).addEventListener(id==='cameraSearch'?'input':'change',filter);
  el('cameraPrev').onclick=()=>{state.offset=Math.max(0,state.offset-30);state.revision++;archive();};
  el('cameraNext').onclick=()=>{if(state.offset+30<state.total){state.offset+=30;state.revision++;archive();}};
  el('cameraArchiveRows').onclick=e=>{
    const button=e.target.closest('[data-camera-play]');if(!button)return;
    const clip=state.segments[Number(button.dataset.cameraPlay)];if(!clip?.video_url)return;
    el('cameraPlayerPanel').hidden=false;el('cameraPlayerTitle').textContent=`${clip.operator||'กล้อง'} · ${date(clip.started_at)}`;
    el('cameraPlayerNotice').textContent=clip.state==='partial'?'คลิปหยุดกลางคัน อาจเปิดไม่ได้หรือมีช่วงที่ขาดหาย':'คลิปที่เซิร์ฟเวอร์รับครบแล้ว';
    el('cameraPlayback').src=clip.video_url;el('cameraPlayback').load();el('cameraVideoLink').href=clip.video_url;
    void el('cameraPlayback').play().catch(()=>{});
    el('cameraPlayerPanel').scrollIntoView({behavior:'smooth',block:'start'});
  };
  function traceSection(title,items,render,empty){
    return `<section class="traceability-section"><h4>${title} · ${items.length}</h4>${items.length?items.map(render).join(''):`<p>${empty}</p>`}</section>`;
  }
  function traceLink(url,label){
    return url?`<a href="${escape(url)}" target="_blank" rel="noopener">${label}</a>`:'';
  }
  el('traceabilityForm').addEventListener('submit',async event=>{
    event.preventDefault();
    const qr=el('traceabilityQr').value.trim(),result=el('traceabilityResult'),button=event.submitter||el('traceabilityForm').querySelector('button[type="submit"]');
    if(!qr)return;
    button.disabled=true;result.textContent='กำลังค้นประวัติที่เชื่อมด้วย QR…';
    try{
      const data=await get('/api/traceability?key='+encodeURIComponent(qr));
      const attemptHtml=row=>{
        const steps=row.result?.steps||[];
        return `<article><b>สเตชั่น ${row.station_id} · ${escape(row.state)}</b><small>รอบงาน ${escape(row.id)} · ${escape(row.operator)} · ${date(row.started_at)} → ${date(row.ended_at)}</small><div>${traceLink(row.video_url,'วิดีโองาน')} ${traceLink(row.frame_url,'ภาพสรุป')}</div>${steps.map(s=>`<small>${escape(s.name)}: ${escape(s.status)}${s.reason?' · '+escape(s.reason):''}</small>`).join('')}</article>`;
      };
      const reportHtml=row=>{
        const proofs=Object.values(row.result?.evidence||{}).map(url=>traceLink(url,'ภาพหลักฐาน')).join(' ');
        return `<article><b>${escape(row.mode)} · ${escape(row.status)}</b><small>${date(row.created_at)} · ${row.verified}/${row.total} ขั้น</small><div>${traceLink(row.video_url,'วิดีโอ')} ${proofs}</div></article>`;
      };
      const cameraHtml=row=>{
        const clips=(row.segments||[]).map(s=>`<small>คลิป ${s.segment_index+1} · ${escape(s.state)} · ${s.available?traceLink(s.video_url,'ดูย้อนหลัง'):'ไม่มีไฟล์พร้อมดู'}</small>`).join('');
        return `<article><b>${escape(source[row.source]||row.source)} · ${row.station_id?'สเตชั่น '+row.station_id:'ไม่ระบุสเตชั่น'}</b><small>${escape(row.operator)} · กล้อง ${escape(row.camera_id)}</small><small>เชื่อม ${date(row.linked_at)} ถึง ${date(row.unlinked_at)}</small>${clips||'<small>ไม่พบคลิปในช่วงเวลาที่เชื่อม</small>'}</article>`;
      };
      result.innerHTML=`<h3>QR ${escape(data.job.qr)}${data.matched_attempt_id?' · ค้นจากรอบงาน '+escape(data.matched_attempt_id):''}</h3><p>สร้างงาน ${date(data.job.created_at)}</p>${traceSection('รอบงานตามสเตชั่น',data.attempts,attemptHtml,'ยังไม่มีรอบงาน')}${traceSection('ผลตรวจจากกล้องและวิดีโอ',data.reports,reportHtml,'ยังไม่มีรายงานที่เชื่อมกับ QR นี้')}${traceSection('คลังวิดีโอกล้อง',data.camera_links,cameraHtml,'ยังไม่มีคลิปกล้องที่เชื่อมกับรอบงาน') }<p class="admin-note">${escape(data.legacy_note)}</p>`;
    }catch(error){result.textContent='ค้นประวัติไม่สำเร็จ: '+error.message;}
    finally{button.disabled=false;}
  });
  el('cameraPlayback').onerror=()=>{el('cameraPlayerNotice').textContent='เปิดวิดีโอไม่สำเร็จ ไฟล์อาจไม่ครบหรือเบราว์เซอร์ไม่รองรับรูปแบบนี้';};
  window.addEventListener('pagehide',()=>connection.close());
  live();archive();setInterval(live,1500);setInterval(archive,5000);
})();
