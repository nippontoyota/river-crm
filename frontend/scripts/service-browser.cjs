/* Run against the isolated database described in backend/servicing/README.md. */
const assert = require('node:assert/strict');
const puppeteer = require(process.env.PUPPETEER_MODULE || 'puppeteer-core');
const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:3040';
const apiBase = process.env.TEST_API_URL || 'http://127.0.0.1:8040';

(async () => {
  const browser = await puppeteer.launch({ executablePath: process.env.BROWSER_EXECUTABLE || '/usr/bin/chromium-browser', headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  const errors = [];
  async function session(role) {
    const context = await browser.createBrowserContext();
    const page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message));
    await page.setViewport({ width: 1440, height: 1000 });
    await page.goto(base, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.login-submit');
    await page.type('[name=email]', `${role}@service-browser.test`);
    await page.type('[name=password]', 'ServiceBrowser123!');
    await page.click('.login-submit');
    await page.waitForFunction(() => location.pathname !== '/');
    return page;
  }
  async function click(page, text, within = '') {
    const element = await page.evaluateHandle((text, within) => [...document.querySelectorAll(`${within} button`)].find(el => el.textContent.trim() === text), text, within);
    assert.ok(element.asElement(), `Missing button: ${text}`);
    await element.asElement().click();
  }
  async function waitText(page, selector, text) {
    await page.waitForFunction((selector, text) => document.querySelector(selector)?.textContent.includes(text), {}, selector, text);
  }
  try {
    const admin = await session('admin');
    await admin.waitForSelector('.top-actions');
    await click(admin, '＋ Add lead', '.top-actions');
    await admin.waitForSelector('#add-lead-title');
    assert.equal(await admin.$('.service-vehicle-panel'), null, 'Add lead has no vehicle controls');
    await admin.click('.modal-close');
    await admin.goto(`${base}/all-leads`, { waitUntil: 'domcontentloaded' });
    await admin.waitForSelector('.lead-row');
    await Promise.all([
      admin.waitForResponse(response => /\/api\/leads\/\d+\/$/.test(response.url())),
      admin.evaluate(() => [...document.querySelectorAll('.lead-row')].find(row => row.textContent.includes('New Enquiry')).querySelector('.row-action').click()),
    ]);
    await admin.waitForSelector('.admin-customer-card');
    assert.equal(await admin.$('.service-vehicle-panel'), null, 'New enquiry details have no vehicle controls');
    await admin.screenshot({ path: '/tmp/crm-service-new-lead.png', fullPage: true });
    await admin.goto(`${base}/services?addService=1`, { waitUntil: 'domcontentloaded' });
    await admin.waitForSelector('.service-desk');
    assert.equal(await admin.$('.service-intake'), null, 'Admin cannot open service intake');
    assert.equal(await admin.evaluate(() => [...document.querySelectorAll('button')].some(button => button.textContent.includes('Add service'))), false);

    const so = await session('so');
    await so.goto(`${base}/all-my-leads`, { waitUntil: 'domcontentloaded' });
    await so.waitForSelector('.so-card-list > div b');
    await so.click('.so-card-list > div');
    await so.waitForSelector('.service-vehicle-panel');
    await click(so, '＋ Add scooter');
    await so.type('[name=chassis_number]', 'RIVERBROWSER123');
    await so.type('[name=registration_number]', 'KL07TEST123');
    await click(so, 'Register scooter');
    await waitText(so, '.service-vehicle-panel', 'RIVERBROWSER123');

    const ce = await session('ce');
    await ce.waitForSelector('.sales-row-action');
    await ce.click('.sales-row-action');
    await ce.waitForSelector('.sales-info-card');
    assert.equal(await ce.$('.service-vehicle-panel'), null, 'CRE new enquiry has no vehicle controls');
    await ce.click('.sales-detail-header .modal-close');
    for (const route of ['/my-leads', '/follow-ups', '/complaints', '/my-analytics']) {
      await ce.goto(`${base}${route}`, { waitUntil: 'domcontentloaded' });
      await ce.waitForSelector('.top-actions .button.primary');
      await click(ce, '＋ Add service', '.top-actions');
      await ce.waitForSelector('.service-intake');
      assert.equal(new URL(ce.url()).pathname, '/services');
    }
    await ce.setViewport({ width: 390, height: 844 });
    assert.ok(await ce.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'CRE service form fits mobile');
    await ce.setViewport({ width: 1440, height: 1000 });
    await ce.type('.service-intake .service-lookup input', 'riverbrowser123');
    await click(ce, 'Look up scooter');
    await waitText(ce, '.service-intake .service-identity', 'Anjali Service Rider');
    await ce.type('textarea[name=issue]', 'Rear brake noise when slowing down.');
    await ce.select('select[name=branch]', 'Kochi');
    await ce.type('input[name=odometer]', '2450');
    await click(ce, 'Save request');
    await ce.waitForSelector('.service-detail');
    await click(ce, 'Forward to Kochi');
    await waitText(ce, '.service-detail header', 'Incoming');
    await ce.screenshot({ path: '/tmp/crm-service-ce.png', fullPage: true });

    const staff = await session('service');
    assert.equal(new URL(staff.url()).pathname, '/services');
    await staff.waitForSelector('.service-ticket');
    await click(staff, '＋ Add service', '.top-actions');
    await staff.waitForSelector('.service-intake');
    await click(staff, 'Close intake');
    await staff.click('.service-ticket');
    await staff.waitForSelector('.service-detail');
    await click(staff, 'Start work');
    await waitText(staff, '.service-detail header', 'In progress');
    await staff.type('textarea[aria-label="Progress note or reason"]', 'Adjusted rear brake and completed road test.');
    await click(staff, 'Resolve request');
    await waitText(staff, '.service-resolution', 'Adjusted rear brake');
    await staff.screenshot({ path: '/tmp/crm-service-resolved.png', fullPage: true });
    const forbidden = await staff.evaluate(async url => (await fetch(`${url}/api/leads/`, { credentials: 'include' })).status, apiBase);
    assert.equal(forbidden, 403);
    await staff.setViewport({ width: 390, height: 844 });
    await staff.screenshot({ path: '/tmp/crm-service-mobile.png', fullPage: true });
    assert.ok(await staff.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'No mobile overflow');

    await click(ce, 'Refresh', '.service-detail');
    await waitText(ce, '.service-resolution', 'Adjusted rear brake');
    const other = await session('other');
    await other.waitForSelector('.service-queue');
    assert.equal(await other.$('.service-ticket'), null);
    await other.type('.service-lookup input', 'RIVERBROWSER123');
    await click(other, 'View history');
    await waitText(other, '.service-history', 'Adjusted rear brake');
    assert.equal(await other.$('.service-actions'), null, 'Cross-branch history is read-only');

    await click(other, '＋ Add service', '.service-page-heading');
    await other.type('.service-intake .service-lookup input', 'RIVERBROWSER123');
    await click(other, 'Look up scooter');
    await other.waitForSelector('textarea[name=issue]');
    assert.equal(await other.$eval('select[name=branch]', el => el.disabled && el.value === 'Thrissur'), true, 'Service branch stays fixed');
    await other.type('textarea[name=issue]', 'Annual service at Thrissur');
    await click(other, 'Add to branch queue');
    await waitText(other, '.service-detail header', 'Incoming');

    await click(ce, 'Close request');
    await click(ce, '＋ Add service', '.service-page-heading');
    await ce.type('.service-intake .service-lookup input', 'RIVERBROWSER123');
    await click(ce, 'Look up scooter');
    await waitText(ce, '.service-intake .service-history', 'Adjusted rear brake');
    assert.deepEqual(errors, []);
    console.log('PASS: no vehicle controls on new enquiries; Add service across CRE sections and Service Department only; booked sale chassis → CE request → branch resolution → repeat service visit; mobile layout and API permissions.');
  } catch (error) {
    for (const page of await browser.pages()) {
      console.error(page.url(), (await page.$eval("body", el => el.innerText)).slice(-1800));
      await page.screenshot({ path: `/tmp/crm-service-failure-${(await browser.pages()).indexOf(page)}.png`, fullPage: true });
    }
    throw error;
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
