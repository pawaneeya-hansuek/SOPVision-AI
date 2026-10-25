const {chromium}=require('../.test-node/node_modules/playwright');
const assert=require('node:assert/strict'),path=require('node:path');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  async function login(username,password){
   await page.goto('http://127.0.0.1:8766/login');
   await page.locator('#username').fill(username);await page.locator('#password').fill(password);await page.locator('#submit').click();
  }
  await login('uiadmin','TestOnly-Password-739');await page.waitForURL('**/admin');
  await page.waitForFunction(()=>document.querySelector('#stats').children.length>0);
  assert(await page.locator('#adminOverview').isVisible());
  assert(await page.locator('#adminLive').isHidden());assert(await page.locator('#adminRecords').isHidden());
  for(const [tab,panel] of [['live','adminLive'],['trace','adminTrace'],['videos','adminVideos'],['records','adminRecords'],['overview','adminOverview']]){
   await page.locator('#tab-'+tab).click();assert(await page.locator('#'+panel).isVisible());
   assert.equal(await page.locator('[data-portal-group="admin"]:visible').count(),1);
   assert.equal(await page.locator('#tab-'+tab).getAttribute('aria-selected'),'true');
  }
  await page.locator('#tab-records').click();await page.locator('[data-detail="ui-attempt-001"]').click();
  await page.waitForFunction(()=>!document.querySelector('#detail').hidden&&document.querySelector('#detailContent video'));
  assert.equal(await page.locator('#detail').getAttribute('role'),'dialog');
  const box=await page.locator('#detail').boundingBox();assert(box.y>=0&&box.y+box.height<=1000);
  await page.keyboard.press('Escape');assert(await page.locator('#detail').isHidden());
  await page.locator('#tab-overview').click();
  await page.screenshot({path:path.resolve('tmp/admin-sections-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2));
  await page.screenshot({path:path.resolve('tmp/admin-sections-mobile.png'),fullPage:true});
  await page.locator('#authLogout').click();await page.waitForURL('**/login');
  await login('uihead','HeadOnly-Password-915');await page.waitForURL('**/supervisor');
  await page.locator('#workVideos [data-video]').first().waitFor();
  assert(await page.locator('#archive').isVisible());assert(await page.locator('#approvals').isHidden());
  assert(await page.locator('#cameraArchivePanel').isHidden());
  await page.locator('#tab-camera-videos').click();assert(await page.locator('#cameraArchivePanel').isVisible());assert(await page.locator('#workArchivePanel').isHidden());
  await page.locator('#tab-work-videos').click();
  await page.locator('#workVideos [data-video]').first().click();
  await page.waitForFunction(()=>document.querySelector('#playback').readyState>=2);
  assert.equal(await page.locator('#playbackPanel').getAttribute('role'),'dialog');
  const video=await page.locator('#playbackPanel').boundingBox();assert(video.y>=0&&video.y+video.height<=844);
  await page.keyboard.press('Escape');assert(await page.locator('#playbackPanel').isHidden());
  assert(await page.locator('#playback').evaluate(v=>v.paused));
  await page.screenshot({path:path.resolve('tmp/supervisor-sections-mobile.png'),fullPage:true});
  await page.locator('#tab-approvals').click();assert(await page.locator('#approvals').isVisible());assert(await page.locator('#archive').isHidden());
  await page.reload();assert(await page.locator('#approvals').isVisible());
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2));
  await page.screenshot({path:path.resolve('tmp/supervisor-approvals-mobile.png'),fullPage:true});
  await page.setViewportSize({width:1440,height:1000});await page.locator('#tab-archive').click();
  await page.screenshot({path:path.resolve('tmp/supervisor-sections-desktop.png'),fullPage:true});
  assert.deepEqual(errors,[]);
  console.log('PASS: admin/supervisor sections, single visible panel, nested video tabs, in-view dialogs, Escape/pause, restored section on reload, mobile overflow');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
