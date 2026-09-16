/* Run against isolated local fixture servers. Seed bulk-browser@example.com /
   BulkBrowser123!, WEBSITE + River Indie in Lists, and an existing lead with
   phone 9876543299. API_BASE / WEB_BASE default to localhost:8048 / 3048. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const puppeteer = require(process.env.PUPPETEER_MODULE || 'puppeteer-core');
const apiBase = process.env.API_BASE || 'http://127.0.0.1:8048';
const webBase = process.env.WEB_BASE || 'http://127.0.0.1:3048';
if (![apiBase, webBase].every(url => ['localhost', '127.0.0.1'].includes(new URL(url).hostname))) throw Error('Use isolated local fixture servers.');

(async () => {
  const browser = await puppeteer.launch({ executablePath: process.env.BROWSER_EXECUTABLE || '/usr/bin/chromium-browser', headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1440, height: 1000 });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(apiBase + '/api/auth/csrf/');
    const admin = (path, method = 'GET', body) => page.evaluate(async ({ apiBase, path, method, body }) => {
      const { csrfToken } = await (await fetch(apiBase + '/api/auth/csrf/', { credentials: 'include' })).json();
      const response = await fetch(apiBase + path, { method, credentials: 'include', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }, body: body === undefined ? undefined : JSON.stringify(body) });
      return { status: response.status, data: await response.json() };
    }, { apiBase, path, method, body });
    assert.equal((await admin('/api/auth/login/', 'POST', { email: 'bulk-browser@example.com', password: 'BulkBrowser123!' })).status, 200);
    const click = async text => {
      await page.waitForFunction(text => [...document.querySelectorAll('button')].some(e => e.textContent.trim() === text && !e.disabled), {}, text);
      await page.evaluate(text => [...document.querySelectorAll('button')].find(e => e.textContent.trim() === text && !e.disabled).click(), text);
    };
    await page.goto(webBase + '/leads', { waitUntil: 'networkidle0' });
    await page.waitForSelector('input[type=file]');
    await page.evaluate(() => {
      const create = URL.createObjectURL.bind(URL);
      URL.createObjectURL = blob => { window.sampleCsv = blob.text(); return create(blob); };
    });
    await click('Download sample format');
    const sample = await page.evaluate(() => window.sampleCsv);
    assert.match(sample.split('\n')[0], /"RTO"/);
    assert.match(sample, /"kl07"/);
    assert.match(sample, /"Thrissur"/);
    assert.match(sample, /"River Indie"/);
    const rows = sample.split('\n');
    rows.push(rows[1].replace('Aarav Sharma', 'Repeated file customer'));
    rows.push(rows[1].replace('Aarav Sharma', 'Existing CRM duplicate').replace('9876543210', '9876543299'));
    rows.push(rows[1].replace('Aarav Sharma', 'Correct RTO Customer').replace('9876543210', '9876543298').replace('kl07', 'KL05 Kollam'));
    const path = '/tmp/crm-bulk-rto-browser.csv';
    fs.writeFileSync(path, rows.join('\n'));
    // Snap Chromium has its own /tmp; construct the selected file in the browser.
    await page.$eval('input[type=file]', (input, csv) => {
      const transfer = new DataTransfer();
      transfer.items.add(new File([csv], 'bulk-rto.csv', { type: 'text/csv' }));
      input.files = transfer.files;
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }, rows.join('\n'));
    await click('Check import');
    await page.waitForSelector('.upload-review tbody tr');
    await page.waitForFunction(() => document.querySelector('.upload-review')?.textContent.includes('1 rows need correction'));
    const review = await page.$eval('.upload-review', e => e.textContent);
    assert.match(review, /KL-07 - Ernakulam/);
    assert.match(review, /KL-08 - Thrissur/);
    assert.match(review, /Same file/);
    assert.match(review, /CRM/);
    await click('Edit row 6');
    const rtoSelect = await page.evaluateHandle(() => [...document.querySelectorAll('.upload-review label')].find(e => e.firstChild?.textContent === 'RTO').querySelector('select'));
    await rtoSelect.asElement().select('KL-05');
    await click('Save row correction');
    await page.waitForFunction(() => !document.querySelector('.upload-review')?.textContent.includes('rows need correction'));
    await page.$eval('.upload-review details', e => { e.open = true; });
    assert.match(await page.$eval('.upload-review', e => e.textContent), /KL-05 - Kottayam/);
    await page.screenshot({ path: '/tmp/crm-bulk-rto-desktop.png', fullPage: true });
    await page.setViewport({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2), 'mobile page overflows');
    await page.screenshot({ path: '/tmp/crm-bulk-rto-mobile.png', fullPage: true });
    await page.setViewport({ width: 1440, height: 1000 });
    await click('Import leads');
    await page.waitForFunction(() => document.body.textContent.includes('3 leads imported.'));
    for (const [phone, rto] of [['9876543210', 'KL-07'], ['9876543211', 'KL-08'], ['9876543298', 'KL-05'], ['9876543299', 'KL-08']]) {
      const response = await admin('/api/leads/?q=' + phone);
      assert.equal(response.data.results.length, 1);
      assert.equal(response.data.results[0].rto, rto);
    }
    await page.goto(webBase + '/all-leads');
    await page.waitForFunction(() => [...document.querySelectorAll('.lead-row')].some(row => row.textContent.includes('Correct RTO Customer')));
    await page.evaluate(() => [...document.querySelectorAll('.lead-row')].find(row => row.textContent.includes('Correct RTO Customer')).querySelector('.row-action').click());
    await page.waitForFunction(() => document.querySelector('.sales-detail-modal')?.textContent.includes('KL-05 - Kottayam'));
    assert.deepEqual(errors, []);
    console.log('PASS: downloaded RTO sample, normalized names/codes, duplicate review, RTO correction, import, admin detail, desktop and mobile.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
