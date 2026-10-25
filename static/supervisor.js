'use strict';
(() => {
  const el=id=>document.getElementById(id);
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const date=value=>value?new Date(value).toLocaleString('th-TH',{timeZone:'Asia/Bangkok'}):'—';
  const state={work:0,camera:0,revision:0};
  async function api(url,options={}){
    const response=await fetch(url,{...options,cache:'no-store',signal:AbortSignal.timeout(15000)});
    const body=await response.json();
    if(!response.ok)throw Error(typeof body.detail==='string'?body.detail:'โหลดข้อมูลไม่สำเร็จ');
    return body;
  }
  function message(text,bad=false){el('supervisorMessage').hidden=false;el('supervisorMessage').textContent=text;el('supervisorMessage').className='worker-message '+(bad?'bad':'good');}
  function videoButton(url,title,notice=''){
    return `<button type="button" class="btn btn-outline" data-video="${esc(url)}" data-title="${esc(title)}" data-notice="${esc(notice)}">ดูวิดีโอย้อนหลัง</button>`;
  }
  async function reviews(){
    el('refreshReviews').disabled=true;
    try{
      const rows=await api('/api/reviews?'+new URLSearchParams({scope:el('reviewScope').value,status:el('reviewStatus').value}));
      el('reviewRows').innerHTML=rows.length?rows.map(row=>`<article class="supervisor-item"><h3>${esc(row.source_qr||row.qr)}</h3><small>สเตชั่น ${row.station_id} · ${esc(row.operator)} · ${date(row.created_at)} · ${row.is_test?'ทดสอบ':'ผลิตจริง'}</small><p>${esc(row.result.error||row.result.completion_error||row.result.recording_error||'ตรวจขั้นตอนไม่ครบหรือผิดลำดับ')}</p>${row.video_url?videoButton(row.video_url,row.source_qr||row.qr):'<p>ไม่มีวิดีโอประจำชิ้นงาน</p>'}${row.status==='pending'?`<form class="approval-form" data-attempt="${esc(row.attempt_id)}"><label>เหตุผลที่อนุญาตสแกนซ้ำ<textarea name="reason" minlength="10" maxlength="2000" rows="2" required placeholder="ระบุเหตุผลอย่างน้อย 10 ตัวอักษร"></textarea></label><button class="btn btn-accent" type="submit">อนุญาตให้สแกนงานซ้ำ</button></form>`:`<p class="decision">${row.decision==='rework_approved'?'อนุญาตสแกนซ้ำแล้ว':'พิจารณาแล้ว'} · ${esc(row.reviewer_name||'')} · ${date(row.reviewed_at)}</p><p>${esc(row.reason)}</p>`}</article>`).join(''):'<p class="empty">ไม่มีงานในรายการนี้</p>';
    }catch(error){message(error.message,true);}
    finally{el('refreshReviews').disabled=false;}
  }
  function params(offset,limit){
    const p=new URLSearchParams({q:el('videoSearch').value.trim(),offset,limit});
    if(el('videoStation').value)p.set('station_id',el('videoStation').value);
    return p;
  }
  async function archive(){
    const revision=++state.revision;
    const query=el('videoSearch').value.trim();
    for(const prefix of ['work','camera']){
      el(prefix+'Prev').disabled=true;el(prefix+'Next').disabled=true;
    }
    try{
      const [work,camera]=await Promise.all([api('/api/supervisor/recordings?'+params(state.work,20)),api('/api/cameras/archive?'+params(state.camera,20))]);
      if(revision!==state.revision)return;
      el('workVideos').innerHTML=work.recordings.length?work.recordings.map(row=>`<article class="supervisor-item"><h3>${esc(row.source_qr||row.qr)}</h3><small>สเตชั่น ${row.station_id} · ${esc(row.operator)} · ${date(row.started_at)} · ${row.is_test?'ทดสอบ':'ผลิตจริง'}</small><p>${row.state==='passed'?'ผ่าน':row.state==='interrupted'?'หยุดกลางงาน':'แยกพัก'}</p>${row.available?videoButton(row.video_url,row.source_qr||row.qr):'<p>ไม่พบไฟล์วิดีโอ</p>'}</article>`).join(''):'<p class="empty">ไม่พบวิดีโอประจำชิ้นงาน</p>';
      el('cameraVideos').innerHTML=camera.segments.length?camera.segments.map(row=>`<article class="supervisor-item"><h3>${row.station_id?'สเตชั่น '+row.station_id:'กล้อง'} · ${esc(row.related_qrs||row.operator||'ไม่ระบุงาน')}</h3><small>${date(row.started_at)} · ${esc(row.device_label)}</small><p>${row.state==='complete'?'รับคลิปครบแล้ว':row.state==='partial'?'คลิปไม่ครบ / ขาดการเชื่อมต่อ':'กำลังบันทึก'}</p>${row.available?videoButton(row.video_url,'กล้อง · '+date(row.started_at),row.state==='partial'?'คลิปหยุดกลางคัน อาจมีช่วงที่ขาดหาย':''):'<p>ยังไม่มีคลิปพร้อมดู</p>'}</article>`).join(''):'<p class="empty">ไม่พบคลิปกล้อง</p>';
      el('searchStatus').textContent=`${query?'ผลค้นหา '+query:'วิดีโอทั้งหมด'} · งาน ${work.total} รายการ · คลิปกล้อง ${camera.total} รายการ`;
      for(const [prefix,data] of [['work',work],['camera',camera]]){
        el(prefix+'Count').textContent=`${data.total?state[prefix]+1:0}–${Math.min(state[prefix]+20,data.total)} / ${data.total} รายการ`;
        el(prefix+'Prev').disabled=state[prefix]===0;el(prefix+'Next').disabled=state[prefix]+20>=data.total;
      }
    }catch(error){if(revision===state.revision)message(error.message,true);}
  }
  document.addEventListener('submit',async event=>{
    const form=event.target.closest('.approval-form');if(!form)return;
    event.preventDefault();const button=form.querySelector('button');button.disabled=true;
    try{
      await api('/api/reviews/'+encodeURIComponent(form.dataset.attempt)+'/decision',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({decision:'rework_approved',reason:new FormData(form).get('reason').trim()})});
      message('อนุญาตแล้ว พนักงานสแกน QR เดิมเพื่อเริ่มรอบตรวจใหม่ได้ ผลตรวจเดิมยังถูกเก็บไว้');await reviews();
    }catch(error){message(error.message,true);}
    finally{button.disabled=false;}
  });
  document.addEventListener('click',event=>{
    const button=event.target.closest('[data-video]');if(!button)return;
    const url=new URL(button.dataset.video,location.origin);
    if(url.origin!==location.origin||!(url.pathname.startsWith('/media/')||/^\/api\/cameras\/[^/]+\/segments\/\d+\/video$/.test(url.pathname)))return;
    el('playbackTitle').textContent=button.dataset.title;el('playbackNotice').textContent=button.dataset.notice;el('playback').dataset.notice=button.dataset.notice;
    el('playbackPanel').hidden=false;el('playback').src=url.href;el('playback').load();el('playbackPanel').scrollIntoView({behavior:'smooth',block:'start'});
    el('playbackNotice').textContent=button.dataset.notice||'กำลังเปิดวิดีโอ… ครั้งแรกอาจใช้เวลาจัดเตรียมไฟล์';
    void el('playback').play().catch(error=>{if(error.name==='NotAllowedError')el('playbackNotice').textContent='กดปุ่มเล่นบนวิดีโอเพื่อเริ่มดู';});
  });
  el('closePlayback').onclick=()=>{el('playback').pause();el('playback').removeAttribute('src');el('playback').load();el('playbackPanel').hidden=true;};
  el('playback').onerror=()=>el('playbackNotice').textContent='เปิดคลิปไม่ได้ ไฟล์อาจไม่ครบหรือเบราว์เซอร์ไม่รองรับ';
  el('playback').onplaying=()=>el('playbackNotice').textContent=el('playback').dataset.notice||'';
  el('refreshReviews').onclick=reviews;el('reviewScope').onchange=reviews;el('reviewStatus').onchange=reviews;
  function searchVideos(value){
    const qr=value.trim();
    if(qr.length>300||/[\x00-\x1f]/.test(qr)){message('รหัสค้นหาไม่ถูกต้อง หรือยาวเกิน 300 ตัวอักษร',true);return;}
    el('videoSearch').value=qr;state.work=0;state.camera=0;
    el('searchStatus').textContent='กำลังค้นหาวิดีโอ…';archive();
  }
  el('archiveFilters').onsubmit=event=>{event.preventDefault();stopScanner();searchVideos(el('videoSearch').value);};
  let scannerGeneration=0,scanStream=null,scanTimer=null,decodeAbort=null;
  function stopScanner(){
    scannerGeneration++;clearTimeout(scanTimer);decodeAbort?.abort();decodeAbort=null;
    scanStream?.getTracks().forEach(track=>track.stop());scanStream=null;
    el('searchQrVideo').srcObject=null;el('searchScanner').hidden=true;el('scanVideoQr').disabled=false;
  }
  async function startScanner(){
    stopScanner();const generation=scannerGeneration;
    el('searchScanner').hidden=false;el('scanVideoQr').disabled=true;el('scannerStatus').textContent='กำลังเปิดกล้อง…';
    try{
      if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia)throw Error('เปิดผ่าน HTTPS บนมือถือเพื่อใช้กล้อง หรือใช้เครื่องสแกน QR ในช่องค้นหา');
      const stream=await navigator.mediaDevices.getUserMedia({audio:false,video:{facingMode:{ideal:'environment'},width:{ideal:1280},height:{ideal:720}}});
      if(generation!==scannerGeneration){stream.getTracks().forEach(track=>track.stop());return;}
      scanStream=stream;const video=el('searchQrVideo');video.srcObject=stream;await video.play();
      if(generation!==scannerGeneration)return;
      stream.getVideoTracks()[0]?.addEventListener('ended',()=>{if(generation===scannerGeneration){stopScanner();message('กล้องถูกตัดการเชื่อมต่อ กรุณาเปิดกล้องใหม่',true);}},{once:true});
      let detector=null;
      try{if(window.BarcodeDetector)detector=new BarcodeDetector({formats:['qr_code']});}catch{}
      const canvas=document.createElement('canvas');
      el('scannerStatus').textContent='เล็ง QR ให้อยู่ในภาพ เมื่ออ่านได้จะปิดกล้องและค้นหาวิดีโออัตโนมัติ';
      const scan=async()=>{
        if(generation!==scannerGeneration)return;
        try{
          let qr=null;
          if(video.readyState>=2&&video.videoWidth){
            if(detector){try{qr=(await detector.detect(video))[0]?.rawValue||null;}catch{detector=null;}}
            if(!detector){
              const scale=Math.min(1,960/Math.max(video.videoWidth,video.videoHeight));
              canvas.width=Math.round(video.videoWidth*scale);canvas.height=Math.round(video.videoHeight*scale);
              canvas.getContext('2d').drawImage(video,0,0,canvas.width,canvas.height);
              const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.85));
              if(generation!==scannerGeneration)return;
              if(!blob)throw Error('อ่านภาพกล้องไม่ได้');
              const body=new FormData();body.append('frame',blob,'search-qr.jpg');
              decodeAbort=new AbortController();const controller=decodeAbort;
              const timeout=setTimeout(()=>controller.abort(),8000);
              try{
                const response=await fetch('/api/supervisor/qr/decode',{method:'POST',body,signal:controller.signal});
                const data=await response.json();
                if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'อ่าน QR ไม่สำเร็จ');
                qr=data.qr;
              }finally{clearTimeout(timeout);if(decodeAbort===controller)decodeAbort=null;}
            }
          }
          if(generation!==scannerGeneration)return;
          if(qr){stopScanner();searchVideos(qr);el('videoSearch').focus();return;}
          scanTimer=setTimeout(scan,500);
        }catch(error){if(generation===scannerGeneration){stopScanner();message(error.name==='AbortError'?'อ่าน QR ไม่สำเร็จ กรุณาเปิดกล้องลองใหม่หรือพิมพ์รหัส':error.message,true);}}
      };
      scanTimer=setTimeout(scan,100);
    }catch(error){
      if(generation!==scannerGeneration)return;
      stopScanner();message(error.name==='NotAllowedError'?'กรุณาอนุญาตกล้อง หรือใช้เครื่องสแกน QR / พิมพ์รหัสในช่องค้นหา':error.message,true);
    }
  }
  el('scanVideoQr').onclick=startScanner;el('stopVideoQr').onclick=stopScanner;
  window.addEventListener('pagehide',stopScanner);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stopScanner();});
  for(const prefix of ['work','camera'])for(const [direction,delta] of [['Prev',-20],['Next',20]])el(prefix+direction).onclick=()=>{state[prefix]=Math.max(0,state[prefix]+delta);archive();};
  Auth.ready.then(()=>Promise.all([reviews(),archive()])).catch(error=>message(error.message,true));
})();
