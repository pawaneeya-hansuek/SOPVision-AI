/* QR-driven workflow. Server decides station handoff from the confirmed color sequence. */
'use strict';
const FLOW = {work:null, camera:null, recorder:null, frameTimer:null, watchTimer:null,
  recordQueue:Promise.resolve(), recordError:null, recordIndex:0, frameBusy:false,
  submitting:false, scanner:null, scannerStream:null, scanLoop:false, lastJob:null, stations:[],
  autoComplete:false, archiveLinked:false,
};
const flowLabels={ready:'พร้อมทำ',locked:'ล็อก',blocked:'แยกพัก / ห้ามแก้ไข',passed:'ผ่าน',active:'กำลังทำ'};
function flowGateText(data){
  if(data.completed) return 'งานนี้ผ่านครบทุกสเตชั่นแล้ว สามารถส่งต่อออกจากไลน์จำลองได้';
  const block=data.stations.find(s=>s.state==='blocked');
  if(block)return `งานถูกแยกพักที่สเตชั่น ${block.id} พนักงานไม่สามารถแก้ไขหรือเริ่มซ้ำได้ ให้นำงานออกแล้วสแกนชิ้นถัดไป`;
  const running=data.stations.find(s=>s.state==='active');
  if(running)return `สเตชั่น ${running.id} กำลังตรวจงาน สเตชั่นถัดไปยังเริ่มงานไม่ได้จนกว่าจะจบและผ่าน`;
  return `เริ่มได้เฉพาะสเตชั่นที่ขึ้นว่า “พร้อมทำ” สเตชั่นถัดไปต้องรอการตรวจ SOP ของสเตชั่นก่อนหน้า`;
}
function flowShowJob(data){
  FLOW.lastJob=data;
  $('flowJobName').textContent=data.qr.length>30?data.qr.slice(0,27)+'…':data.qr;
  $('flowChain').innerHTML=data.stations.map(st=>`<div class="flow-step ${st.state}">
    <div class="flow-step-icon">${st.state==='passed'?'✓':st.state==='locked'?'🔒':st.id}</div>
    <div class="flow-step-main"><b>${escapeHTML(st.name)}</b><small>${st.steps.map(s=>escapeHTML(s.name)).join(' → ')}</small>${st.last_operator?`<br><small>ตรวจล่าสุด: ${escapeHTML(st.last_operator)} · ${st.attempts} รอบ</small>`:''}</div>
    <span class="flow-step-tag">${flowLabels[st.state]}</span>
  </div>`).join('');
  $('flowGateMessage').textContent=flowGateText(data);
  FLOW.stations=data.stations;
  flowRenderPreview();
}
function flowRenderPreview(){
  if(FLOW.work)return;
  const station=FLOW.stations.find(s=>s.id===Number($('flowStation').value));
  if(!station)return;
  renderSteps('flowStepList',station.steps.map(s=>({...s,status:'waiting',reason:'รอสีตามลำดับ'})));
  if(FLOW.lastJob)$('flowGateMessage').textContent=flowGateText(FLOW.lastJob);
}
async function flowLookup(){
  const qr=$('flowQr').value.trim();if(!qr){toast('กรุณาสแกน QR หรือกรอกรหัสงาน',true);return null;}
  try{const data=await api('/api/flow/lookup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({qr})});flowShowJob(data);return data}
  catch(e){toast(e.message,true);return null;}
}
$('flowLookupBtn').addEventListener('click',flowLookup);
$('flowStation').addEventListener('change',flowRenderPreview);
$('flowQr').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();flowStart();}});
$('flowStartBtn').addEventListener('click',flowStart);
function flowMime(){return typeof MediaRecorder!=='undefined'
  ? ['video/webm;codecs=vp8','video/webm','video/mp4'].find(m=>MediaRecorder.isTypeSupported(m))||''
  : '';}
