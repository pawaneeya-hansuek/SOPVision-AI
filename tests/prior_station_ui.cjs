const {chromium}=require('../.test-node/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
(async()=>{
 const fixture=JSON.parse(fs.readFileSync('.test-supervisor-ready.json','utf8'));
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true,args:[
  '--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream','--use-file-for-fake-video-capture='+fixture.portrait]});
 try{
  const context=await browser.newContext({permissions:['camera'],viewport:{width:390,height:844}});
  const page=await context.newPage(),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto('http://127.0.0.1:8766/worker?station=2');
  await page.waitForFunction(()=>window.Auth?.account?.guest&&document.querySelector('#station').options.length===3);
  assert(await page.locator('#priorCheck').isVisible());
  assert((await page.locator('#priorCheckTitle').textContent()).includes('0/2'));
  await page.locator('#openCamera').click();
  await page.waitForFunction(()=>document.querySelector('#video').videoWidth>0);
  const seed=await page.evaluate(async()=>{
   const qr='PRIOR-UI-'+Date.now();
   const bgr={green:'#2dbE1e',red:'#dc2828',blue:'#143cdc',yellow:'#dcdc14'};
   window.drawTestFrame=async(canvas,colors)=>{
    canvas.width=600;canvas.height=400;
    const ctx=canvas.getContext('2d');ctx.fillStyle='#5a5a5a';ctx.fillRect(0,0,600,400);
    colors.forEach((color,n)=>{ctx.fillStyle=bgr[color];ctx.fillRect(20+n*90,140,65,65);});
    return new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.8));
   };
   const previous=await post('/api/flow/start',{qr,station_id:1,operator:'TEST'});
   for(const colors of [['green'],['green','red']]){
    const body=new FormData();body.append('frame',await drawTestFrame(document.createElement('canvas'),colors),'frame.jpg');
    await api('/api/flow/frame/'+previous.id,{method:'POST',body});
   }
   const completed=await api('/api/flow/finish/'+previous.id,{method:'POST'});
   if(completed.state!=='passed')throw Error('Previous station did not pass');
   window.testColors=['blue'];const originalSnapshot=snapshot;
   snapshot=async(canvas=workerFrameCanvas)=>canvas===workerQrCanvas?originalSnapshot(canvas):drawTestFrame(canvas,window.testColors);
   return {qr,previous:previous.id};
  });
  await page.locator('#qr').fill(seed.qr);await page.locator('#start').click();
  await page.waitForFunction(()=>W.work);
  const sid=await page.evaluate(()=>W.work.id);
  await page.waitForFunction(()=>document.querySelector('#message').textContent.includes('งานก่อนหน้าครบ 0/2'));
  assert.equal((await page.locator('#progress').textContent()).trim(),'0 / 2');
  await page.evaluate(()=>{window.testColors=['green','blue'];});
  await page.waitForFunction(()=>document.querySelector('#priorCheckTitle').textContent.includes('1/2'));
  assert.equal((await page.locator('#progress').textContent()).trim(),'0 / 2');
  await page.evaluate(()=>{window.testColors=['green','red','blue'];});
  await page.waitForFunction(()=>document.querySelector('#priorCheckTitle').textContent.includes('ครบ 2/2')&&document.querySelector('#progress').textContent==='1 / 2');
  await page.evaluate(()=>{window.testColors=['yellow'];});
  await page.waitForFunction(()=>!W.work&&document.querySelector('#message').textContent.includes('ผ่านครบทุกขั้น'));
  await page.waitForFunction(()=>W.archiveTasks.size===0);
  const saved=await page.evaluate(id=>api('/api/flow/attempts/'+id),sid);
  assert.equal(saved.state,'passed');assert(saved.result.prior_check.passed);
  assert(saved.result.prior_check.steps.every(step=>step.source_attempt_id===seed.previous));
  assert(saved.result.evidence.handoff);
  assert.deepEqual(errors,[]);
  await page.screenshot({path:path.resolve('tmp/prior-station-ui-passed.png'),fullPage:true});
  await page.locator('#closeCamera').click();
  console.log('PASS: station 2 displays missing earlier colors, waits for green/red, then instantly confirms blue/yellow with persisted handoff evidence');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
