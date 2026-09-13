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
    await ce.goto(`${base}/services`, { waitUntil: 'domcontentloaded' });
    await ce.waitForSelector('.service-desk');
    await click(ce, '＋ New service request');
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

    await click(ce, 'Close request');
    await click(ce, '＋ New service request');
    await ce.type('.service-intake .service-lookup input', 'RIVERBROWSER123');
    await click(ce, 'Look up scooter');
    await waitText(ce, '.service-intake .service-history', 'Adjusted rear brake');
    assert.deepEqual(errors, []);
    console.log('PASS: sale chassis registration → CE lookup and forwarding → branch resolution → CE tracking → cross-branch history → repeat visit; mobile layout and Service API restrictions.');
  } catch (error) {
    for (const page of await browser.pages()) {
      console.error(page.url(), (await page.$eval("body", el => el.innerText)).slice(-1800));
      await page.screenshot({ path: `/tmp/crm-service-failure-${(await browser.pages()).indexOf(page)}.png`, fullPage: true });
    }
    throw error;
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
