'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const W = {stations:[], stream:null, work:null, busy:false, sampling:false, recorder:null,
  queue:Promise.resolve(), uploadError:null, sequence:0, lastQr:null, history:[], detector:null, started:0,pending:null,lastQrScan:0,
  nextQrCandidate:null,nextQrObservations:0,nextQr:null,archiveLinked:false,
  frames:[],capturing:false,frameEpoch:0,qrReady:false,qrClearObservations:0,qrTimer:null,recording:null,archiveTasks:new Set()};
const labels = {pending:'รอตรวจ',waiting:'รอสีตามลำดับ',candidate:'พบสี',verifying:'กำลังยืนยันจำนวน',passed:'สีและจำนวนผ่าน',missing:'จำนวนชิ้นไม่ครบ',out_of_order:'ลำดับสีผิด',uncertain:'จำนวนสีไม่ตรง'};
const colors = {green:'เขียว',red:'แดง',blue:'น้ำเงิน',yellow:'เหลือง',orange:'ส้ม',purple:'ม่วง'};
const API_TIMEOUT_MS=60000;
async function checkInspectionServer() {
  const health=await api('/api/health');
  if(health.frame_protocol!==2 || !health.instant_completion || health.needs_restart)
    throw Error('เซิร์ฟเวอร์ตรวจงานยังไม่ได้อัปเดต กรุณาเริ่มเซิร์ฟเวอร์ใหม่ก่อนเริ่มงาน');
}
async function api(url, options={}) {
  let response;
  try {
    response = await fetch(url, {...options, cache:'no-store',signal:options.signal || AbortSignal.timeout(API_TIMEOUT_MS)});
  } catch(error) {
    if(error.name==='TimeoutError'||error.name==='AbortError')throw Error('เซิร์ฟเวอร์ตอบช้าเกินกำหนด กรุณาตรวจเครือข่ายแล้วลองอีกครั้ง');
    throw error;
  }
  const data = await response.json();
  if (!response.ok) { const error=Error(typeof data.detail === 'string' ? data.detail : 'ระบบรับข้อมูลไม่สำเร็จ');error.status=response.status;throw error; }
  return data;
}
const post = (url, data) => api(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
async function safeRetry(action) {
  try {return await action();} catch(e) {
    if(e.status && e.status<500)throw e;
    return action(); // Only used for endpoints that deduplicate the same request.
  }
}
function clearPending(){W.pending=null;sessionStorage.removeItem('workerPending');}
function message(text, kind='') { $('message').textContent=text; $('message').className='worker-message '+kind; }
function controls() {
  const locked = !!W.work || !!W.pending || W.busy;
  if(window.Auth){window.Auth.locked=locked;document.querySelectorAll('#workMode,#testRun,#newTestRun,#testLabel').forEach(e=>e.disabled=locked);}
  $('station').disabled=locked;$('operator').disabled=locked;
  $('qr').disabled=!!W.pending||W.busy;$('start').disabled=!!W.pending||W.busy;
  $('station').disabled=locked||!!W.stream;$('operator').disabled=locked||!!W.stream;
  $('camera').disabled=!!W.stream || locked;
  $('openCamera').disabled=!!W.stream || locked;
  $('closeCamera').disabled=!W.stream || locked;
  $('separate').disabled=!W.pending || W.busy;
  $('separate').hidden=!W.pending;
  $('separate').textContent='ตรวจสถานะคำขอที่ค้าง';
}
function renderSteps(steps) {
  $('steps').innerHTML=steps.map((s,i)=>`<div class="step-item ${esc(s.status || 'waiting')}"><div class="step-index">${s.status==='passed'?'✓':i+1}</div><div class="step-name"><b>${esc(s.name)}</b><span>ชิ้นส่วนสี${esc(colors[s.color])}${s.temporarily_hidden?' · ถูกบัง/ไม่พบชั่วคราว':''}</span>${s.reason?`<small class="step-reason">${esc(s.reason)}</small>`:''}</div><span class="step-result">${labels[s.status] || 'รอเริ่ม'}</span></div>`).join('');
  $('progress').textContent=`${steps.filter(s=>s.status==='passed').length} / ${steps.length}`;
}
function renderPriorCheck(check){
  $('priorCheck').hidden=!check?.total;
  if(!check?.total)return;
  $('priorCheckTitle').textContent=`${check.passed?'✓ งานจากสเตชั่นก่อนหน้าครบ':'ตรวจงานจากสเตชั่นก่อนหน้า'} ${check.verified||0}/${check.total}`;
  $('priorSteps').innerHTML=check.steps.map(step=>`<div class="step-item ${step.status==='passed'?'passed':'waiting'}"><div class="step-index">${step.status==='passed'?'✓':'?'}</div><div class="step-name"><b>สเตชั่น ${esc(step.source_station_id)} · สี${esc(colors[step.color])}</b><span>${step.status==='passed'?'ตรวจพบแล้ว':'แสดงสีของงานก่อนหน้าให้กล้องเห็นครบก่อนเริ่มขั้นตอนใหม่'}</span></div></div>`).join('');
}
function priorPreview(station){
  const steps=station.prior_steps||[];
  renderPriorCheck({total:steps.length,verified:0,passed:false,steps});
}
function stationPreview() {
  const station=W.stations.find(s=>s.id===Number($('station').value));
  if (!station) return;
  $('stationTitle').textContent=station.name;
  if(window.Auth?.account?.guest){$('operator').value='STATION-'+station.id;localStorage.setItem('workerOperator',$('operator').value);}
  renderSteps(station.steps);
  priorPreview(station);
  localStorage.setItem('workerStation',station.id);
  const url=new URL(location.href);url.searchParams.set('station',station.id);history.replaceState(null,'',url);
}
function mimeType() {
  if (typeof MediaRecorder==='undefined') return '';
  const mime=['video/webm;codecs=vp8','video/webm','video/mp4'].find(m=>MediaRecorder.isTypeSupported(m));
  return mime||'';
}
async function openCamera() {
  if (W.stream || W.busy) return;
  W.busy=true;controls();
  try {
    await checkInspectionServer();
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) throw Error('เปิดหน้านี้ผ่าน HTTPS บนมือถือ หรือ localhost บนคอมพิวเตอร์ก่อนใช้งานกล้อง');
    if(!$('operator').value.trim())throw Error('เลือกสเตชั่นก่อนเปิดกล้อง');
    const device=$('camera').value;
    W.stream=await navigator.mediaDevices.getUserMedia({audio:false,video:device?{deviceId:{exact:device}}:{facingMode:{ideal:'environment'},width:{ideal:1280},height:{ideal:720}}});
    $('video').srcObject=W.stream;await $('video').play();
    W.archiveLinked=false;
    if(mimeType()){
      try{
        await CameraShare.start(W.stream,{source:'worker',station_id:Number($('station').value),operator:$('operator').value.trim(),video:$('video'),onerror:error=>{
          message('วิดีโอสำรองบันทึกไม่สำเร็จ แต่ระบบตรวจสีและจำนวนยังทำงานต่อ: '+error.message,'bad');
        }});
        W.archiveLinked=true;
      }catch(error){
        void CameraShare.stop(W.stream);
        $('scanHint').textContent='วิดีโอเป็นข้อมูลเสริม: '+error.message+' · ยังตรวจสีและจำนวนได้';
        message('วิดีโอสำรองใช้ไม่ได้ แต่ระบบตรวจสีและจำนวนยังทำงานต่อ: '+error.message,'bad');
      }
    }
    W.stream.getVideoTracks()[0].onended=()=>cameraFailure('กล้องถูกตัดการเชื่อมต่อ');
    $('cameraEmpty').hidden=true;$('cameraBadge').textContent='กล้องพร้อม · รอสแกน';
    const devices=await navigator.mediaDevices.enumerateDevices();
    const selected=W.stream.getVideoTracks()[0].getSettings().deviceId;
    $('camera').innerHTML=devices.filter(d=>d.kind==='videoinput').map((d,i)=>`<option value="${esc(d.deviceId)}">${esc(d.label || 'กล้อง '+(i+1))}</option>`).join('');
    if(selected)$('camera').value=selected;
    if ('BarcodeDetector' in window) {
      try { W.detector=new BarcodeDetector({formats:['qr_code']}); } catch { W.detector=null; }
    }
    scheduleQrScan(0);
    message('กล้องพร้อมแล้ว สแกน QR ของชิ้นงานเพื่อเริ่มงาน');$('qr').focus();
  } catch(e) { closeCamera();message(e.message,'bad'); }
  finally { W.busy=false;controls(); }
}
function closeCamera() {
  void CameraShare.stop(W.stream);
  W.stream?.getTracks().forEach(t=>t.stop());W.stream=null;
  $('video').srcObject=null;$('cameraEmpty').hidden=false;$('cameraBadge').textContent='ยังไม่เปิดกล้อง';controls();
}
async function cameraFailure(reason) {
  if (W.work && !W.busy) await endWork(true);
  closeCamera();message(reason+' กรุณาเปิดกล้องอีกครั้งก่อนสแกนงานถัดไป','bad');
}
const workerFrameCanvas=document.createElement('canvas');
const workerQrCanvas=document.createElement('canvas');
function resizeCameraView(){
  const video=$('video');
  if(video.videoWidth&&video.videoHeight)video.parentElement.style.setProperty('--camera-aspect',`${video.videoWidth} / ${video.videoHeight}`);
}
$('video').addEventListener('loadedmetadata',resizeCameraView);
$('video').addEventListener('resize',resizeCameraView);
function expandCameraView(expanded){
  document.body.classList.toggle('camera-expanded',expanded);
  $('expandCamera').setAttribute('aria-pressed',String(expanded));
  $('expandCamera').textContent=expanded?'ย่อภาพ ✕':'ขยายภาพ ⛶';
}
$('expandCamera').onclick=()=>expandCameraView(!document.body.classList.contains('camera-expanded'));
document.addEventListener('keydown',event=>{if(event.key==='Escape')expandCameraView(false);});
async function snapshot(canvas=workerFrameCanvas) {
  const v=$('video');
  if (!v.videoWidth || v.readyState<2) return null;
  const scale=canvas===workerQrCanvas?640/v.videoWidth:Math.min(1,384/Math.max(v.videoWidth,v.videoHeight));
  canvas.width=Math.round(v.videoWidth*scale);canvas.height=Math.round(v.videoHeight*scale);
  canvas.getContext('2d',{willReadFrequently:true}).drawImage(v,0,0,canvas.width,canvas.height);
  return new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',canvas===workerQrCanvas ? .72 : .62));
}
function inspectionSignature(canvas,steps){
  // This selects uploads only. The server still decides every step and pass.
  const pixels=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
  const ranges={green:[[36,65,55,85]],red:[[0,140,60,8],[169,140,60,179]],blue:[[91,85,50,132]],yellow:[[18,75,75,37]],orange:[[8,100,80,20]],purple:[[133,60,50,165]]};
  const palette=[...new Set(steps.map(step=>step.color))],counts=palette.map(()=>0);
  for(let i=0;i<pixels.length;i+=4){
    const r=pixels[i],g=pixels[i+1],b=pixels[i+2],v=Math.max(r,g,b),low=Math.min(r,g,b),delta=v-low;
    if(!delta||!v)continue;
    const s=255*delta/v;
    let h=(v===r?(g-b)/delta:v===g?(b-r)/delta+2:(r-g)/delta+4)*30;
    if(h<0)h+=180;
    for(let n=0;n<palette.length;n++){
      for(const range of ranges[palette[n]]||[]){
        if(h>=range[0]&&h<=range[3]&&s>=range[1]&&v>=range[2]){counts[n]++;break;}
      }
    }
  }
  const minimum=Math.max(12,canvas.width*canvas.height*.003);
  return counts.map(count=>count<minimum?0:Math.floor(Math.log2(count))).join(':');
}
async function captureInspectionFrame() {
  if(!W.work || !W.stream || W.busy || W.capturing || W.uploadError) return;
  W.capturing=true;
  const sid=W.work.id,at=performance.now()-W.frameEpoch;
  try {
    const blob=await snapshot();
    if(blob && W.work?.id===sid && !W.busy) {
      const signature=inspectionSignature(workerFrameCanvas,[...(W.work.station.prior_steps||[]),...W.work.station.steps]);
      const changed=signature!==W.lastFrameSignature;
      if(!changed&&!W.repeatFrame&&at-W.lastFrameQueued<2000)return;
      if(changed)W.repeatFrame=1;else W.repeatFrame=0;
      W.lastFrameSignature=signature;W.lastFrameQueued=at;
      if(W.frames.length>=100)throw Error('ภาพตรวจค้างส่งนานเกินไป กรุณาตรวจการเชื่อมต่อก่อนเริ่มรอบใหม่');
      W.frames.push({blob,at});
    }
  }catch(error){W.uploadError=error;}
  finally{W.capturing=false;if(W.work&&!W.sampling&&!W.busy)void tick();}
}
async function flushInspectionFrames(sid) {
  const frames=W.frames.splice(0,16);
  if(!frames.length)return null;
  const body=new FormData();
  frames.forEach(item=>body.append('frame',item.blob,'frame.jpg'));
  body.append('captured_ms',JSON.stringify(frames.map(item=>item.at)));
  const result=await api(`/api/flow/frame/${sid}`,{method:'POST',body});
  if(result.processed_frames!==frames.length)
    throw Error('เซิร์ฟเวอร์รับภาพตรวจไม่ครบ กรุณาอัปเดตเซิร์ฟเวอร์ก่อนเริ่มงานใหม่');
  return result;
}
async function scanQr() {
  let qr=null;
  if (W.detector) {
    try { qr=(await W.detector.detect($('video')))[0]?.rawValue || null; }
    catch { W.detector=null; }
  }
  if (!W.detector) {
    const blob=await snapshot(workerQrCanvas);if(!blob)return null;
    const body=new FormData();body.append('frame',blob,'scan.jpg');
    qr=(await api('/api/qr/decode',{method:'POST',body})).qr;
  }
  return qr;
}
function observeNextQr(qr) {
  // The initial QR sheet may contain neighboring codes. Do not interpret
  // those as a request to close the job that has just started.
  if(!qr){
    W.qrClearObservations++;
    if(W.qrClearObservations>=2)W.qrReady=true;
    W.nextQrCandidate=null;W.nextQrObservations=0;
    return;
  }
  if(!W.qrReady){
    W.qrClearObservations=0;
    return;
  }
  if (!qr || qr===(W.work?.source_qr||W.work?.qr)) {
    W.nextQrCandidate=null;W.nextQrObservations=0;
    return;
  }
  if(qr===W.nextQrCandidate)W.nextQrObservations++;
  else{W.nextQrCandidate=qr;W.nextQrObservations=1;}
  if(W.nextQrObservations>=2)W.nextQr=qr;
}
function queueNextQr(qr) {
  if(!qr||!W.work||qr===(W.work.source_qr||W.work.qr))return;
  W.nextQr=qr;W.nextQrCandidate=qr;W.nextQrObservations=2;
  message(`อ่าน QR งานถัดไป ${qr} แล้ว · กำลังตรวจเฟรมสุดท้ายและปิดวิดีโองานปัจจุบัน`);
  if(!W.busy&&!W.sampling)void tick();
}
function drawWorkerOverlay(data){
  const canvas=$('workerOverlay'),video=$('video');if(!video.videoWidth)return;
  const width=data.frame_width||640,height=data.frame_height||Math.round(width*video.videoHeight/video.videoWidth);
  canvas.width=width;canvas.height=height;const ctx=canvas.getContext('2d');ctx.clearRect(0,0,width,height);
  Object.entries(data.visible||{}).forEach(([color,item])=>{ctx.strokeStyle='#36dc9b';ctx.lineWidth=2;(item.objects||[]).forEach(object=>{const [x,y,w,h]=object.bbox;ctx.strokeRect(x,y,w,h)});if(item.bbox){const [x,y]=item.bbox;ctx.fillStyle=ctx.strokeStyle;ctx.font='13px sans-serif';ctx.fillText(`${color.toUpperCase()} ${item.count||0}`,x,Math.max(14,y-4))}});
}
async function startWork(qr) {
  if (W.work || W.busy || W.pending) return;
  W.lastQr=qr;W.busy=true;controls();
  W.nextQr=null;W.nextQrCandidate=null;W.nextQrObservations=0;
  W.qrReady=false;W.qrClearObservations=0;
  let started=null;
  try {
    await checkInspectionServer();
    if (!qr || !$('operator').value.trim()) throw Error('เลือกสเตชั่นและสแกน QR ก่อนเริ่มงาน');
    if (!W.stream || W.stream.getVideoTracks()[0]?.readyState!=='live') throw Error('เปิดกล้องก่อนสแกน QR');
    const mime=mimeType(),operator=$('operator').value.trim(),station_id=Number($('station').value);
    W.pending={qr,operator,station_id,mime_type:mime,auto_complete:true,camera_id:CameraShare.sessionId?.(W.stream)||null,request_id:crypto.randomUUID(),test_mode:window.Auth?.scope==='test',test_run_id:localStorage.getItem('sopTestRun')};
    sessionStorage.setItem('workerPending',JSON.stringify(W.pending));
    started=await safeRetry(()=>post('/api/flow/start',W.pending));
    W.work=started;sessionStorage.setItem('workerActive',started.id);
    clearPending();
    W.sequence=0;W.uploadError=null;W.queue=Promise.resolve();W.started=Date.now();
    W.frames=[];W.frameEpoch=performance.now();
    W.lastFrameSignature=null;W.lastFrameQueued=-Infinity;W.repeatFrame=0;
    W.recorder=mime?new MediaRecorder(W.stream,{mimeType:mime,videoBitsPerSecond:500000}):null;
    const recording=W.recording={recorder:W.recorder,queue:Promise.resolve(),sequence:0,error:null};
    const sid=started.id;
    if(W.recorder){
      W.recorder.ondataavailable=e=>{
        if (!e.data.size) return;
        const sequence=recording.sequence++;
        recording.queue=recording.queue.then(async()=>{
          if (recording.error) return;
          const body=new FormData();body.append('chunk',e.data,'part');
          await safeRetry(()=>api(`/api/flow/recording/${sid}/${sequence}`,{method:'POST',body}));
        }).catch(error=>{recording.error=error;if(W.recording===recording)W.uploadError=error;});
        W.queue=recording.queue;
      };
      W.recorder.onerror=()=>{recording.error=Error('การบันทึกวิดีโอขัดข้อง');if(W.recording===recording)W.uploadError=recording.error;};
      W.recorder.start(1500);
    }
    $('qr').value=qr;$('currentJob').textContent=qr;$('currentOperator').textContent=window.Auth?.account?.guest?'สเตชั่น '+station_id:'พนักงาน '+operator;
    $('videoLabel').textContent='● กำลังตรวจสีและจำนวน';$('cameraBadge').textContent='กำลังทำงาน';
    renderSteps(started.station.steps);localStorage.setItem('workerOperator',operator);
    priorPreview(started.station);
    message('เริ่มงาน '+qr+' · ทำตามขั้นตอนที่แสดง');
  } catch(e) {
    if(!started&&W.pending){
      if(e.status&&e.status<500){
        try {await api('/api/flow/requests/'+W.pending.request_id);}
        catch(check){if(check.status===404)clearPending();}
      }
      if(W.pending){message('ยังยืนยันคำขอเริ่มงานไม่ได้ · กดตรวจสถานะคำขอที่ค้างก่อนสแกนชิ้นถัดไป','bad');return;}
    }
    if (started) {
      try {
        await api(`/api/flow/abort/${started.id}`,{method:'POST'});
        if(W.archiveLinked)await CameraShare.unlinkWork(W.stream,started.id);
        W.archiveLinked=false;W.work=null;sessionStorage.removeItem('workerActive');
      }
      catch { message('ยังยืนยันการแยกงานไม่ได้ กรุณากดแยกงานออกอีกครั้ง','bad');return; }
    }
    message(e.message+' · นำงานนี้ออกแล้วสแกนชิ้นถัดไป','bad');
  } finally { W.busy=false;controls(); }
}
async function stopRecording() {
  return stopRecordingSession(W.recording);
}
async function stopRecordingSession(recording) {
  if(!recording)return;
  const recorder=recording.recorder;
  if (recorder?.state!=='inactive' && recorder) {
    await new Promise((resolve,reject)=>{
      const timeout=setTimeout(()=>reject(Error('หยุดบันทึกวิดีโอไม่สำเร็จ')),10000);
      recorder.onstop=()=>{clearTimeout(timeout);resolve();};recorder.stop();
    });
  }
  await recording.queue;
  if(recording.error)throw recording.error;
}
let historyBusy=false,historyRevision=0;
async function refreshWorkerHistory(){
  const operator=$('operator').value.trim(),station=$('station').value;
  if(!operator||!station){$('history').textContent='เลือกสเตชั่นเพื่อดูรายการล่าสุด';$('counts').textContent='—';return;}
  if(historyBusy)return;
  historyBusy=true;const revision=historyRevision;
  try{
    const params=new URLSearchParams({station_id:station,scope:window.Auth?.scope||'production'});
    const data=await api('/api/flow/my-history?'+params);
    if(revision!==historyRevision||operator!==$('operator').value.trim()||station!==$('station').value)return;
    const s=data.filtered_stats;
    $('counts').textContent='สเตชั่น '+station+' · ผ่าน '+s.passed+' · แยกพัก/หยุด '+s.quarantined+' · กำลังทำ/ปิดงาน '+s.running;
    $('history').innerHTML=data.attempts.filter(r=>r.ended_at).map(r=>{
      const inspection=r.result||{},passed=r.state==='passed';
      const concerns=(inspection.steps||[]).filter(step=>step.status!=='passed');
      const summary=inspection.completion_error||inspection.error;
      const recordingNotice=inspection.recording_error
        ?`<p>วิดีโอเป็นข้อมูลเสริม ไม่กระทบผลตรวจสีและจำนวน: ${esc(inspection.recording_error)}</p>`:'';
      const screenshot=r.frame_url||inspection.frame_url;
      const date=new Date(/(?:Z|[+-]\d\d:\d\d)$/.test(r.started_at)?r.started_at:r.started_at+'Z').toLocaleString('th-TH',{timeZone:'Asia/Bangkok'});
      return `<div class="worker-history-row"><span>${esc(date)}</span><strong>${esc(r.source_qr||r.qr)}</strong><span class="${passed?'good':'bad'}">${passed?'✓ ผ่าน / ส่งต่อ':r.state==='interrupted'?'⛔ หยุดกลางงาน':'⛔ แยกพัก / ล็อก QR'}</span>${r.video_url&&r.recording_available?`<a href="${esc(r.video_url)}" target="_blank" rel="noopener">ดูวิดีโอ ↗</a>`:''}${screenshot?`<a href="${esc(screenshot)}" target="_blank" rel="noopener">ภาพสรุปผล ↗</a>`:''}${concerns.length||summary||recordingNotice?`<details><summary>${passed?'รายละเอียดรายการ':'เหตุผลที่ยังไม่ผ่าน'}</summary>${summary?`<p>${esc(summary)}</p>`:''}${recordingNotice}${concerns.map(step=>`<p>${esc(step.name)}: ${esc(step.reason||labels[step.status]||step.status)}</p>`).join('')}</details>`:''}</div>`;
    }).join('')||'ยังไม่มีงานที่ปิดแล้ว';
  }catch(e){$('counts').textContent='โหลดประวัติไม่สำเร็จ: '+e.message;}
  finally{historyBusy=false;}
}
function addHistory(){historyRevision++;refreshWorkerHistory();}
$('operator').addEventListener('change',()=>{historyRevision++;refreshWorkerHistory();});
$('station').addEventListener('change',()=>{historyRevision++;refreshWorkerHistory();});
setInterval(()=>{if(!document.hidden)refreshWorkerHistory();},3000);
async function endWork(abort=false) {
  if (!W.work || W.busy) return;
  W.busy=true;controls();
  const work=W.work;
  message(abort?'กำลังปิดงาน':'กำลังบันทึกผลขั้นตอนที่ตรวจแล้ว');
  try {
    // Let the already submitted frame settle before deciding the final result.
    while(W.sampling) await new Promise(resolve=>setTimeout(resolve,50));
    let result,stopReason=W.uploadError?.message||'';
    try {
      while(W.frames.length){
        const data=await flushInspectionFrames(work.id);
        if(data?.completion){releasePassedWork(work,data.completion);return;}
      }
      await stopRecording();
      result=await api(`/api/flow/${abort?'abort':'finish'}/${work.id}`,{method:'POST'});
    } catch(error) {
      stopReason=error.message;
      try{await stopRecording();}catch(recordError){stopReason+=' · '+recordError.message;}
      // A lost finish response may already have committed a pass. Read before aborting.
      const saved=await api(`/api/flow/attempts/${work.id}`);
      result=saved.ended_at?saved:await api(`/api/flow/abort/${work.id}?reason=${encodeURIComponent(stopReason.slice(0,300))}`,{method:'POST'});
    }
    if(result.inspection){renderSteps(result.inspection.steps);renderPriorCheck(result.inspection.prior_check);}
    addHistory(work.qr,result);
    const passed=result.state==='passed';
    const inspection=result.inspection||result.result||{};
    const concerns=(inspection.steps||[]).filter(step=>step.status!=='passed');
    const reason=stopReason||inspection.recording_error||inspection.completion_error||inspection.error
      ||concerns.map(step=>`${step.name}: ${step.reason}`).join(' · ')||'ยังยืนยันขั้นตอนไม่ครบ';
    message(passed?`${work.source_qr||work.qr} ผ่านครบทุกขั้น · เริ่มงานถัดไปได้`
      :`${work.source_qr||work.qr} หยุดงาน: ${reason} · งานนี้ยังส่งต่อไม่ได้`,passed?'good':'bad');
    if(W.archiveLinked){
      try{await CameraShare.unlinkWork(W.stream,work.id);W.archiveLinked=false;}
      catch{message('บันทึกผลแล้ว แต่ยกเลิกการเชื่อมคลังกล้องไม่ได้ · ตรวจรายการกล้องย้อนหลัง','bad');}
    }
    sessionStorage.removeItem('workerActive');W.work=null;W.recorder=null;W.frames=[];
    $('qr').value='';$('currentJob').textContent='รอสแกนชิ้นถัดไป';$('videoLabel').textContent='รอสแกน QR ชิ้นถัดไป';$('cameraBadge').textContent='กล้องพร้อม · รอสแกน';
  } catch(e) {
    message('ยังยืนยันผลไม่ได้: '+e.message+' · ตรวจการเชื่อมต่อแล้วลองปิดงานด้วย QR งานถัดไปอีกครั้ง','bad');
  } finally { W.busy=false;controls();if(!W.work)$('qr').focus(); }
}
function releasePassedWork(work,completion){
  const recording=W.recording,stream=W.stream,archiveLinked=W.archiveLinked;
  const nextQr=W.nextQr;
  renderSteps(completion.inspection.steps);
  renderPriorCheck(completion.inspection.prior_check);
  sessionStorage.removeItem('workerActive');
  W.work=null;W.recording=null;W.recorder=null;W.frames=[];W.uploadError=null;
  $('qr').value='';$('currentJob').textContent='รอสแกนชิ้นถัดไป';
  $('videoLabel').textContent='รอสแกน QR ชิ้นถัดไป';$('cameraBadge').textContent='กล้องพร้อม · รอสแกน';
  message(`${work.source_qr||work.qr} ผ่านครบทุกขั้น · เริ่มงานถัดไปได้`,'good');
  controls();addHistory();
  const task=(async()=>{
    try{
      const unlink=archiveLinked?Promise.resolve().then(()=>CameraShare.unlinkWork(stream,work.id)).catch(()=>{}):Promise.resolve();
      await stopRecordingSession(recording);
      await safeRetry(()=>api(`/api/flow/finish/${work.id}`,{method:'POST'}));
      await unlink;addHistory();
    }catch(error){
      $('scanHint').textContent=`งาน ${work.source_qr||work.qr} ผ่านแล้ว แต่วิดีโอส่งไม่ครบ: ${error.message}`;
    }
  })();
  W.archiveTasks.add(task);void task.finally(()=>W.archiveTasks.delete(task));
  if(nextQr)setTimeout(()=>{if(!W.work&&W.stream&&!W.busy)void startWork(nextQr);},0);
}
async function tick() {
  if (!W.stream || W.busy || W.sampling || W.pending || !W.stations.length) return;
  W.sampling=true;
  let finish=false;
  try {
    if (W.work) {
      if (W.uploadError) { finish=true;return; }
      const sid=W.work.id;
      const data=await flushInspectionFrames(sid);if(!data)return;
      if(W.work?.id!==sid)return;
      renderSteps(data.steps);
      renderPriorCheck(data.prior_check);
      drawWorkerOverlay(data);
      if(data.completion?.state==='passed'){
        releasePassedWork(W.work,data.completion);return;
      }
      const concern=data.steps.find(step=>step.status!=='passed');
      message(data.prior_check?.required&&!data.prior_check.passed
        ? `ยังไม่พบสีของงานก่อนหน้าครบ ${data.prior_check.verified}/${data.prior_check.total} · แสดงงานเดิมให้กล้องเห็นก่อนเริ่มสีใหม่`
        : data.quarantined
        ? `⚠ ${W.work.source_qr||W.work.qr} · ${data.steps.find(step=>step.sequence_violation||step.ambiguous_sequence)?.reason||'ลำดับขั้นตอนยังไม่ชัดเจน'} · บันทึกวิดีโอต่อจนกว่าจะสแกน QR ชิ้นถัดไป`
        : data.verified===data.total
          ? `✓ สีและจำนวนครบ ${data.verified}/${data.total} · ผ่านอัตโนมัติแล้ว`
          : `กำลังตรวจ ${W.work.source_qr||W.work.qr} · ผ่าน ${data.verified}/${data.total} · ${concern?.reason||'รอสีตามลำดับ'} · ตรวจสีและจำนวนตามลำดับ`,
      data.quarantined?'bad':data.verified===data.total?'good':'');
      finish=data.verified===data.total&&data.total>0&&!data.quarantined;
    }
  } catch(e) {
    if(W.work) { W.uploadError=e;finish=true; }
    else message('อ่าน QR ไม่สำเร็จ: '+e.message+' · ใช้เครื่องสแกน USB หรือกรอกรหัสได้','bad');
  } finally {
    W.sampling=false;
    if(finish)await endWork(false);
    else if(W.nextQr && W.work && !W.busy){
      const nextQr=W.nextQr;
      W.nextQr=null;W.nextQrCandidate=null;W.nextQrObservations=0;
      await endWork(false);
      if(!W.work && W.stream && !W.uploadError)await startWork(nextQr);
      else if(W.work)W.nextQr=nextQr;
    }
  }
}
async function tickQr(){
  if(!W.stream||W.busy||W.pending||W.qrScanning||!W.stations.length||!$('operator').value.trim()){
    scheduleQrScan(700);return;
  }
  W.qrScanning=true;
  const stream=W.stream,workId=W.work?.id;
  try{
    const qr=await scanQr();
    if(W.stream!==stream||W.busy||W.pending||W.work?.id!==workId)return;
    if(W.work)observeNextQr(qr);
    else if(!qr)W.lastQr=null;
    else if(qr!==W.lastQr)await startWork(qr);
  }catch(error){
    if(W.stream===stream)$('scanHint').textContent='อ่าน QR ไม่สำเร็จ: '+error.message+' · ใช้เครื่องสแกน USB หรือพิมพ์รหัสได้ การตรวจงานยังทำต่อ';
  }finally{W.qrScanning=false;scheduleQrScan(W.work?1200:W.detector?80:250);}
}
function scheduleQrScan(delay){clearTimeout(W.qrTimer);W.qrTimer=setTimeout(tickQr,delay);}
$('openCamera').onclick=openCamera;
$('closeCamera').onclick=()=>{closeCamera();message('ปิดกล้องแล้ว');};
$('station').onchange=stationPreview;
$('scanForm').onsubmit=e=>{
  e.preventDefault();
  const qr=$('qr').value.trim();
  if(W.work)queueNextQr(qr);
  else startWork(qr);
};
async function recoverPending(){
  if(!W.pending||W.busy)return;
  W.busy=true;controls();
  try{
    let saved;
    try {saved=await api('/api/flow/requests/'+W.pending.request_id);}
    catch(e){
      if(e.status!==404)throw e;
      try {
        const started=await safeRetry(()=>post('/api/flow/start',W.pending));
        saved=await api('/api/flow/attempts/'+started.id);
      }catch(startError){
        if(!startError.status||startError.status>=500)throw startError;
        try {saved=await api('/api/flow/requests/'+W.pending.request_id);}
        catch(check){if(check.status!==404)throw check;clearPending();message(startError.message,'bad');return;}
      }
    }
    const result=saved.ended_at?saved:await safeRetry(()=>api('/api/flow/abort/'+saved.id,{method:'POST'}));
    addHistory(saved.qr,result);clearPending();sessionStorage.removeItem('workerActive');
    message('ตรวจสอบคำขอเดิมแล้ว · '+(result.state==='passed'?'งานผ่านและบันทึกแล้ว':'แยกชิ้นงานเดิมออก งานนี้ถูกล็อกแล้ว')+' · สแกนชิ้นถัดไปได้');
  }catch(e){message('ยังเชื่อมต่อเซิร์ฟเวอร์ไม่ได้: '+e.message+' · กรุณาตรวจสถานะอีกครั้งก่อนสแกนชิ้นใหม่','bad');}
  finally{W.busy=false;controls();}
}
$('separate').onclick=()=>recoverPending();
window.addEventListener('beforeunload',()=>{
  if(W.work)navigator.sendBeacon(`/api/flow/abort/${W.work.id}`,new Blob([JSON.stringify({csrf:window.Auth?.csrf||'',worker_mode:'station'})],{type:'application/json'}));
  W.stream?.getTracks().forEach(t=>t.stop());
});
document.addEventListener('visibilitychange',()=>{if(document.hidden && W.work)cameraFailure('หน้าจอถูกพักระหว่างทำงาน ชิ้นงานถูกแยกเพื่อตรวจสอบ');});
(async()=>{
  try {
    await checkInspectionServer();
    W.stations=await api('/api/flow/stations');
    $('station').innerHTML=W.stations.map(s=>`<option value="${s.id}">${esc(s.name)}</option>`).join('');
    const requested=Number(new URLSearchParams(location.search).get('station') || localStorage.getItem('workerStation') || 1);
    $('station').value=W.stations.some(s=>s.id===requested)?requested:1;
    $('operator').value=localStorage.getItem('workerOperator') || '';stationPreview();
    W.pending=JSON.parse(sessionStorage.getItem('workerPending')||'null');
    if(W.pending)await recoverPending();
    const previous=sessionStorage.getItem('workerActive');
    if(previous) {
      const saved=await api(`/api/flow/attempts/${previous}`);
      if(!saved.ended_at)await api(`/api/flow/abort/${previous}`,{method:'POST'});
      sessionStorage.removeItem('workerActive');
      message('งานก่อนหน้าถูกปิดหรือแยกพักแล้ว กรุณาตรวจชิ้นงานก่อนเปิดกล้องสแกนชิ้นถัดไป');
    }
    controls();refreshWorkerHistory();setInterval(captureInspectionFrame,80);setInterval(tick,80);scheduleQrScan(0);
    setInterval(()=>{const n=W.work?Math.floor((Date.now()-W.started)/1000):0;$('clock').textContent=String(Math.floor(n/60)).padStart(2,'0')+':'+String(n%60).padStart(2,'0');},500);
  } catch(e) { W.busy=true;controls();message('โหลดระบบไม่สำเร็จ: '+e.message+' · กรุณาโหลดหน้าใหม่','bad'); }
})();
