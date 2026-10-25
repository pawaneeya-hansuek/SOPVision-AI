const {chromium}=require('../.test-node/node_modules/playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true,args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream']});
 const errors=[],batches=[];
 try{
  const page=await browser.newPage({permissions:['camera'],viewport:{width:390,height:1000}});
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto('http://127.0.0.1:8765/worker?station=1');
  await page.waitForFunction(()=>window.Auth?.account?.guest&&W.stations.length===3);
  await page.evaluate(()=>{
   const canvas=document.createElement('canvas');canvas.width=640;canvas.height=480;
   let assemblyHasCover=false;
   window.drawTestAssembly=(cover=false)=>{
    assemblyHasCover=cover;
    const ctx=canvas.getContext('2d');ctx.fillStyle='rgb(90,90,90)';ctx.fillRect(0,0,640,480);
    ctx.fillStyle='rgb(45,190,30)';ctx.fillRect(90,140,66,66);
    if(cover){ctx.fillStyle='rgb(220,40,40)';ctx.fillRect(190,140,66,66);}
   };
   drawTestAssembly();
   setInterval(()=>drawTestAssembly(assemblyHasCover),50);
   navigator.mediaDevices.getUserMedia=async()=>canvas.captureStream(20);
  });
  await page.route('**/api/flow/frame/*',async route=>{
   const body=route.request().postDataBuffer().toString('latin1');
   batches.push((body.match(/name="frame"/g)||[]).length);
   await new Promise(resolve=>setTimeout(resolve,900));
   await route.continue();
  });
  await page.locator('#openCamera').click();
  await page.waitForFunction(()=>W.stream&&!W.busy);
  await page.locator('#qr').fill('SLOW-NETWORK-BROWSER-'+Date.now());
  await page.locator('#start').click();
  await page.waitForFunction(()=>W.work&&!W.busy);
  await page.waitForFunction(()=>W.sampling&&W.frames.length>=3);
  assert.equal(await page.locator('#finishWork').count(),0,'Manual finish control must not be present');
  await page.waitForFunction(()=>document.querySelector('#progress').textContent==='1 / 2');
  await page.evaluate(()=>drawTestAssembly(true));
  await page.waitForFunction(()=>document.querySelector('#progress').textContent==='2 / 2');
  await page.waitForFunction(()=>!W.work&&!W.busy,{timeout:30000});
  assert.match(await page.locator('#message').innerText(),/ผ่านครบทุกขั้น/);
  assert(batches.some(count=>count>=3),'Captured frames must accumulate during slow requests');
  assert.equal(errors.length,0,errors.join('\n'));
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2));
  await page.locator('#closeCamera').click();
  console.log(JSON.stringify({passed:true,delayedRequestMs:900,batchSizes:batches,errors}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