const flowFrameCanvas=document.createElement('canvas');
function flowFeedVideo(){
  if(!FLOW.work || FLOW.frameBusy || !$('flowVideo').videoWidth)return;
  FLOW.frameBusy=true;
  const sid=FLOW.work.id, v=$('flowVideo');
  (async()=>{
    const canvas=flowFrameCanvas,width=640;
    canvas.width=width;canvas.height=Math.round(width*v.videoHeight/v.videoWidth);
    canvas.getContext('2d').drawImage(v,0,0,canvas.width,canvas.height);
    const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.72));
    if(!blob)return;
    const fd=new FormData();fd.append('frame',blob,'frame.jpg');
    const data=await api(`/api/flow/frame/${sid}`,{method:'POST',body:fd});
    if(FLOW.work?.id!==sid)return;
    renderSteps('flowStepList',data.steps);
    flowDrawInspectionOverlay(data.steps,data.visible);
    const trouble=data.steps.find(s=>['out_of_order','uncertain'].includes(s.status));
    const waiting=data.steps.find(s=>s.status!=='passed');
    $('flowLiveWarning').textContent=trouble?trouble.reason:`ตรวจสีและจำนวน ${data.verified}/${data.total} · ${waiting?.reason||'ยืนยันจำนวนชิ้นครบแล้ว'}`;
    FLOW.autoComplete=data.verified===data.total&&data.total>0&&!data.quarantined;
  })().catch(e=>{$('flowLiveWarning').textContent='ตรวจเฟรมมีปัญหา: '+e.message;})
     .finally(()=>{
       FLOW.frameBusy=false;
       if(FLOW.autoComplete&&FLOW.work&&!FLOW.submitting){FLOW.autoComplete=false;void flowFinish();}
     });
}
function flowDrawInspectionOverlay(steps,visible){
  const canvas=$('flowOverlay'),video=$('flowVideo');if(!video.videoWidth)return;
  const width=640,height=Math.round(width*video.videoHeight/video.videoWidth);
  canvas.width=width;canvas.height=height;const ctx=canvas.getContext('2d');ctx.clearRect(0,0,width,height);
  Object.entries(visible||{}).forEach(([color,item])=>{ctx.strokeStyle='#36dc9b';ctx.lineWidth=2;(item.objects||[]).forEach(object=>{const [x,y,w,h]=object.bbox;ctx.strokeRect(x,y,w,h)});if(item.bbox){const [x,y]=item.bbox;ctx.fillStyle=ctx.strokeStyle;ctx.font='13px sans-serif';ctx.fillText(`${color.toUpperCase()} ${item.count||0}`,x,Math.max(14,y-4))}});
}
async function flowSubmitFinalFrame(sid){
  if(FLOW.frameTimer){clearInterval(FLOW.frameTimer);FLOW.frameTimer=null}
  while(FLOW.frameBusy)await new Promise(resolve=>setTimeout(resolve,30));
  const video=$('flowVideo');if(!video.videoWidth)throw Error('ไม่มีภาพกล้องล่าสุดสำหรับตรวจซ้ำก่อนจบงาน');
  const canvas=flowFrameCanvas,width=640,height=Math.round(width*video.videoHeight/video.videoWidth);
  canvas.width=width;canvas.height=height;canvas.getContext('2d').drawImage(video,0,0,width,height);
  const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.72));
  if(!blob)throw Error('สร้างภาพตรวจซ้ำก่อนจบงานไม่สำเร็จ');
  const form=new FormData();form.append('frame',blob,'final-frame.jpg');
  const data=await api(`/api/flow/frame/${sid}`,{method:'POST',body:form});
  if(FLOW.work?.id!==sid)return;
  renderSteps('flowStepList',data.steps);flowDrawInspectionOverlay(data.steps,data.visible);
  const trouble=data.steps.find(step=>step.status!=='passed');
  $('flowLiveWarning').textContent=trouble?`ตรวจซ้ำก่อนจบ: ${trouble.reason}`:'ตรวจซ้ำแล้ว สีและจำนวนชิ้นครบตามกำหนด';
}
function flowQueueVideo(blob){
  if(!blob.size)return;
  const sid=FLOW.work?.id;if(!sid)return;
  const seq=FLOW.recordIndex++;
  FLOW.recordQueue=FLOW.recordQueue.then(async()=>{
    if(FLOW.recordError)return;
    const fd=new FormData();fd.append('chunk',blob,`video-part-${seq}`);
    await api(`/api/flow/recording/${sid}/${seq}`,{method:'POST',body:fd});
  }).catch(e=>{FLOW.recordError=e;$('flowRecordHint').textContent='บันทึกวิดีโอมีปัญหา: '+e.message;});
}
function flowStopCamera(){
  if(FLOW.frameTimer){clearInterval(FLOW.frameTimer);FLOW.frameTimer=null;}
  if(FLOW.watchTimer){clearInterval(FLOW.watchTimer);FLOW.watchTimer=null;}
  void CameraShare.stop(FLOW.camera);
  if(FLOW.camera){FLOW.camera.getTracks().forEach(t=>t.stop());FLOW.camera=null;}
  $('flowVideo').srcObject=null;
  $('flowCameraEmpty').hidden=false;
  $('flowCameraBadge').innerHTML='<span class="online-dot"></span> รอเริ่มงาน';
  $('flowStartBtn').disabled=false;$('flowAbortBtn').disabled=true;
}
async function flowStart(){
  if(FLOW.work||FLOW.submitting)return;
  FLOW.submitting=true;$('flowStartBtn').disabled=true;
  let stream=null,started=null;
  try{
    const qr=$('flowQr').value.trim(),operator=$('flowOperator').value.trim(),station_id=Number($('flowStation').value);
    if(!qr||!operator)throw Error('กรุณาสแกน QR และระบุรหัสพนักงาน');
    if(!navigator.mediaDevices?.getUserMedia)throw Error('เบราว์เซอร์นี้ไม่รองรับกล้อง กรุณาใช้ Chrome/Edge ผ่าน localhost หรือ HTTPS');
    const job=await flowLookup();if(!job)throw Error('อ่านข้อมูลงานไม่ได้');
    const selected=job.stations.find(x=>x.id===station_id);
    if(job.quarantined)throw Error('งานถูกแยกพักแล้ว พนักงานไม่สามารถแก้ไขเองได้ กรุณาสแกนชิ้นถัดไป');
    if(!selected||selected.state!=='ready')throw Error(`สเตชั่น ${station_id} ยังทำไม่ได้ สเตชั่นเก่าต้องผ่าน SOP ก่อน`);
    // Request permission before occupying a station on the server.
    stream=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:1280},height:{ideal:720},facingMode:'environment'},audio:false});
    const mime=flowMime();
    started=await api('/api/flow/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({qr,operator,station_id,mime_type:mime})});
    FLOW.camera=stream;FLOW.work=started;FLOW.autoComplete=false;FLOW.archiveLinked=false;
    FLOW.recordError=null;FLOW.recordIndex=0;FLOW.recordQueue=Promise.resolve();
    if(mime){
      try{
        await CameraShare.start(stream,{source:'flow',station_id,operator,onerror:e=>{
          $('flowRecordHint').textContent='วิดีโอสำรองบันทึกไม่สำเร็จ แต่ระบบตรวจสีและจำนวนยังทำงานต่อ: '+e.message;
        }});
        await CameraShare.linkWork(stream,started.qr,started.id);
        FLOW.archiveLinked=true;
      }catch(e){
        void CameraShare.stop(stream);
        $('flowRecordHint').textContent='วิดีโอสำรองใช้ไม่ได้ แต่ระบบตรวจสีและจำนวนยังทำงานต่อ: '+e.message;
      }
    }
    const video=$('flowVideo');video.srcObject=stream;await video.play();
    const recorder=mime?new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:1_100_000}):null;FLOW.recorder=recorder;
    if(recorder){
      recorder.ondataavailable=e=>flowQueueVideo(e.data);
      recorder.onerror=e=>{FLOW.recordError=FLOW.recordError||new Error('กล้องบันทึกวิดีโอขัดข้อง');};
      recorder.start(1500);
    }
    $('flowCameraEmpty').hidden=true;
    $('flowCameraBadge').innerHTML='🟢 กำลังตรวจ';
    $('flowAbortBtn').disabled=false;
    $('flowRecordHint').textContent=mime
      ? `ตรวจสีและจำนวนอัตโนมัติ: ${started.station.name} · ${escapeHTML(operator)}`
      : `ตรวจสีและจำนวนอัตโนมัติ: ${started.station.name} · ไม่รองรับบันทึกวิดีโอ`;
    FLOW.frameTimer=setInterval(flowFeedVideo,started.sample_every_ms||100);
    const startedMs=Date.now();FLOW.watchTimer=setInterval(()=>$('flowRecClock').textContent=fmtTime((Date.now()-startedMs)/1000),450);
    $('flowResult').hidden=true;
    flowShowJob(await api('/api/flow/lookup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({qr})}));
    toast('สแกน QR ผ่าน เริ่มตรวจสีและจำนวนอัตโนมัติแล้ว');
  }catch(e){
    if(started){try{await api(`/api/flow/abort/${started.id}`,{method:'POST'});}catch{}}
    if(stream){void CameraShare.stop(stream);stream.getTracks().forEach(t=>t.stop());}
    FLOW.work=null;FLOW.recorder=null;FLOW.archiveLinked=false;flowStopCamera();
    toast('เริ่มงานไม่ได้: '+e.message,true);
  }finally{FLOW.submitting=false;if(!FLOW.work)$('flowStartBtn').disabled=false;}
}
async function flowStopRecording(){
  const r=FLOW.recorder;if(!r)return;
  if(r.state!=='inactive')await new Promise(resolve=>{r.onstop=resolve;r.stop();});
  await FLOW.recordQueue;
}
async function flowFinish(){
  if(!FLOW.work||FLOW.submitting)return;
  FLOW.submitting=true;  $('flowAbortBtn').disabled=true;
  const sid=FLOW.work.id;
  try{
    await flowSubmitFinalFrame(sid);
    await flowStopRecording();
    const data=await api(`/api/flow/finish/${sid}`,{method:'POST'});
    if(FLOW.archiveLinked){
      try{await CameraShare.unlinkWork(FLOW.camera,sid);}
      catch{toast('บันทึกผลแล้ว แต่ยกเลิกการเชื่อมวิดีโอสำรองไม่ได้',true);}
    }
    FLOW.archiveLinked=false;FLOW.work=null;FLOW.recorder=null;flowStopCamera();
    flowShowJob(data.job);
    $('flowResult').hidden=false;
    $('flowResult').innerHTML=`<div class="${data.can_handoff?'flow-result-pass':'flow-result-block'}"><b>${data.can_handoff?'✓ ผ่าน SOP ปลดล็อกสเตชั่นถัดไปแล้ว':'⛔ ตรวจไม่ผ่าน งานนี้ถูกแยกพัก'}</b><p>ตรวจพบ ${data.inspection.verified}/${data.inspection.total} ขั้นตอน · ${data.inspection.issues} ประเด็นที่ต้องตรวจสอบ</p>${data.video_url?`<a href="${encodeURI(data.video_url)}" target="_blank" rel="noopener">▶ ดูวิดีโอการทำงานที่บันทึกไว้</a>`:''}<p>${data.can_handoff?'สามารถนำ QR ใบงานเดิมไปสแกนที่สเตชั่นถัดไปได้':'พนักงานแก้ไขหรือเริ่มงาน QR นี้ซ้ำไม่ได้ ให้นำงานออกแล้วสแกนชิ้นถัดไป'}</p></div>`;
    toast(data.can_handoff?'ผ่านแล้ว ส่งต่องานได้':'ตรวจไม่ผ่าน สเตชั่นถัดไปถูกล็อก',!data.can_handoff);
  }catch(e){
    toast('จบงานไม่สำเร็จ: '+e.message,true);
    // In any upload failure, abort on the server; never release the following stage.
    try{await api(`/api/flow/abort/${sid}`,{method:'POST'});}catch{}
    FLOW.archiveLinked=false;FLOW.work=null;FLOW.recorder=null;flowStopCamera();await flowLookup();
  }finally{FLOW.submitting=false;}
}
$('flowAbortBtn').addEventListener('click',async()=>{
  if(!FLOW.work||FLOW.submitting)return;
  FLOW.submitting=true;
  const sid=FLOW.work.id;
  try{await flowStopRecording();await api(`/api/flow/abort/${sid}`,{method:'POST'});}catch(e){toast(e.message,true)}
  if(FLOW.archiveLinked){try{await CameraShare.unlinkWork(FLOW.camera,sid);}catch{}}
  FLOW.archiveLinked=false;FLOW.work=null;FLOW.recorder=null;flowStopCamera();FLOW.submitting=false;
  await flowLookup();toast('แยกพักแล้ว พนักงานแก้ไขงานนี้ไม่ได้ สแกนชิ้นถัดไปได้');
});

