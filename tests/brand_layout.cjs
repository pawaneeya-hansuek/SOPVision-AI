const {chromium}=require('../.test-node/node_modules/playwright');
const assert=require('node:assert/strict'),path=require('node:path');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 try{
  const ctx=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
  const page=await ctx.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const base='http://127.0.0.1:8765';
  const login=await ctx.request.post(base+'/api/auth/login',{data:{username:'browseradmin',password:'Browser-Test-Only-739'}});
  assert.equal(login.status(),200,'isolated browser fixture login');
  for(const route of ['/login','/setup','/','/worker','/admin','/access']){
   await page.goto(base+route);
   await page.waitForFunction(()=>[...document.querySelectorAll('.brand-image')].length>0&&[...document.querySelectorAll('.brand-image')].every(i=>i.complete&&i.naturalWidth===1024));
   const imgs=page.locator('.brand-image');
   for(let i=0;i<await imgs.count();i++){
    const img=imgs.nth(i);assert((await img.getAttribute('src')).includes('sopvision-logo-current.png'));
    const shape=await img.evaluate(i=>({w:i.getBoundingClientRect().width,h:i.getBoundingClientRect().height,transform:getComputedStyle(i).transform}));
    assert(Math.abs(shape.w/shape.h-1024/338)<.05,'proportions '+route);assert.equal(shape.transform,'none','uncropped '+route);
   }
   assert((await page.locator('link[rel="icon"]').getAttribute('href')).includes('sopvision-logo-current.png'));
   if(route==='/')await page.screenshot({path:path.resolve('backups/brand-home-desktop.png'),fullPage:true});
   if(route==='/admin')await page.screenshot({path:path.resolve('backups/brand-admin-desktop.png'),fullPage:true});
   await page.setViewportSize({width:390,height:844});
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),'mobile overflow '+route);
   if(route==='/worker')await page.screenshot({path:path.resolve('backups/brand-worker-mobile.png'),fullPage:true});
   await page.setViewportSize({width:1440,height:1000});
  }
  const response=await ctx.request.get(base+'/api/flow/admin/export?format=html');assert.equal(response.status(),200);
  const report=await response.text();assert(report.includes('data:image/png;base64,')&&report.includes('alt="SOPVision AI'));
  const asset=await ctx.request.get(base+'/static/brand/sopvision-logo-current.png');
  assert(report.includes((await asset.body()).toString('base64')),'report embeds exact new logo');
  assert.deepEqual(errors,[]);
  console.log('PASS: shared original logo and favicon across all pages, correct proportions without crop, desktop/mobile layouts, exact logo embedded in printable report; no JS errors.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
