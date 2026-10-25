const {chromium}=require('../.test-node/node_modules/playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs'),previews=path.resolve('output/previews');fs.mkdirSync(previews,{recursive:true});
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 try{
  const ctx=await browser.newContext({viewport:{width:1440,height:1100},acceptDownloads:true});
  await ctx.route('https://fonts.googleapis.com/**',r=>r.abort());
  const page=await ctx.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8000/admin',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>document.getElementById('rowCount').textContent.includes('รายการที่ตรง'));
  assert(await page.locator('#exportCsv').isVisible());
  const [response]=await Promise.all([
   page.waitForResponse(r=>r.url().includes('/api/flow/admin?')&&r.url().includes('state=passed')),
   page.locator('#stateFilter').selectOption('passed')
  ]);
  const filtered=await response.json();
  await page.waitForFunction(n=>document.getElementById('rowCount').textContent.startsWith(n+' '),filtered.total);
  const [download]=await Promise.all([page.waitForEvent('download'),page.locator('#exportCsv').click()]);
  assert.equal(await download.failure(),null);
  assert(download.suggestedFilename().endsWith('.csv'));
  const [print]=await Promise.all([ctx.waitForEvent('page'),page.locator('#exportPrint').click()]);
  await print.waitForLoadState('domcontentloaded');
  assert(await print.getByRole('button',{name:'พิมพ์ / บันทึก PDF'}).isVisible());
  assert((await print.locator('body').innerText()).includes('รอบงาน '+filtered.total));
  await print.close();
  await page.locator('#stateFilter').selectOption('all');
  await page.waitForResponse(r=>r.url().includes('/api/flow/admin?')&&r.url().includes('state=all'));
  await page.screenshot({path:path.join(previews,'admin-reporting-preview.png'),fullPage:true});
  await page.goto('http://127.0.0.1:8000/',{waitUntil:'domcontentloaded'});
  await page.waitForResponse(r=>r.url().endsWith('/api/stats'));
  const stats=(await (await page.request.get('http://127.0.0.1:8000/api/stats')).json()).production;
  assert.equal(await page.locator('#statTotal').innerText(),String(stats.total_jobs));
  assert.equal(await page.locator('#statPass').innerText(),String(stats.passed));
  await page.locator('[data-view="reports"]').click();
  await page.waitForResponse(r=>r.url().endsWith('/api/records'));
  await page.locator('#reportMode').selectOption('flow');
  assert((await page.locator('#reportRows').innerText()).includes('งาน QR'));
  await page.locator('#reportRows [data-open-report]').first().press('Enter');
  await page.locator('#drawerBackdrop').waitFor({state:'visible'});
  assert((await page.locator('#drawerContent').innerText()).includes('งานผลิต QR'));
  await page.goto('http://127.0.0.1:8000/worker?station=1',{waitUntil:'domcontentloaded'});
  await page.locator('#operator').fill('EMP-001');
  await page.locator('#operator').dispatchEvent('change');
  await page.waitForResponse(r=>r.url().includes('/api/flow/admin?')&&r.url().includes('operator=EMP-001'));
  await page.waitForFunction(()=>document.getElementById('counts').textContent.includes('พนักงาน EMP-001'));
  await page.reload({waitUntil:'domcontentloaded'});
  // The operator used for actual work is persisted by the existing start flow.
  await page.locator('#operator').fill('EMP-001');await page.locator('#operator').dispatchEvent('change');
  await page.waitForFunction(()=>document.getElementById('counts').textContent.includes('พนักงาน EMP-001'));
  await page.screenshot({path:path.join(previews,'worker-reporting-preview.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.goto('http://127.0.0.1:8000/admin',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>document.getElementById('rowCount').textContent.includes('รายการที่ตรง'));
  assert(await page.locator('#exportCsv').isVisible());
  assert(await page.locator('#exportPrint').isVisible());
  assert.deepEqual(errors,[]);
  console.log('PASS: CSV download, filtered printable report, overview parity, unified QR detail, database worker history, mobile admin controls; no page JS errors');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
