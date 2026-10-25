// Run the actual worker script with slow fetches and a deterministic camera.
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const elements=new Map(),trace=[],batchSizes=[];
function element(){return {value:'1',textContent:'',innerHTML:'',style:{},classList:{toggle(){},contains(){return false;}},
 addEventListener(){},focus(){},querySelector(){return null;},getContext(){return {drawImage(){trace.push('capture');},clearRect(){},strokeRect(){},fillText(){}};},
 toBlob(callback){setTimeout(()=>callback(new Blob(['jpeg'])),1);},videoWidth:640,videoHeight:480,readyState:4};}
const storage=()=>{const values=new Map();return {getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,String(value)),removeItem:key=>values.delete(key)};};
const context=vm.createContext({console,Blob,FormData,URL,URLSearchParams,AbortSignal,performance,
 setTimeout,clearTimeout,setInterval(){},crypto:require('node:crypto').webcrypto,
 document:{getElementById(id){if(!elements.has(id))elements.set(id,element());return elements.get(id);},
  createElement:element,addEventListener(){},querySelectorAll(){return [];},body:{classList:{contains(){return false;}}}},
 window:{Auth:{account:{guest:true}},addEventListener(){}},navigator:{},CameraShare:{},
 localStorage:storage(),sessionStorage:storage(),location:{href:'http://localhost/worker'},history:{replaceState(){}},
 fetch:async(url,options={})=>{
  let data={};
  if(url==='/api/flow/stations')data=[{id:1,name:'Test',steps:[]}];
  else if(url.startsWith('/api/flow/my-history'))data={filtered_stats:{passed:0,quarantined:0,running:0},attempts:[]};
  else if(url.startsWith('/api/flow/frame/')){
   batchSizes.push(options.body.getAll('frame').length);await delay(1500);
   data={steps:[],visible:{},verified:0,total:2,quarantined:false};
  }else if(url.startsWith('/api/flow/finish/')){
   assert(options.body.get('frame'),'Final image must be in the finish request');
   assert(trace.indexOf('recording-finished')<trace.lastIndexOf('capture'),'Final capture must follow recording upload');
   trace.push('finished');data={state:'passed',inspection:{steps:[]}};
  }
  return {ok:true,json:async()=>data};
 }});
vm.runInContext(fs.readFileSync('static/worker.js','utf8'),context);
(async()=>{
 await delay(20);
 vm.runInContext("W.stream={};W.work={id:'slow-work',qr:'WORK'};W.frameEpoch=performance.now();",context);
 vm.runInContext("observeNextQr('NEIGHBOR');observeNextQr('NEIGHBOR');",context);
 assert.equal(vm.runInContext('W.nextQr',context),null,'A neighboring QR on the initial sheet must not end the job');
 vm.runInContext("observeNextQr(null);observeNextQr(null);observeNextQr('NEXT');observeNextQr('NEXT');",context);
 assert.equal(vm.runInContext('W.nextQr',context),'NEXT','Scanning the next piece after clearing the QR remains available');
 vm.runInContext('W.nextQr=null;',context);
 await vm.runInContext('captureInspectionFrame()',context);
 const pending=vm.runInContext('tick()',context);
 for(let n=0;n<7;n++){await delay(20);await vm.runInContext('captureInspectionFrame()',context);}
 assert(vm.runInContext('W.sampling && W.frames.length>=6',context),'Capture must continue while fetch waits');
 await pending;
 await vm.runInContext('tick()',context);
 assert.deepEqual(batchSizes,[1,7],'No captured steps should be dropped during a slow response');
 assert.equal(vm.runInContext('W.frames.length',context),0);
 context.trace=trace;
 vm.runInContext("stopRecording=async()=>{trace.push('recording-finished');};",context);
 await vm.runInContext('endWork(false)',context);
 assert(trace.includes('finished'));
 assert.equal(vm.runInContext('W.work',context),null);
 console.log('Worker transport: captured 8 frames during slow fetch, preserved order, uploaded recording before atomic final inspection.');
})().catch(error=>{console.error(error);process.exitCode=1;});

