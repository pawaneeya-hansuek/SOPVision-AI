const {chromium} = require('../.test-node/node_modules/playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
(async () => {
  const browser = await chromium.launch({executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true});
  try {
    const context = await browser.newContext({viewport: {width: 1440, height: 1000}, reducedMotion: 'reduce'});
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.route('**/api/auth/status', route => route.fulfill({json: {configured: true}}));
    await page.goto('http://127.0.0.1:8000/login');
    await page.waitForFunction(() => document.querySelector('.login-brand img').naturalWidth === 1024);
    assert.equal(await page.locator('#codeLabel').isVisible(), false);
    assert.equal(await page.locator('#setupLink').isVisible(), false);
    await page.locator('#password').fill('Only-a-UI-test');
    await page.locator('#togglePassword').click();
    assert.equal(await page.locator('#password').getAttribute('type'), 'text');
    assert.equal(await page.locator('#togglePassword').getAttribute('aria-pressed'), 'true');
    await page.locator('#togglePassword').click();
    assert.equal(await page.locator('#password').getAttribute('type'), 'password');
    await page.locator('#password').fill('');
    await page.screenshot({path: path.resolve('backups/login-redesign-desktop.png'), fullPage: true});
    for (const width of [768, 390, 320]) {
      await page.setViewportSize({width, height: 844});
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'overflow at ' + width);
      assert(await page.locator('#submit').isVisible());
      if (width === 390) await page.screenshot({path: path.resolve('backups/login-redesign-mobile.png'), fullPage: true});
    }
    await page.route('**/api/auth/login', async route => {
      assert.deepEqual(route.request().postDataJSON(), {username: 'uitest', password: 'Only-a-UI-test'});
      await route.fulfill({status: 401, json: {detail: 'ชื่อบัญชีหรือรหัสผ่านไม่ถูกต้อง'}});
    });
    await page.locator('#username').fill('uitest');
    await page.locator('#password').fill('Only-a-UI-test');
    await page.locator('#submit').click();
    await page.waitForFunction(() => document.querySelector('#message').textContent.includes('ไม่ถูกต้อง'));
    assert.equal(await page.locator('#submit').isDisabled(), false);
    await page.unroute('**/api/auth/status');
    await page.route('**/api/auth/status', route => route.fulfill({json: {configured: false}}));
    await page.goto('http://127.0.0.1:8000/setup?token=ui-test-token-never-a-real-secret');
    await page.waitForFunction(() => !document.querySelector('#codeLabel').hidden);
    assert(!page.url().includes('token='));
    for (const id of ['codeLabel', 'displayLabel', 'confirmLabel']) assert(await page.locator('#'+id).isVisible());
    assert.equal(await page.locator('#password').getAttribute('minlength'), '10');
    assert.equal(await page.locator('#password').getAttribute('autocomplete'), 'new-password');
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    assert.deepEqual(errors, []);
    console.log('PASS: original logo loaded, desktop/tablet/mobile layouts, password toggle, login error recovery, first-admin setup, no JS errors. No production account created or changed.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
