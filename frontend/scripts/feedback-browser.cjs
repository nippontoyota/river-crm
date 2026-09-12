/* Run against an isolated database seeded as described in backend/feedback/README.md. */
const assert = require('node:assert/strict');
const puppeteer = require(process.env.PUPPETEER_MODULE || 'puppeteer-core');
const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:3039';
const apiBase = process.env.TEST_API_URL || 'http://127.0.0.1:8039';

(async () => {
  const browser = await puppeteer.launch({ executablePath: process.env.BROWSER_EXECUTABLE || '/usr/bin/chromium-browser', headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.setViewport({ width: 1440, height: 1000 });
  async function login(role) {
    await page.goto(base, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.login-submit');
    await page.type('[name=email]', `${role}@feedback-browser.test`);
    await page.type('[name=password]', 'FeedbackBrowser123!');
    await page.click('.login-submit');
    await page.waitForFunction(() => location.pathname !== '/');
  }
  async function clickText(text, selector = 'button') {
    const handle = await page.evaluateHandle((text, selector) => [...document.querySelectorAll(selector)].find(e => e.textContent.trim() === text), text, selector);
    assert.ok(handle.asElement(), `Missing ${selector}: ${text}`);
    await handle.asElement().click();
  }
  try {
    await login('caller');
    await page.waitForSelector('.feedback-type-card');
    assert.equal(new URL(page.url()).pathname, '/feedback');
    assert.equal(await page.$$eval('.feedback-type-card', els => els.length), 3);
    await page.click('.feedback-bell summary');
    await page.waitForSelector('.feedback-notifications a.unread');
    await page.select('.feedback-notifications select', 'TDF');
    await page.waitForFunction(() => [...document.querySelectorAll('.feedback-notifications a.unread b')].every(e => e.textContent.includes('TDF')));
    await page.click('.feedback-bell summary');
    await page.screenshot({ path: '/tmp/crm-feedback-desktop.png', fullPage: true });
    const dueCall = await page.evaluateHandle(() => [...document.querySelectorAll('.feedback-queue tbody tr')].find(row => row.textContent.includes('Anjali Menon'))?.querySelector('button'));
    assert.ok(dueCall.asElement(), 'Assigned TDF customer is visible');
    await dueCall.asElement().click();
    await page.waitForSelector('dialog[open]');
    if (await page.$('dialog .feedback-call-form')) {
      await page.type('dialog textarea', 'Comfortable test drive. Customer appreciated the SO explanation.');
      await clickText('Save call outcome');
    }
    await page.waitForFunction(() => document.querySelector('.feedback-history')?.textContent.includes('Comfortable test drive'));
    assert.equal(await page.$('dialog .feedback-call-form'), null);
    await page.screenshot({ path: '/tmp/crm-feedback-completed.png', fullPage: true });
    await clickText('Close');
    await page.waitForSelector('dialog[open]', { hidden: true });
    const forbidden = await page.evaluate(async apiBase => (await fetch(`${apiBase}/api/leads/`, { credentials: 'include' })).status, apiBase);
    assert.equal(forbidden, 403);
    await page.setViewport({ width: 390, height: 844 });
    assert.equal(await page.$eval('.feedback-shell .sidebar', e => getComputedStyle(e).display), 'none');
    await page.screenshot({ path: '/tmp/crm-feedback-mobile.png', fullPage: true });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'No mobile page overflow');
    await page.setViewport({ width: 1440, height: 1000 });
    await page.click('.user-card button');
    await page.waitForSelector('.login-submit');
    await login('ceo');
    await page.goto(`${base}/ceo/feedback?range=all`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.feedback-comparisons tbody tr');
    assert.match(await page.$eval('.feedback-comparisons', e => e.textContent), /Asha/);
    await page.screenshot({ path: '/tmp/crm-feedback-ceo.png', fullPage: true });
    await clickText('Open call');
    await page.waitForSelector('dialog[open]');
    assert.equal(await page.$('dialog .feedback-call-form'), null);
    assert.equal(await page.$('dialog .feedback-reassign'), null);
    await clickText('Close');
    const exported = await page.evaluate(async apiBase => { const response = await fetch(`${apiBase}/api/ceo/export/feedback/?range=all`, { credentials: 'include' }); return { status: response.status, body: await response.text() }; }, apiBase);
    assert.equal(exported.status, 200);
    assert.match(exported.body, /original_due_at/);
    await page.click('.user-card button');
    await page.waitForSelector('.login-submit');
    await login('admin');
    await page.goto(`${base}/team`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.team-create-form');
    const browserEmail = `browser-caller-${Date.now()}@feedback-browser.test`;
    await page.type('[name=firstName]', 'Browser Caller');
    await page.type('[name=email]', browserEmail);
    await page.type('[name=password]', 'FeedbackBrowser123!');
    await page.select('[name=role]', 'Feedback Caller');
    await page.waitForFunction(() => [...document.querySelectorAll('[name=branch] option')].some(e => e.value === 'Kochi'));
    assert.equal(await page.$eval('[name=branch]', e => e.required), true);
    await page.select('[name=branch]', 'Kochi');
    await page.click('.team-submit');
    await page.waitForFunction(email => [...document.querySelectorAll('.team-user-row')].some(e => e.textContent.includes(email) && e.textContent.includes('Feedback Caller')), {}, browserEmail);
    await page.click('.user-card button');
    await page.waitForSelector('.login-submit');
    await login('manager');
    await page.goto(`${base}/feedback`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.feedback-queue tbody tr');
    assert.doesNotMatch(await page.$eval('.feedback-queue', e => e.textContent), /Rohan Das/);
    assert.deepEqual(errors, []);
    console.log('PASS: feedback login, tiles, notification filter, call completion/history, permissions, mobile layout, CEO reporting/export, admin account creation, and manager branch scope.');
  } catch (error) {
    await page.screenshot({ path: '/tmp/crm-feedback-browser-failure.png', fullPage: true }).catch(() => {});
    throw error;
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
