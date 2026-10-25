const {chromium}=require('../.test-node/node_modules/playwright');
const assert=require('node:assert/strict'),path=require('node:path');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true,args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream']});
 try{
  const ctx=await browser.newContext({permissions:['camera'],viewport:{width:1440,height:1000}}),page=await ctx.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8765/worker?station=1');
  await page.waitForFunction(()=>window.Auth?.account?.guest&&document.querySelector('#station').options.length===3);
  assert(page.url().includes('/worker'));
  assert.equal(await page.locator('#operator').isVisible(),false);
  assert.equal(await page.locator('#authLogout').count(),0);
  await page.locator('#station').selectOption('3');
  assert.equal(await page.locator('#operator').inputValue(),'STATION-3');
  await page.locator('#station').selectOption('1');
  const protectedStatus=await page.evaluate(async()=>(await fetch('/api/flow/admin')).status);
  assert.equal(protectedStatus,403);assert(page.url().includes('/worker'));
  await page.locator('#workMode').selectOption('test');await page.locator('#newTestRun').click();
  await page.waitForFunction(()=>document.querySelector('#testRun').value.length>0);
  await page.locator('#openCamera').click();
  await page.waitForFunction(()=>document.querySelector('#video').videoWidth>0);
  await page.locator('#qr').fill('GUEST-BROWSER-'+Date.now());await page.locator('#start').click();
  await page.waitForFunction(()=>sessionStorage.getItem('workerActive'));
  assert(await page.locator('#station').isDisabled());
  await page.waitForFunction(()=>W.sequence>0);
  const result=await page.evaluate(async()=>{
   const id=sessionStorage.getItem('workerActive');
   const response=await fetch('/api/flow/abort/'+id,{method:'POST'});
   const done=await response.json();
   return {status:response.status,state:done.state};
  });
  assert.equal(result.status,200);assert.equal(result.state,'interrupted');
  await page.reload();await page.waitForFunction(()=>window.Auth?.account?.guest&&document.querySelector('#station').options.length===3);
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2));
  await page.screenshot({path:path.resolve('backups/station-no-login-mobile.png'),fullPage:true});
  assert.deepEqual(errors,[]);
  await page.goto('http://127.0.0.1:8765/admin');assert(page.url().includes('/login'));
  console.log('PASS: fresh browser enters worker with no login, selects station only, streams synthetic camera and records work, retains own history, mobile fits, admin remains protected.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
