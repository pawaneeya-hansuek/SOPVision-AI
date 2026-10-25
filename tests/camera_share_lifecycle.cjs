/* Browser recording lifecycle contracts without camera hardware or user data. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {webcrypto}=require('node:crypto');
const code=fs.readFileSync(require('node:path').join(__dirname,'../static/camera-share.js'),'utf8');

function environment(failUploads=false){
  const calls=[],recorders=[],intervals=new Map();let next=0,uploadFailures=0;
  const video={videoWidth:640,videoHeight:360,readyState:4,currentTime:1,play:async()=>{},pause(){}};
  class Recorder{
    static isTypeSupported(mime){return mime.startsWith('video/webm');}
    constructor(){this.state='inactive';recorders.push(this);}
    start(){this.state='recording';}
    data(text){this.ondataavailable?.({data:new Blob([text])});}
    stop(){this.state='inactive';queueMicrotask(()=>{this.data('final-bytes');this.onstop?.();});}
  }
  const node=()=>({style:{},setAttribute(){},remove(){}});
  const context={console,Blob,FormData,MediaRecorder:Recorder,crypto:webcrypto,AbortSignal,queueMicrotask,
    setInterval(fn,ms){const id=++next;intervals.set(id,{fn,ms});return id;},clearInterval(id){intervals.delete(id);},
    setTimeout(fn,ms){return ms===4000?0:setTimeout(fn,ms);},clearTimeout,
    document:{body:{appendChild(){}},createElement(type){if(type==='video')return video;if(type==='canvas')return{getContext:()=>({drawImage(){}}),toBlob(cb){cb(new Blob(['jpeg']));}};return node();}},
    navigator:{sendBeacon(){}},location:{pathname:'/worker'},window:{addEventListener(){}},
    fetch:async(url,options)=>{
      const entry={url,options};
      if(options.body instanceof FormData){const b=options.body.get('chunk')||options.body.get('frame');entry.bytes=b.size;}
      else if(options.body)entry.body=JSON.parse(options.body);
      calls.push(entry);
      if(failUploads===true&&url.includes('/chunks/'))return{ok:false,status:507,json:async()=>({detail:'disk full'})};
      if(failUploads==='transient'&&url.includes('/chunks/')&&uploadFailures++===0)return{ok:false,status:503,json:async()=>({detail:'temporary disconnect'})};
      return{ok:true,status:200,json:async()=>url.endsWith('/open')?{segment_ms:30000,preview_ms:250}:{}};
    }};
  vm.createContext(context);vm.runInContext(code,context);
  const stream={getVideoTracks:()=>[{label:'Synthetic test camera',addEventListener(){}}]};
  return{share:context.window.CameraShare,calls,recorders,intervals,video,stream};
}

(async()=>{
  const test=environment();
  const instance=await test.share.start(test.stream,{source:'worker',station_id:1,operator:'TEST',video:test.video});
  assert(test.calls.some(c=>c.url==='/api/cameras/open'));
  assert(test.calls.some(c=>c.url.includes('/frame/0')));
  assert(!test.calls.some(c=>c.url.startsWith('/api/flow/')),'Camera must work without any QR job');
  test.recorders[0].data('first-data');
  const rotate=[...test.intervals.values()].find(t=>t.ms===30000);
  await rotate.fn();
  assert.equal(test.recorders.length,2,'Next recording must start at rotation');
  test.recorders[1].data('next-data');
  await test.share.stop(test.stream);
  const finishes=test.calls.filter(c=>c.url.endsWith('/finish'));
  assert.equal(finishes.length,2,'Both standalone clips must be finalized');
  for(const [index,finish] of finishes.entries()){
    const pieces=test.calls.filter(c=>c.url.includes(`/segments/${index}/chunks/`));
    assert.equal(finish.body.chunks,pieces.length,'Final fragment must be uploaded before finish');
    assert.equal(finish.body.bytes,pieces.reduce((sum,c)=>sum+c.bytes,0));
  }
  assert(test.calls.at(-1).url.endsWith('/close'));
  assert.equal(test.calls.at(-1).body.error,'');
  assert.equal(test.intervals.size,0);
  await instance.stop();
  assert.equal(test.calls.filter(c=>c.url.endsWith('/close')).length,1);

  const failure=environment(true);let reported=false;
  const bad=await failure.share.start(failure.stream,{source:'live',video:failure.video,onerror(){reported=true;}});
  failure.recorders[0].data('cannot-save');
  // Settle fetch/recording callbacks, then await the public close contract.
  await new Promise(resolve=>setImmediate(resolve));
  await bad.stop();
  assert(reported,'Recording failure must be visible to the caller');
  assert(!failure.calls.some(c=>c.url.endsWith('/finish')),'Unsaved recording must not be marked complete');
  assert.equal(failure.calls.at(-1).body.error,'disk full');
  const recovery=environment('transient');
  const recovered=await recovery.share.start(recovery.stream,{source:'worker',video:recovery.video});
  recovery.recorders[0].data('retry-same-fragment');
  await recovered.queue;
  await recovered.stop();
  assert.equal(recovered.error,null,'A brief disconnect must recover');
  const retries=recovery.calls.filter(c=>c.url.endsWith('/chunks/0'));
  assert.equal(retries.length,2);
  assert.equal(retries[0].bytes,retries[1].bytes,'Retries must preserve the exact fragment');
  assert.equal(recovery.calls.find(c=>c.url.endsWith('/finish')).body.chunks,2);
  console.log('Camera lifecycle: idle preview, 30s rotation, final fragment, idempotent close and disk failure passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
