const {chromium}=require('../.test-node/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const previews=path.resolve('output/previews');fs.mkdirSync(previews,{recursive:true});
(async()=>{
 const fixture=JSON.parse(fs.readFileSync('.test-supervisor-ready.json','utf8'));
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true,args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream','--use-file-for-fake-video-capture='+fixture.portrait]});
 try{
  const ctx=await browser.newContext({permissions:['camera'],viewport:{width:390,height:844}}),page=await ctx.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{delete window.BarcodeDetector;});
  await page.route('**/api/health',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({ok:true})}));
  await page.goto('http://127.0.0.1:8766/worker?station=1');
  await page.waitForFunction(()=>document.querySelector('#message').textContent.includes('เซิร์ฟเวอร์ตรวจงานยังไม่ได้อัปเดต'));
  assert(await page.locator('#openCamera').isDisabled(),'Old backend must not allow a job to start');
  await page.unroute('**/api/health');
  let inspectionRequests=0;
  page.on('request',request=>{if(request.url().includes('/api/flow/frame/'))inspectionRequests++;});
  await page.route('**/api/qr/decode',async route=>{
    await new Promise(resolve=>setTimeout(resolve,2500));
    try{await route.fulfill({status:200,contentType:'application/json',body:'{"qr":null}'});}catch{}
  });
  await page.goto('http://127.0.0.1:8766/worker?station=1');
  await page.waitForFunction(()=>window.Auth?.account?.guest&&document.querySelector('#station').options.length===3);
  await page.locator('#openCamera').click();
  await page.waitForFunction(()=>document.querySelector('#video').videoHeight===568);
  const captureSize=await page.evaluate(async()=>{
    await snapshot();return [workerFrameCanvas.width,workerFrameCanvas.height];
  });
  assert(Math.max(...captureSize)<=640,'Portrait inspection frames must have a bounded long edge');
  await page.route('**/api/flow/frame/protocol-probe',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({verified:0})}));
  const rejected=await page.evaluate(async()=>{
    W.frames.push({blob:await snapshot(),at:0});
    try{await flushInspectionFrames('protocol-probe');return false;}catch(error){return error.message.includes('เซิร์ฟเวอร์รับภาพตรวจไม่ครบ');}
  });
  assert(rejected,'A backend that silently accepts only one frame must be rejected');
  await page.unroute('**/api/flow/frame/protocol-probe');
  const size=await page.locator('#video').boundingBox();assert(size.width>300&&size.height>500,'Portrait camera must fill a large display');
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2));
  await page.locator('.worker-camera').screenshot({path:path.join(previews,'worker-large-camera-preview.png')});
  await page.locator('#expandCamera').click();
  assert.equal(await page.locator('#expandCamera').getAttribute('aria-pressed'),'true');
  const expanded=await page.locator('.worker-video').boundingBox();assert(expanded.height>800&&expanded.width>360);
  await page.keyboard.press('Escape');assert.equal(await page.locator('#expandCamera').getAttribute('aria-pressed'),'false');
  inspectionRequests=0;
  await page.locator('#qr').fill('QR-SCAN-MUST-NOT-STALL-'+Date.now());await page.locator('#start').click();
  await page.waitForFunction(()=>!!W.work);
  await page.waitForTimeout(1500);
  assert(inspectionRequests>=2&&inspectionRequests<=4,'Inspection must run during QR decoding without flooding unchanged frames');
  console.log('Inspection continues during slow QR decoding:',inspectionRequests,'frame requests in 1.5 seconds');
  await page.evaluate(()=>endWork(true));
  await page.locator('#closeCamera').click();
  await page.waitForFunction(()=>!document.querySelector('#video').srcObject);
  await page.unrouteAll({behavior:'wait'});
  await page.goto('http://127.0.0.1:8766/login');
  assert.equal(await page.locator('a[href="/supervisor/login"]').count(),0);
  await page.locator('#username').fill('uiadmin');await page.locator('#password').fill('TestOnly-Password-739');await page.locator('#submit').click();
  await page.waitForURL('**/admin');
  await page.locator('#authLogout').click();await page.waitForURL('**/login');
  await page.screenshot({path:path.join(previews,'supervisor-login-preview.png'),fullPage:true});
  await page.locator('#username').fill('uihead');await page.locator('#password').fill('HeadOnly-Password-915');await page.locator('#submit').click();
  await page.waitForURL('**/supervisor');await page.getByRole('heading',{name:'UI-RETRY-001',exact:true}).first().waitFor();
  assert(await page.evaluate(()=>document.querySelector('#archive').compareDocumentPosition(document.querySelector('#approvals'))&Node.DOCUMENT_POSITION_FOLLOWING));
  const scanButton=await page.locator('#scanVideoQr').boundingBox();
  assert(scanButton.y+scanButton.height<844,'QR search must be visible immediately on mobile');
  await page.screenshot({path:path.join(previews,'supervisor-search-mobile-preview.png'),fullPage:false});
  assert.equal(await page.locator('.session-bar a[href="/admin"]').count(),0);
  assert.equal(await page.locator('.session-bar a[href="/access"]').count(),0);
  assert.equal(await page.locator('button').filter({hasText:'ปฏิเสธ'}).count(),0);
  await page.locator('#videoSearch').fill('NO-SUCH-VIDEO');await page.locator('#videoSearch').press('Enter');
  await page.waitForFunction(()=>document.querySelector('#workCount').textContent.includes('/ 0'));
  await page.locator('#videoSearch').fill('UI-RETRY-001');await page.locator('#videoSearch').press('Enter');
  await page.waitForFunction(()=>document.querySelector('#workCount').textContent.includes('/ 1'));
  await page.locator('#scanVideoQr').click();
  await page.waitForFunction(()=>document.querySelector('#searchQrVideo').videoWidth>0);
  await page.locator('#stopVideoQr').click();
  assert(await page.locator('#searchScanner').isHidden());
  assert(await page.evaluate(()=>!document.querySelector('#searchQrVideo').srcObject));
  await page.locator('#videoSearch').fill('NO-SUCH-VIDEO');await page.locator('#videoSearch').press('Enter');
  await page.waitForFunction(()=>document.querySelector('#workCount').textContent.includes('/ 0'));
  // Exercise the browser's native detector branch with a predictable QR result.
  await page.evaluate(()=>{window.BarcodeDetector=class{async detect(){return[{rawValue:'UI-RETRY-001'}]}};});
  await page.locator('#scanVideoQr').click();
  await page.waitForFunction(()=>document.querySelector('#videoSearch').value==='UI-RETRY-001'&&document.querySelector('#workCount').textContent.includes('/ 1'));
  assert(await page.locator('#searchScanner').isHidden());
  // Exercise server decoding with real QR pixels where BarcodeDetector is absent.
  const qr=fs.readFileSync(fixture.qr).toString('base64');
  await page.evaluate(async data=>{
    delete window.BarcodeDetector;
    const image=new Image();image.src='data:image/png;base64,'+data;await image.decode();
    const draw=CanvasRenderingContext2D.prototype.drawImage;
    CanvasRenderingContext2D.prototype.drawImage=function(source,...args){
      if(source?.id==='searchQrVideo'){
        this.fillStyle='#fff';this.fillRect(0,0,this.canvas.width,this.canvas.height);
        const side=Math.min(this.canvas.width,this.canvas.height);
        return draw.call(this,image,(this.canvas.width-side)/2,(this.canvas.height-side)/2,side,side);
      }
      return draw.call(this,source,...args);
    };
  },qr);
  await page.locator('#videoSearch').fill('NO-SUCH-VIDEO');await page.locator('#videoSearch').press('Enter');
  await page.waitForFunction(()=>document.querySelector('#workCount').textContent.includes('/ 0'));
  await page.locator('#scanVideoQr').click();
  await page.waitForFunction(()=>document.querySelector('#videoSearch').value==='UI-RETRY-001'&&document.querySelector('#workCount').textContent.includes('/ 1'));
  assert(await page.locator('#searchScanner').isHidden());
  await page.setViewportSize({width:1440,height:1000});await page.screenshot({path:path.join(previews,'supervisor-preview.png'),fullPage:true});
  await page.locator('#workVideos [data-video]').first().click();
  await page.waitForFunction(()=>document.querySelector('#playback').readyState>=2);
  await page.waitForFunction(()=>Number.isFinite(document.querySelector('#playback').duration)&&document.querySelector('#playback').currentTime>0);
  await page.locator('#playback').evaluate(video=>{video.currentTime=video.duration*.75;});
  await page.waitForFunction(()=>{const video=document.querySelector('#playback');return video.readyState>=2&&video.currentTime>=video.duration*.65;});
  await page.locator('#closePlayback').click();
  await page.locator('#tab-approvals').click();
  const review=page.locator('#reviewRows .supervisor-item').filter({hasText:'UI-RETRY-001'});
  await review.locator('textarea').fill('ตรวจสอบชิ้นงานแล้ว อนุญาตให้สแกนซ้ำเพื่อเริ่มตรวจใหม่');
  await review.getByRole('button',{name:'อนุญาตให้สแกนงานซ้ำ',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#supervisorMessage').textContent.startsWith('อนุญาตแล้ว'));
  await page.locator('#reviewStatus').selectOption('closed');await page.getByText('อนุญาตสแกนซ้ำแล้ว',{exact:false}).waitFor();
  await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2));
  assert.deepEqual(errors,[]);
  console.log('PASS: large portrait video, expand/escape, separate supervisor login/nav, real archive playback, approval with history, mobile layout');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
