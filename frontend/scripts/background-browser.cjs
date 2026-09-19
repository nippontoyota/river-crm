/* Isolated browser regression. See background-fixture.py; set DATABASE_URL to a
   localhost test_crm_background_browser database. Start its serve mode on 8064
   and frontend on 3064 with NEXT_PUBLIC_API_URL=http://localhost:8064.
   PUPPETEER_MODULE may point to an existing puppeteer-core installation. */
const assert = require('node:assert/strict');
const { createHmac } = require('node:crypto');
const { execFileSync } = require('node:child_process');
const path = require('node:path');
const puppeteer = require(process.env.PUPPETEER_MODULE || 'puppeteer-core');
const apiBase = 'http://localhost:8064';
const webBase = 'http://localhost:3064';
const fixture = mode => execFileSync(path.resolve(__dirname, '../../backend/.venv/bin/python'), [path.join(__dirname, 'background-fixture.py'), mode], { encoding: 'utf8', env: process.env });

(async () => {
  fixture('seed');
  const browser = await puppeteer.launch({ executablePath: '/usr/bin/chromium-browser', headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.setViewport({ width: 1440, height: 1000 });
    await page.goto(apiBase + '/api/auth/csrf/');
    const admin = (path, method = 'GET', body) => page.evaluate(async ({ apiBase, path, method, body }) => {
      const { csrfToken } = await (await fetch(apiBase + '/api/auth/csrf/', { credentials: 'include' })).json();
      const response = await fetch(apiBase + path, { method, credentials: 'include', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }, body: body === undefined ? undefined : JSON.stringify(body) });
      return { status: response.status, data: await response.json() };
    }, { apiBase, path, method, body });
    assert.equal((await admin('/api/auth/login/', 'POST', { email: 'background-browser@example.com', password: 'BackgroundBrowser123!' })).status, 200);
    const click = async text => {
      await page.waitForFunction(text => [...document.querySelectorAll('button')].some(e => e.textContent.trim() === text && !e.disabled), {}, text);
      await page.evaluate(text => [...document.querySelectorAll('button')].find(e => e.textContent.trim() === text).click(), text);
    };
    const connections = async () => {
      await page.goto(webBase + '/lead-intake');
      await click('Connections');
      await page.waitForSelector('.intake-form-line');
    };
    await connections();
    assert.match(await page.$eval('.intake-panel', e => e.textContent), /Automatic Meta checks about every 30 minutes/);
    assert.doesNotMatch(await page.$eval('.intake-panel', e => e.textContent), /Worker:|Scheduler:/);
    assert.match(await page.$eval('.intake-panel', e => e.textContent), /Webhook receipts and uploads processed about every 5 minutes/);
    assert.match(await page.$eval('.intake-panel', e => e.textContent), /configured \(access not verified here\)/);
    assert.match(await page.$eval('body', e => e.textContent), /No successful processor run recorded yet/);
    // No recovery request: automatic scanning must discover the form itself.
    assert.ok(await page.evaluate(() => [...document.querySelectorAll('button')].some(e => e.textContent === 'Request recovery')));
    const raw = JSON.stringify({ object: 'page', entry: [{ id: '456', changes: [{ field: 'leadgen', value: { form_id: '123', leadgen_id: '222' } }] }] });
    const response = await fetch(apiBase + '/api/integrations/meta/webhook/', { method: 'POST', body: raw, headers: { 'Content-Type': 'application/json', 'X-Hub-Signature-256': 'sha256=' + createHmac('sha256', 'isolated-meta-test-secret').update(raw).digest('hex') } });
    assert.equal(response.status, 200);
    const before = (await admin('/api/intake/submissions/')).data;
    assert.equal(before.results[0].state, 'RECEIVED');
    await page.goto(webBase + '/all-leads');
    await page.waitForSelector('input[type=file]');
    await click('Fresh');
    let navigations = 0;
    page.on('framenavigated', frame => { if (frame === page.mainFrame()) navigations++; });
    console.log(fixture('process').trim());
    // Exercise the real 30-second visible-list timer, without refresh or navigation.
    await page.waitForFunction(() => document.body.textContent.includes('Automatic Customer 333'), { timeout: 45000 });
    assert.equal(navigations, 0);
    await connections();
    assert.match(await page.$eval('.intake-panel', e => e.textContent), /Last successful run:/);
    assert.match(await page.$eval('.intake-form-line', e => e.textContent), /Scan: completed/);
    const leads = (await admin('/api/leads/?status=FRESH')).data;
    assert.equal(leads.count, 2);
    await page.screenshot({ path: '/tmp/crm-background-desktop.png', fullPage: true });
    await page.setViewport({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2), 'mobile overflow');
    await page.screenshot({ path: '/tmp/crm-background-mobile.png', fullPage: true });
    fixture('error');
    await connections();
    assert.match(await page.$eval('.intake-panel', e => e.textContent), /Last processor attempt:/);
    assert.match(await page.$eval('.intake-form-line', e => e.textContent), /Scan: error/);
    assert.match(await page.$eval('body', e => e.textContent), /No successful processor run in the last 15 minutes/);
    assert.match(await page.$eval('.intake-form-line', e => e.textContent), /Meta scan delayed/);
    await click('Request recovery');
    await page.waitForFunction(() => document.body.textContent.includes('Recovery queued for River Indie fixture'));
    const health = (await admin('/api/intake/connections/health/')).data;
    const form = health.connections[0].forms[0];
    const repeated = await admin(`/api/intake/forms/${form.id}/fetch/`, 'POST');
    assert.equal(repeated.status, 202);
    assert.equal(repeated.data.fetch_requested_at, form.fetch_requested_at);
    console.log(fixture('process').trim());
    assert.equal((await admin('/api/leads/?status=FRESH')).data.count, 2);
    await page.goto(webBase + '/leads');
    await page.waitForSelector('input[type=file]');
    await page.$eval('input[type=file]', input => {
      const transfer = new DataTransfer();
      transfer.items.add(new File(['name,phone,email,source,enquiry date,city,pincode\nAutomatic Upload,9876543999,,META,,,\n'], 'cron.csv', { type: 'text/csv' }));
      input.files = transfer.files;
      input.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await page.waitForFunction(() => document.body.textContent.includes('Your file is queued. Checking normally starts within five minutes'));
    console.log(fixture('process').trim());
    await page.waitForFunction(() => document.body.textContent.includes('No duplicate phone numbers or invalid rows found.'), { timeout: 30000 });
    await click('Import leads');
    await page.waitForFunction(() => document.body.textContent.includes('1 leads imported.'));
    assert.equal((await admin('/api/leads/?status=FRESH')).data.count, 3);
    assert.deepEqual(errors, []);
    console.log('PASS: automatic scans without recovery clicks, webhook replay deduplication, real 30-second Fresh refresh, timing/credential messages, delayed warnings, recovery, upload review/import, desktop/mobile.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
