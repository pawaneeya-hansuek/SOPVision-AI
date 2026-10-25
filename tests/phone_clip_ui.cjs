// Run against tests/serve_supervisor_ui.py; never writes production records.
const {chromium}=require('../.test-node/node_modules/playwright');
const assert=require('node:assert/strict'),path=require('node:path');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true,args:[
  '--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream',
  '--use-file-for-fake-video-capture='+path.resolve('tmp/inspection-20261022/phone-replay.y4m')]});
 try{
  const context=await browser.newContext({permissions:['camera'],viewport:{width:390,height:844}});
  const page=await context.newPage(),errors=[],batches=[];
  let releaseVideos;
  const videoGate=new Promise(resolve=>{releaseVideos=resolve;});
  await page.route('**/api/flow/recording/*/*',async route=>{
   await videoGate;await route.continue();
  });
  page.on('pageerror',e=>errors.push(e.message));
  page.on('response',async response=>{
   if(response.url().includes('/api/flow/frame/'))batches.push({...await response.json(),sid:response.url().split('/').pop(),receivedAt:Date.now()});
  });
  await page.addInitScript(()=>{delete window.BarcodeDetector;});
  await page.route('**/api/qr/decode',async route=>{
   await new Promise(resolve=>setTimeout(resolve,2500));
   try{await route.fulfill({status:200,contentType:'application/json',body:'{"qr":null}'});}catch{}
  });
  let frameRequests=0;
  await page.route('**/api/flow/frame/*',async route=>{
   await new Promise(resolve=>setTimeout(resolve,frameRequests++===0?2500:80));await route.continue();
  });
  await page.goto('http://127.0.0.1:8766/worker?station=1');
  await page.waitForFunction(()=>window.Auth?.account?.guest&&document.querySelector('#station').options.length===3);
  await page.locator('#openCamera').click();
  await page.waitForFunction(()=>document.querySelector('#video').videoHeight>0);
  await page.locator('#qr').fill('PHONE-CLIP-END-TO-END-'+Date.now());
  await page.locator('#start').click();
  await page.waitForFunction(()=>!!W.work);
  const sid=await page.evaluate(()=>W.work.id);
  const epochWall=Date.now()-await page.evaluate(()=>performance.now()-W.frameEpoch);
  await page.waitForFunction(()=>!W.work&&document.querySelector('#message').textContent.includes('ผ่านครบทุกขั้น'),{},{timeout:25000});
  let saved=await page.evaluate(async id=>api('/api/flow/attempts/'+id),sid);
  assert.equal(saved.state,'passed');
  assert.equal(saved.result.verified,2);
  assert.deepEqual(saved.result.events.map(e=>e.color),['green','red']);
  assert(saved.result.events.every(e=>e.time===e.confirmed_at),'Each color must confirm in its first frame');
  assert(batches.some(b=>b.verified===1),'Green must show 1/2 before red is seen');
  assert.equal(saved.recorded_chunks,0,'Pass must commit while video uploads are held');
  assert(saved.result.recording_pending);
  assert(batches.some(b=>b.completion?.state==='passed'),'Pass must be in the last color response');
  assert(!await page.locator('#start').isDisabled(),'The next QR must be ready before video upload');
  const completedFrames=saved.result.frames;
  assert(completedFrames<40,'Unchanged video must not flood the inspection upload queue');
  const firstGreen=batches.find(b=>b.sid===sid&&b.verified===1);
  const lastColor=batches.find(b=>b.sid===sid&&b.completion?.state==='passed');
  const feedbackDelay=Math.max(firstGreen.receivedAt-epochWall-firstGreen.events[0].confirmed_at*1000,
    lastColor.receivedAt-epochWall-lastColor.events.at(-1).confirmed_at*1000);
  assert(feedbackDelay<1000,'Color feedback must arrive within one second despite slow background uploads');
  await page.locator('#qr').fill('NEXT-WHILE-PREVIOUS-VIDEO-PENDING-'+Date.now());
  await page.locator('#start').click();
  await page.waitForFunction(previous=>W.work&&W.work.id!==previous,sid);
  releaseVideos();
  await page.waitForFunction(()=>W.archiveTasks.size===0,{},{timeout:15000});
  saved=await page.evaluate(async id=>api('/api/flow/attempts/'+id),sid);
  assert(saved.video_url&&saved.recorded_chunks>0&&saved.recorded_bytes>200);
  assert(!saved.result.recording_pending);
  assert.equal(saved.result.frames,completedFrames,'Background archiving must not inspect another final image');
  assert(batches.some(b=>b.processed_frames>1),'Delayed uploads must process all frames in batches');
  assert(batches.filter(b=>b.sid===sid).every(b=>!b.quarantined));
  assert.equal((await page.request.get(new URL(saved.video_url,page.url()).href)).status(),200);
  assert.deepEqual(errors,[]);
  await page.screenshot({path:path.resolve('tmp/inspection-20261022/phone-replay-passed.png'),fullPage:true});
  console.log('PASS: last color commits pass with video uploads held; next job starts immediately; background video saved; no final image inspection; frames='+saved.result.frames+'; color feedback delay='+Math.round(feedbackDelay)+'ms');
  await page.evaluate(()=>endWork(true));
  await page.locator('#closeCamera').click();
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