// Native BarcodeDetector works in supported secure-context browsers. USB readers
// and manual QR entry remain available when the browser does not support it.
function flowCloseScanner(){
  FLOW.scanLoop=false;
  void CameraShare.stop(FLOW.scannerStream);
  FLOW.scannerStream?.getTracks().forEach(t=>t.stop());FLOW.scannerStream=null;
  FLOW.scanner?.remove();FLOW.scanner=null;
}
$('flowQrCameraBtn').addEventListener('click',async()=>{
  if(FLOW.work)return toast('กรุณาจบงานที่กำลังบันทึกก่อน',true);
  if(!('BarcodeDetector' in window))return toast('เบราว์เซอร์นี้ไม่รองรับสแกน QR ผ่านกล้อง ใช้เครื่องอ่าน QR แบบ USB หรือกรอกรหัสแทน',true);
  let stream;
  try{
    const detector=new BarcodeDetector({formats:['qr_code']});
    stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'environment',
      width:{ideal:1280},height:{ideal:720}},audio:false});
    FLOW.scannerStream=stream;
    if(flowMime()){
      try{await CameraShare.start(stream,{source:'qr',station_id:Number($('flowStation').value),operator:$('flowOperator').value.trim(),onerror:e=>toast('วิดีโอสำรองมีปัญหา แต่ยังสแกน QR ได้: '+e.message,true)});}
      catch(e){toast('วิดีโอสำรองใช้ไม่ได้ แต่ยังสแกน QR ได้: '+e.message,true);}
    }
    const wrap=document.createElement('div');wrap.className='flow-qr-scanner';
    wrap.innerHTML='<div class="scan-inner"><h3>สแกน QR ใบงาน</h3><p>เล็งกล้องไปที่ QR Code เดิมของงาน เมื่ออ่านสำเร็จจะเริ่มกระบวนการให้อัตโนมัติ</p><video autoplay muted playsinline></video><button type="button" class="btn btn-outline">ยกเลิก</button></div>';
    document.body.appendChild(wrap);FLOW.scanner=wrap;
    wrap.querySelector('button').onclick=flowCloseScanner;
    const video=wrap.querySelector('video');video.srcObject=stream;await video.play();FLOW.scanLoop=true;
    async function scan(){
      if(!FLOW.scanLoop)return;
      try{
        const codes=await detector.detect(video);
        if(codes.length&&codes[0].rawValue){const code=codes[0].rawValue;flowCloseScanner();$('flowQr').value=code;await flowStart();return;}
      }catch{}
      if(FLOW.scanLoop)setTimeout(scan,80);
    }
    scan();
  }catch(e){stream?.getTracks().forEach(t=>t.stop());flowCloseScanner();toast('ไม่สามารถสแกน QR ผ่านกล้อง: '+e.message,true);}
});
window.addEventListener('beforeunload',()=>{
  if(FLOW.work){try{navigator.sendBeacon(`/api/flow/abort/${FLOW.work.id}`,new Blob([JSON.stringify({csrf:window.Auth?.csrf||''})],{type:'application/json'}));}catch{}}
  FLOW.camera?.getTracks().forEach(t=>t.stop());FLOW.scannerStream?.getTracks().forEach(t=>t.stop());
});
(async()=>{try{
  FLOW.stations=await api('/api/flow/stations');
  $('flowStation').innerHTML=FLOW.stations.map(station=>`<option value="${station.id}">${escapeHTML(station.name)}</option>`).join('');
  flowRenderPreview();
}catch(e){toast('โหลดระบบ QR Production Flow ไม่สำเร็จ: '+e.message,true)}})();

let flowLookupBusy=false;
setInterval(async()=>{
  if(document.hidden||FLOW.work||FLOW.submitting||flowLookupBusy||!document.getElementById('view-flow')?.classList.contains('active')||!document.getElementById('flowQr')?.value.trim())return;
  flowLookupBusy=true;try{await flowLookup();}finally{flowLookupBusy=false;}
},3000);
