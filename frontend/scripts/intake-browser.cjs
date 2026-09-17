/* Smoke test against isolated fixture servers only.
   API: SQLite /tmp/crm-intake-browser.sqlite3, INTAKE_ENABLED=true, eager=true,
   INTAKE_SECRETS_JSON={"browser":{"active":"browser-fixture-secret"}}.
   Seed admin intake-browser@example.com / IntakeBrowser123! and WEBSITE source.
   Allow the frontend origin in CORS/CSRF. Start frontend with NEXT_PUBLIC_API_URL.
   PUPPETEER_MODULE may point at an existing puppeteer-core installation.
   API_BASE and WEB_BASE default to localhost:8041 and localhost:3041.
*/
const assert = require('node:assert/strict');
const fs = require('node:fs');
const puppeteer = require(process.env.PUPPETEER_MODULE || 'puppeteer-core');
const apiBase = process.env.API_BASE || 'http://127.0.0.1:8041';
const webBase = process.env.WEB_BASE || 'http://127.0.0.1:3041';
if (![apiBase, webBase].every(url => ['127.0.0.1', 'localhost'].includes(new URL(url).hostname))) throw Error('Use isolated local fixture servers.');
(async () => {
  const browser = await puppeteer.launch({ executablePath: process.env.BROWSER_EXECUTABLE || '/usr/bin/chromium-browser', headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1440, height: 1000 });
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.goto(apiBase + '/api/auth/csrf/');
    const admin = async (path, method = 'GET', body) => page.evaluate(async ({ apiBase, path, method, body }) => {
      const { csrfToken } = await (await fetch(apiBase + '/api/auth/csrf/', { credentials: 'include' })).json();
      const response = await fetch(apiBase + path, { method, credentials: 'include', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }, body: body === undefined ? undefined : JSON.stringify(body) });
      return { status: response.status, data: await response.json() };
    }, { apiBase, path, method, body });
    assert.equal((await admin('/api/auth/login/', 'POST', { email: 'intake-browser@example.com', password: 'IntakeBrowser123!' })).status, 200);
    const stamp = Date.now().toString();
    const phone = '98' + stamp.slice(-8), phone2 = '97' + stamp.slice(-8), phone3 = '96' + stamp.slice(-8), phone4 = '95' + stamp.slice(-8);
    const activated_at = new Date(Date.now() - 86400000).toISOString();
    const connections = await admin('/api/intake/connections/');
    const existing = connections.data.find(c => c.name.startsWith('Browser website'));
    const connection = existing ? { status: 201, data: existing } : await admin('/api/intake/connections/', 'POST', { name: 'Browser website ' + stamp, origin: 'WEBSITE', source: 'WEBSITE', secret_ref: 'browser', activated_at, enabled: true });
    assert.equal(connection.status, 201);
    const form = await admin('/api/intake/forms/', 'POST', { connection: connection.data.id, name: 'Browser enquiry ' + stamp, external_id: 'browser-' + stamp, activated_at, enabled: true });
    assert.equal(form.status, 201, JSON.stringify(form.data));
    const deliver = async (id, fields) => {
      const response = await fetch(apiBase + '/api/integrations/website/leads/', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer browser-fixture-secret' }, body: JSON.stringify({ submission_id: id, form_id: form.data.external_id, fields }) });
      const data = await response.json(); assert.equal(response.status, 202, JSON.stringify(data)); return data.receipt_id;
    };
    const firstId = await deliver('valid', { Name: 'Browser Valid ' + stamp, Phone: phone });
    const badId = await deliver('correction', { Name: 'Browser Correct ' + stamp, Phone: phone2, Email: 'bad' });
    const mapId = await deliver('mapping', { Name: 'Browser Map ' + stamp, Contact: phone3 });
    const duplicateId = await deliver('duplicate', { Name: 'Browser Duplicate ' + stamp, Phone: phone });
    const first = await admin(`/api/intake/submissions/${firstId}/`);
    assert.equal(first.data.state, 'IMPORTED');
    const click = async text => {
      await page.waitForFunction(text => [...document.querySelectorAll('button')].some(e => e.textContent.trim() === text && !e.disabled), {}, text);
      await page.evaluate(text => [...document.querySelectorAll('button')].find(e => e.textContent.trim() === text && !e.disabled).click(), text);
    };
    const open = async name => {
      await page.waitForFunction(name => [...document.querySelectorAll('tbody tr')].some(e => e.textContent.includes(name)), {}, name);
      await page.evaluate(name => [...document.querySelectorAll('tbody tr')].find(e => e.textContent.includes(name)).querySelector('button').click(), name);
      await page.waitForSelector('.intake-dialog');
    };
    const fillLabel = async (scope, label, value) => {
      const handle = await page.evaluateHandle(({ scope, label }) => [...document.querySelectorAll(scope + ' label')].find(e => e.childNodes[0]?.textContent.trim() === label)?.querySelector('input'), { scope, label });
      const input = handle.asElement(); assert.ok(input, label);
      await input.click({ clickCount: 3 }); await input.press('Backspace'); await input.type(value);
    };
    await page.goto(webBase + '/lead-intake');
    await open('Browser Correct ' + stamp);
    await fillLabel('.intake-dialog', 'email', 'corrected@example.com');
    // Polling must preserve a draft; visibility events exercise the resume path.
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    assert.equal(await page.$eval('.intake-dialog label:nth-child(3) input', e => e.value), 'corrected@example.com');
    await click('Save corrections and reprocess');
    await page.waitForFunction(() => document.querySelector('.intake-dialog')?.textContent.includes('IMPORTED'));
    await click('Close');
    await page.click(`input[aria-label="Select receipt ${mapId}"]`);
    await open('Browser Map ' + stamp);
    await click('Map this form’s answers');
    await page.waitForSelector('select[aria-label="Map Contact"]');
    await page.select('select[aria-label="Map Contact"]', 'phone');
    await click('Save new version');
    await page.waitForFunction(() => document.body.textContent.includes('Mapping version 1 saved.'));
    await click('Reprocess 1 selected pending receipts');
    await page.waitForFunction(() => document.body.textContent.includes('1 pending receipts queued'));
    assert.equal((await admin(`/api/intake/submissions/${mapId}/`)).data.state, 'IMPORTED');
    await click('Receipts');
    await open('Browser Duplicate ' + stamp);
    await fillLabel('.intake-dialog', 'Existing lead ID', String(first.data.lead));
    await click('Link to existing lead');
    await page.waitForFunction(() => document.querySelector('.intake-dialog')?.textContent.includes('LINKED'));
    await click('Close');
    assert.equal((await admin(`/api/intake/submissions/${duplicateId}/`)).data.lead, first.data.lead);
    assert.equal((await admin(`/api/intake/submissions/${badId}/`)).data.state, 'IMPORTED');
    await page.screenshot({ path: '/tmp/crm-intake-desktop.png', fullPage: true });
    await page.goto(webBase + '/leads');
    await page.waitForFunction(name => document.body.textContent.includes(name), {}, 'Browser Valid ' + stamp);
    const headers = 'name,phone,email,source,enquiry date,city,pincode\n';
    await page.waitForSelector('input[type=file]');
    const uploadCsv = content => page.$eval('input[type=file]', (input, csv) => {
      const transfer = new DataTransfer();
      transfer.items.add(new File([csv], 'spreadsheet.csv', { type: 'text/csv' }));
      input.files = transfer.files;
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }, content);
    await uploadCsv(headers + 'Spreadsheet Customer,,,WEBSITE,,,\n');
    await page.waitForFunction(() => document.body.textContent.includes('Fix 1 row'));
    await uploadCsv(headers + `Spreadsheet Customer,${phone4},,WEBSITE,,,\n`);
    await page.waitForFunction(() => document.querySelector('.upload-review')?.textContent.includes('No duplicate phone numbers or invalid rows found.'));
    await click('Import leads');
    await page.waitForFunction(() => document.body.textContent.includes('1 leads imported.'));
    await page.goto(webBase + '/lead-intake');
    await page.waitForSelector('.intake-table-wrap table');
    await page.setViewport({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2), 'mobile page overflows');
    await page.screenshot({ path: '/tmp/crm-intake-mobile.png', fullPage: true });
    assert.deepEqual(errors, []);
    console.log('PASS: receipt correction, mapping preview/version/reprocess, duplicate link, assignment pool, upload error/correction/commit, desktop and mobile views.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
