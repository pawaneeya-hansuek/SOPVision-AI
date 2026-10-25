/* Share and archive each explicitly opened camera, independent of QR jobs. */
'use strict';
(() => {
  const instances=new Map();
  const REQUEST_TIMEOUT_MS=30000;
  async function request(url,options={}) {
    const run=async()=>{
      const response=await fetch(url,{...options,cache:'no-store',signal:AbortSignal.timeout(REQUEST_TIMEOUT_MS)});
      const body=await response.json();
      if(!response.ok){const e=Error(body.detail||'ส่งข้อมูลกล้องไม่สำเร็จ');e.status=response.status;throw e;}
      return body;
    };
    for(let attempt=0;attempt<3;attempt++){
      try{return await run();}catch(e){
        const transient=!e.status||[408,429,500,502,503,504].includes(e.status);
        if(!transient||attempt===2)throw e;
        await new Promise(resolve=>setTimeout(resolve,300*(2**attempt)));
      }
    }
  }
  class Share {
    constructor(stream,options){
      this.stream=stream;this.options=options;this.id=crypto.randomUUID();
      this.token=crypto.randomUUID()+crypto.randomUUID();this.index=0;this.frameIndex=0;
      this.queue=Promise.resolve();this.error=null;this.stopping=false;this.previewBusy=false;this.pendingBytes=0;
      this.canvas=document.createElement('canvas');
      this.notice=document.createElement('div');this.notice.setAttribute('role','status');
      Object.assign(this.notice.style,{position:'fixed',bottom:'16px',left:'16px',zIndex:1000,padding:'10px 16px',borderRadius:'10px',background:'#166534',color:'white',fontSize:'12px',maxWidth:'90vw',boxShadow:'0 4px 18px #0002'});
      const panel=this.options.video?.closest?.('.worker-camera')?.querySelector('.worker-scan');
      if(panel){Object.assign(this.notice.style,{position:'static',marginTop:'12px',maxWidth:'100%',boxShadow:'none'});panel.appendChild(this.notice);}
      else document.body.appendChild(this.notice);
      this.say('กำลังเชื่อมกล้องให้แอดมิน…');
    }
    say(text,bad=false){this.notice.textContent=text;this.notice.style.background=bad?'#b42318':'#166534';}
    linkWork(qr,attemptId){
      return request(`/api/cameras/${this.id}/work-link`,{method:'POST',headers:{'Content-Type':'application/json','X-Camera-Key':this.token},body:JSON.stringify({qr,attempt_id:attemptId})});
    }
    unlinkWork(attemptId){
      return request(`/api/cameras/${this.id}/work-link`,{method:'POST',headers:{'Content-Type':'application/json','X-Camera-Key':this.token},body:JSON.stringify({qr:null,attempt_id:attemptId})});
    }
    async start(){
      try{
        if(typeof MediaRecorder==='undefined')throw Error('เบราว์เซอร์ไม่รองรับบันทึกย้อนหลัง');
        this.mime=['video/webm;codecs=vp8','video/webm','video/mp4'].find(m=>MediaRecorder.isTypeSupported(m));
        if(!this.mime)throw Error('ไม่พบรูปแบบวิดีโอที่รองรับ');
        this.video=this.options.video||document.createElement('video');
        if(!this.options.video){this.video.muted=true;this.video.playsInline=true;this.video.srcObject=this.stream;await this.video.play();}
        const info=await request('/api/cameras/open',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
          id:this.id,token:this.token,source:this.options.source,station_id:this.options.station_id||null,
          operator:this.options.operator||'',device_label:(this.stream.getVideoTracks()[0]?.label||'กล้อง').slice(0,200),mime_type:this.mime})});
        this.registered=true;
        this.startSegment();
        this.previewTimer=setInterval(()=>this.preview(),this.options.source==='worker'?1000:info.preview_ms);
        this.rotateTimer=setInterval(()=>this.rotate(),info.segment_ms);
        this.stream.getVideoTracks()[0]?.addEventListener('ended',()=>this.stop('กล้องถูกตัดการเชื่อมต่อ'),{once:true});
        void this.preview();
        if(this.error)throw this.error;
        this.say('● แอดมินดูสดได้ • กำลังบันทึกย้อนหลัง');
        return this;
      }catch(e){await this.stop(e.message);throw e;}
    }
    enqueue(action){
      this.queue=this.queue.then(async()=>{if(!this.error)await action();}).catch(e=>this.fail(e));
    }
    fail(error){
      if(this.error)return;
      this.error=error;this.say('กล้องส่งข้อมูลไม่สำเร็จ: '+error.message,true);
      // Run outside the upload queue: stop must be able to await that queue.
      queueMicrotask(()=>{try{this.options.onerror?.(error);}finally{void this.stop(error.message);}});
    }
    startSegment(){
      const ctx={index:this.index++,sequence:0,bytes:0};
      ctx.recorder=new MediaRecorder(this.stream,{mimeType:this.mime,videoBitsPerSecond:this.options.source==='worker'?350000:650000});
      ctx.stopped=new Promise(resolve=>ctx.resolve=resolve);
      ctx.recorder.ondataavailable=e=>{
        if(!e.data.size)return;
        const sequence=ctx.sequence++;ctx.bytes+=e.data.size;this.pendingBytes+=e.data.size;
        if(this.pendingBytes>20*1024*1024){this.fail(Error('เครือข่ายส่งวิดีโอไม่ทัน'));return;}
        this.enqueue(async()=>{
          try{
            const body=new FormData();body.append('chunk',e.data,'camera-part');
            await request(`/api/cameras/${this.id}/segments/${ctx.index}/chunks/${sequence}`,{method:'POST',headers:{'X-Camera-Key':this.token},body});
          }finally{this.pendingBytes-=e.data.size;}
        });
      };
      ctx.recorder.onstop=()=>{
        if(ctx.sequence)this.enqueue(()=>request(`/api/cameras/${this.id}/segments/${ctx.index}/finish`,{method:'POST',headers:{'Content-Type':'application/json','X-Camera-Key':this.token},body:JSON.stringify({chunks:ctx.sequence,bytes:ctx.bytes})}));
        ctx.resolve();
      };
      ctx.recorder.onerror=()=>this.fail(Error('บันทึกคลิปกล้องขัดข้อง'));
      this.segment=ctx;ctx.recorder.start(1000);
    }
    async stopSegment(ctx){
      if(!ctx)return;
      if(ctx.recorder.state!=='inactive')ctx.recorder.stop();
      let timer;
      try{await Promise.race([ctx.stopped,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('ปิดคลิปไม่สำเร็จ')),10000);})]);}
      finally{clearTimeout(timer);}
    }
    async rotate(){
      if(this.stopping||this.rotating)return;
      this.rotating=true;
      try{await this.stopSegment(this.segment);if(!this.stopping&&!this.error)this.startSegment();}
      catch(e){this.fail(e);}finally{this.rotating=false;}
    }
    async preview(){
      if(this.stopping||this.previewBusy||!this.video.videoWidth||this.video.readyState<2||this.lastVideoTime===this.video.currentTime)return;
      this.previewBusy=true;
      try{
        this.lastVideoTime=this.video.currentTime;
        const scale=Math.min(1,(this.options.source==='worker'?320:640)/Math.max(this.video.videoWidth,this.video.videoHeight));
        this.canvas.width=Math.round(this.video.videoWidth*scale);this.canvas.height=Math.round(this.video.videoHeight*scale);
        this.canvas.getContext('2d').drawImage(this.video,0,0,this.canvas.width,this.canvas.height);
        const blob=await new Promise(resolve=>this.canvas.toBlob(resolve,'image/jpeg',.65));
        if(!blob)throw Error('อ่านภาพจากกล้องไม่ได้');
        const body=new FormData();body.append('frame',blob,'camera.jpg');
        await request(`/api/cameras/${this.id}/frame/${this.frameIndex++}`,{method:'POST',headers:{'X-Camera-Key':this.token},body});
      }catch(e){if(!this.stopping)this.fail(e);}finally{this.previewBusy=false;}
    }
    stop(reason=''){
      if(this.stopPromise)return this.stopPromise;
      this.stopping=true;clearInterval(this.previewTimer);clearInterval(this.rotateTimer);
      this.stopPromise=(async()=>{
        if(!this.error)this.say('กำลังเก็บคลิปท้ายสุด กรุณารอ…');
        try{await this.stopSegment(this.segment);}catch(e){this.error=this.error||e;}
        await this.queue;
        if(this.registered){
          try{await request(`/api/cameras/${this.id}/close`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:this.token,csrf:window.Auth?.csrf||'',worker_mode:location.pathname==='/worker'?'station':undefined,error:(this.error?.message||reason).slice(0,300)})});}
          catch(e){this.error=this.error||e;}
        }
        if(!this.options.video){this.video?.pause();if(this.video)this.video.srcObject=null;}
        if(this.error)this.say('บันทึกกล้องไม่ครบ: '+this.error.message,true);
        else{this.say('ปิดกล้องแล้ว • บันทึกย้อนหลังแล้ว');setTimeout(()=>this.notice.remove(),4000);}
        instances.delete(this.stream);
      })();
      return this.stopPromise;
    }
    beacon(){
      if(this.registered&&!this.stopping)navigator.sendBeacon(`/api/cameras/${this.id}/close`,new Blob([JSON.stringify({token:this.token,csrf:window.Auth?.csrf||'',worker_mode:location.pathname==='/worker'?'station':undefined,error:'หน้ากล้องถูกปิด คลิปท้ายสุดอาจไม่ครบ'})],{type:'application/json'}));
    }
  }
  window.CameraShare={
    sessionId(stream){const instance=instances.get(stream);return instance?.registered&&!instance.stopping?instance.id:null;},
    async start(stream,options){
      if(instances.has(stream))return instances.get(stream);
      const instance=new Share(stream,options);instances.set(stream,instance);
      return instance.start();
    },
    linkWork(stream,qr,attemptId){
      const instance=instances.get(stream);
      if(!instance)throw Error('ไม่พบเซสชันกล้องสำหรับเชื่อมงาน');
      return instance.linkWork(qr,attemptId);
    },
    unlinkWork(stream,attemptId){
      const instance=instances.get(stream);
      if(!instance)throw Error('ไม่พบเซสชันกล้องสำหรับยกเลิกการเชื่อมงาน');
      return instance.unlinkWork(attemptId);
    },
    stop(stream,reason=''){return instances.get(stream)?.stop(reason)||Promise.resolve();}
  };
  window.addEventListener('pagehide',()=>instances.forEach(instance=>instance.beacon()));
})();
