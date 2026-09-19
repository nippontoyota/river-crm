/* Run against isolated local fixture servers. Seed bulk-browser@example.com /
   BulkBrowser123!, WEBSITE + River Indie in Lists, and an existing lead with
   phone 9876543299. API_BASE / WEB_BASE default to localhost:8048 / 3048. */
const assert = require('node:assert/strict');
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
    const rowRequests = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => { if (request.url().includes('/api/uploads/')) rowRequests.push(request.url()); });
    await page.goto(apiBase + '/api/auth/csrf/');
    const admin = (path, method = 'GET', body) => page.evaluate(async ({ apiBase, path, method, body }) => {
      const { csrfToken } = await (await fetch(apiBase + '/api/auth/csrf/', { credentials: 'include' })).json();
      const response = await fetch(apiBase + path, { method, credentials: 'include', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }, body: body === undefined ? undefined : JSON.stringify(body) });
      return { status: response.status, data: response.status === 204 ? null : await response.json() };
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
    assert.equal(sample.split('\n')[0], '"name","phone","email","source","enquiry date","city","pincode"');
    const existingLead = (await admin('/api/leads/?q=9876543299')).data.results[0];
    const selectCsv = async (csv) => {
      await page.$eval('input[type=file]', (input, content) => {
        const transfer = new DataTransfer();
        transfer.items.add(new File([content], 'bulk-leads.csv', { type: 'text/csv' }));
        input.files = transfer.files;
        input.dispatchEvent(new Event('change', { bubbles: true }));
      }, csv);
    };
    const importDisabled = () => page.evaluate(() => [...document.querySelectorAll('button')].find(button => button.textContent.trim() === 'Import leads')?.disabled);
    await selectCsv(sample.replace('"name"', '"Customer Name"'));
    await page.waitForFunction(() => document.querySelector('.bulk-import-review')?.textContent.includes('Unrecognized headings: Customer Name'));
    assert.match(await page.$eval('.bulk-import-review', e => e.textContent), /Missing headings: name/);
    assert.equal(await page.$('select[aria-label="Upload mapping template"]'), null);
    assert.doesNotMatch(await page.$eval('.bulk-import-review', e => e.textContent), /Preview \/ edit mapping|Reparse|Excel template/);

    const rows = sample.split('\n');
    rows.push(rows[1].replace('Aarav Sharma', 'Repeated file customer'));
    rows.push(rows[1].replace('Aarav Sharma', 'Existing CRM duplicate').replace('9876543210', '9876543299'));
    rows.push(rows[1].replace('Aarav Sharma', 'Correct Email Customer').replace('9876543210', '9876543298').replace('aarav@example.com', 'invalid-email'));
    await selectCsv(rows.join('\n'));
    await page.waitForFunction(() => document.querySelector('.upload-review')?.textContent.includes('Fix 1 row'));
    assert.equal(await importDisabled(), true);
    assert.doesNotMatch(await page.$eval('.upload-review', e => e.textContent), /Edit row|Import separately/);
    rows[5] = rows[5].replace('invalid-email', 'aarav@example.com');
    await selectCsv(rows.join('\n'));
    await page.waitForFunction(() => document.querySelector('.bulk-import-review')?.textContent.includes('5 rows · 2 ready · 3 duplicates need review'));
    assert.equal(await importDisabled(), true);
    await page.waitForFunction(() => document.querySelector('.upload-review')?.getAttribute('aria-busy') === 'false');
    const review = await page.$eval('.upload-review', e => e.textContent);
    assert.match(review, /Repeated in this file/);
    assert.match(review, /Already in CRM/);
    await page.click('[aria-label="Reject row 2"]');
    await page.waitForFunction(() => document.querySelector('[aria-label="Reject row 2"]')?.disabled && !document.querySelector('[aria-label="Approve row 4"]')?.disabled);
    await page.click('[aria-label="Approve row 4"]');
    await page.waitForFunction(() => document.querySelector('[aria-label="Approve row 4"]')?.disabled && !document.querySelector('[aria-label="Approve row 5"]')?.disabled);
    await page.click('[aria-label="Approve row 5"]');
    await page.waitForFunction(() => [...document.querySelectorAll('button')].some(button => button.textContent.trim() === 'Import leads' && !button.disabled));
    await page.screenshot({ path: '/tmp/crm-bulk-simple-desktop.png', fullPage: true });
    await page.setViewport({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2), 'mobile page overflows');
    assert.ok(await page.$eval('.upload-review .intake-table-wrap', element => element.getBoundingClientRect().right <= innerWidth && element.scrollWidth > element.clientWidth), 'Mobile table must scroll inside the page');
    await page.screenshot({ path: '/tmp/crm-bulk-simple-mobile.png', fullPage: true });
    await page.setViewport({ width: 1440, height: 1000 });
    await click('Import leads');
    await page.waitForFunction(() => document.body.textContent.includes('3 leads imported. 1 existing leads updated. 1 rows skipped.'));
    for (const [phone, rto] of [['9876543210', ''], ['9876543211', ''], ['9876543298', ''], ['9876543299', existingLead.rto]]) {
      const response = await admin('/api/leads/?q=' + phone);
      assert.equal(response.data.results.length, 1, `One lead per phone: ${phone}`);
      assert.equal(response.data.results[0].rto, rto);
      if (phone === '9876543210') assert.equal(response.data.results[0].name, 'Repeated file customer');
      if (phone === '9876543299') {
        assert.equal(response.data.results[0].name, 'Existing CRM duplicate');
        assert.equal(response.data.results[0].status, 'QUALIFIED');
        assert.ok(response.data.results[0].assigned_so);
      }
    }
    const heading = sample.split('\n')[0];
    const repeated = Array.from({ length: 120 }, (_, i) => `Paged customer ${i},${i < 60 ? '7888888888' : '7888888889'},,META,,,`);
    const invalid = Array.from({ length: 51 }, (_, i) => `Invalid ${i},bad-phone,,META,,,`);
    await selectCsv([heading, ...repeated, ...invalid].join('\n'));
    await page.waitForFunction(() => document.querySelector('.upload-review')?.textContent.includes('Fix 51 rows'));
    await page.click('[aria-label="Next invalid rows page"]');
    await page.waitForFunction(() => document.querySelector('[aria-label="invalid rows pages"]')?.textContent.includes('Page 2'));
    await page.waitForFunction(() => document.querySelector('.upload-review')?.textContent.includes('Invalid 50'));
    await selectCsv([heading, ...repeated].join('\n'));
    await page.waitForFunction(() => document.querySelector('.bulk-import-review')?.textContent.includes('120 duplicates need review'));
    await page.waitForFunction(() => {
      const button = document.querySelector('[aria-label="Next duplicates page"]');
      return button && !button.disabled;
    });
    assert.match(await page.$eval('.upload-review', e => e.textContent), /showing 20 of 60 matching rows/);
    await page.click('[aria-label="Next duplicates page"]');
    await page.waitForFunction(() => document.querySelector('[aria-label="Approve row 52"]') && !document.querySelector('[aria-label="Approve row 52"]').disabled);
    await page.click('[aria-label="Approve row 52"]');
    await page.waitForFunction(() => document.querySelector('.bulk-import-review')?.textContent.includes('60 duplicates need review'));
    await click('Reject all pending duplicates');
    await page.waitForFunction(() => document.querySelector('.bulk-import-review')?.textContent.includes('0 duplicates need review'));
    await click('Import leads');
    await page.waitForFunction(() => document.body.textContent.includes('1 leads imported. 0 existing leads updated. 119 rows skipped.'));
    const uploaderEmail = `paged-uploader-${Date.now()}@example.com`;
    assert.equal((await admin('/api/auth/users/', 'POST', { first_name: 'Pagination uploader', email: uploaderEmail, password: 'BulkBrowser123!', role: 'META_UPLOADER' })).status, 201);
    await admin('/api/auth/logout/', 'POST', {});
    assert.equal((await admin('/api/auth/login/', 'POST', { email: uploaderEmail, password: 'BulkBrowser123!' })).status, 200);
    await page.goto(webBase + '/bulk-upload', { waitUntil: 'networkidle0' });
    await page.waitForSelector('input[type=file]');
    assert.match(await page.$eval('.uploader-dropzone', e => e.textContent), /1,000 leads/);
    await selectCsv([heading, ...Array.from({ length: 60 }, () => 'Uploader duplicate,7888888890,,META,,,')].join('\n'));
    await page.waitForFunction(() => document.querySelector('.bulk-import-review')?.textContent.includes('60 duplicates need review'));
    await click('Reject all pending duplicates');
    await click('Import leads');
    await page.waitForFunction(() => document.body.textContent.includes('0 leads imported. 0 existing leads updated. 60 rows skipped.'));
    assert.ok(rowRequests.some(url => url.includes('/rows/?filter=duplicates&page=2')));
    assert.ok(!rowRequests.some(url => url.includes('include_rows=true')), 'Review must not load a whole batch');
    assert.deepEqual(errors, []);
    console.log('PASS: Admin and Meta Uploader, format validation, offline correction, paginated errors/duplicates, group samples, batch-wide rejection preserves approvals, atomic imports, ownership/status, desktop and mobile.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
