/* Run only against an isolated local database with an admin account.
   Start the frontend with NEXT_PUBLIC_API_URL matching API_BASE (default :8042).
   Set ADMIN_EMAIL / ADMIN_PASSWORD and PUPPETEER_MODULE if needed.
   This test creates accounts and replaces the fixture's list configuration. */
const assert = require('node:assert/strict');
const puppeteer = require(process.env.PUPPETEER_MODULE || 'puppeteer-core');
const apiBase = process.env.API_BASE || 'http://127.0.0.1:8042';
const webBase = process.env.WEB_BASE || 'http://127.0.0.1:3042';
if (![apiBase, webBase].every(url => ['127.0.0.1', 'localhost'].includes(new URL(url).hostname))) throw Error('Use isolated local fixture servers.');

(async () => {
  const browser = await puppeteer.launch({ executablePath: process.env.BROWSER_EXECUTABLE || '/usr/bin/chromium-browser', headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.setViewport({ width: 1600, height: 1000 });
    await page.goto(apiBase + '/api/auth/csrf/');
    const api = (path, method = 'GET', body) => page.evaluate(async ({ apiBase, path, method, body }) => {
      const { csrfToken } = await (await fetch(apiBase + '/api/auth/csrf/', { credentials: 'include' })).json();
      const response = await fetch(apiBase + path, { method, credentials: 'include', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }, body: body === undefined ? undefined : JSON.stringify(body) });
      return { status: response.status, data: await response.json() };
    }, { apiBase, path, method, body });
    assert.equal((await api('/api/auth/login/', 'POST', { email: process.env.ADMIN_EMAIL || 'admin-edit-browser@example.com', password: process.env.ADMIN_PASSWORD || 'AdminEditBrowser123!' })).status, 200);
    const lists = { branches: ['Kochii', 'Aluva'], sources: ['WALKIN', 'Metaa'], activities: ['Roadshw', 'Exhibition'], subActivities: { Roadshw: ['Kochii'], Exhibition: ['Other'] }, models: ['Indei'], colorVariants: ['Monson Blue'] };
    assert.equal((await api('/api/system-config/', 'PUT', { lists })).status, 200);
    const stamp = Date.now();
    const members = [];
    for (const role of ['ADMIN', 'CEO', 'CRE', 'SO', 'SALES_MANAGER', 'RECEPTIONIST', 'COMPLAINTS', 'FEEDBACK', 'SERVICE', 'META_UPLOADER']) {
      const response = await api('/api/auth/users/', 'POST', { email: `${role.toLowerCase()}-${stamp}@example.com`, password: 'Unchanged123!', first_name: role, role, location: 'Aluva' });
      assert.equal(response.status, 201, JSON.stringify(response.data));
      members.push(response.data);
    }
    const click = async (selector, text) => {
      const handle = await page.evaluateHandle((selector, text) => [...document.querySelectorAll(selector)].find(node => node.textContent.trim() === text && !node.disabled), selector, text);
      assert.ok(handle.asElement(), `Missing enabled button: ${selector} ${text}`);
      await handle.asElement().click();
    };
    const fill = async (selector, value) => { await page.click(selector, { clickCount: 3 }); await page.keyboard.press('Backspace'); await page.type(selector, value); };
    const listRowAction = async (item, action) => {
      await page.waitForFunction((item, action) => {
        const row = [...document.querySelectorAll('.list-items li')].find(row => row.querySelector('span')?.textContent === item);
        return row && [...row.querySelectorAll('button')].some(button => button.textContent === action && !button.disabled);
      }, {}, item, action);
      await page.evaluate((item, action) => {
        const row = [...document.querySelectorAll('.list-items li')].find(row => row.querySelector('span')?.textContent === item);
        [...row.querySelectorAll('button')].find(button => button.textContent === action).click();
      }, item, action);
    };
    const waitList = item => page.waitForFunction(item => [...document.querySelectorAll('.list-items li > span')].some(node => node.textContent === item), {}, item);
    await page.goto(webBase + '/lists');
    await waitList('Kochii');
    await page.select('[aria-label="Parent activity"]', 'Roadshw');
    await listRowAction('Roadshw', 'Edit');
    await fill('.list-edit-form input', ' Roadshow ');
    await click('.list-edit-form button', 'Save');
    await waitList('Roadshow');
    assert.equal(await page.$eval('[aria-label="Parent activity"]', node => node.value), 'Roadshow');
    assert.deepEqual((await api('/api/system-config/')).data.lists.subActivities, { Roadshow: ['Kochii'], Exhibition: ['Other'] });

    for (const [oldName, newName] of [['Kochii', 'Kochi'], ['Metaa', 'Meta'], ['Indei', 'Indie'], ['Monson Blue', 'Monsoon Blue'], ['Kochii', 'Kochi']]) {
      await listRowAction(oldName, 'Edit');
      await fill('.list-edit-form input', newName);
      await click('.list-edit-form button', 'Save');
      await page.waitForFunction(() => !document.querySelector('.list-edit-form'));
    }
    const savedLists = (await api('/api/system-config/')).data.lists;
    assert.deepEqual(savedLists, { branches: ['Kochi', 'Aluva'], sources: ['WALKIN', 'Meta'], activities: ['Roadshow', 'Exhibition'], subActivities: { Roadshow: ['Kochi'], Exhibition: ['Other'] }, models: ['Indie'], colorVariants: ['Monsoon Blue'] });
    await listRowAction('Kochi', 'Edit');
    await fill('.list-edit-form input', '  ');
    await click('.list-edit-form button', 'Save');
    await page.waitForSelector('.list-edit-form [role=alert]');
    await fill('.list-edit-form input', 'Aluva');
    await click('.list-edit-form button', 'Save');
    await page.waitForFunction(() => document.querySelector('.list-edit-form')?.textContent.includes('already exists'));
    await click('.list-edit-form button', 'Cancel');
    await listRowAction('Meta', 'Edit');
    await fill('.list-edit-form input', 'Walk-in');
    await click('.list-edit-form button', 'Save');
    await page.waitForSelector('.list-edit-form [role=alert]');
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => !document.querySelector('.list-edit-form'));
    assert.deepEqual((await api('/api/system-config/')).data.lists, savedLists);
    assert.equal(await page.evaluate(() => [...document.querySelectorAll('.list-items li')].find(row => row.textContent.includes('Walk-in')).querySelectorAll('button').length), 1);

    await listRowAction('Indie', 'Edit');
    await fill('.list-edit-form input', 'River Indie');
    await page.setOfflineMode(true);
    await click('.list-edit-form button', 'Save');
    await page.waitForSelector('.empty-state[role=alert]');
    assert.equal(await page.$eval('.list-edit-form input', node => node.value), 'River Indie');
    await page.setOfflineMode(false);
    await click('.list-edit-form button', 'Save');
    await waitList('River Indie');
    assert.deepEqual((await api('/api/system-config/')).data.lists, { ...savedLists, models: ['River Indie'] });
    await fill('input[placeholder="Add branch"]', 'Temporary branch');
    await page.$eval('input[placeholder="Add branch"]', input => input.form.requestSubmit());
    await waitList('Temporary branch');
    await listRowAction('Temporary branch', 'Remove');
    await page.waitForFunction(() => !document.querySelector('.list-items')?.textContent.includes('Temporary branch'));
    await page.reload();
    await waitList('River Indie');
    await page.screenshot({ path: '/tmp/crm-admin-edit-lists-desktop.png', fullPage: true });
    await page.setViewport({ width: 390, height: 844 });
    await listRowAction('Kochi', 'Edit');
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2), 'Lists overflow on mobile');
    await page.screenshot({ path: '/tmp/crm-admin-edit-lists-mobile.png', fullPage: true });
    await page.keyboard.press('Escape');

    await page.setViewport({ width: 1600, height: 1000 });
    await page.goto(webBase + '/team');
    await page.waitForSelector('.team-user-row');
    const openUser = async email => {
      await page.waitForFunction(email => [...document.querySelectorAll('.team-user-row')].some(row => row.textContent.includes(email)), {}, email);
      await page.evaluate(email => [...document.querySelectorAll('.team-user-row')].find(row => row.textContent.includes(email)).querySelector('.team-row-actions button').click(), email);
      await page.waitForSelector('.team-edit-dialog[open]');
    };
    for (const member of members) {
      await openUser(member.email);
      assert.equal(await page.$eval('.team-edit-dialog [name=email]', node => node.value), member.email);
      assert.equal(await page.$eval('.team-edit-dialog [name=password]', node => node.value), '');
      await fill('.team-edit-dialog [name=first_name]', `${member.role} Corrected`);
      await fill('.team-edit-dialog [name=last_name]', 'Name');
      await fill('.team-edit-dialog [name=phone]', '9876543210');
      await click('.team-edit-dialog button', 'Save changes');
      await page.waitForFunction(() => !document.querySelector('.team-edit-dialog'));
      const saved = (await api(`/api/auth/users/${member.id}/`)).data;
      assert.equal(saved.first_name, `${member.role} Corrected`);
      assert.equal(saved.phone, '9876543210');
      assert.equal(saved.role, member.role);
      assert.equal(saved.is_active, true);
    }
    const member = members.find(member => member.role === 'SO');
    await openUser(member.email);
    await fill('.team-edit-dialog [name=email]', members[0].email);
    await click('.team-edit-dialog button', 'Save changes');
    await page.waitForSelector('.team-edit-dialog [role=alert]');
    await fill('.team-edit-dialog [name=email]', `corrected-${stamp}@example.com`);
    await page.select('.team-edit-dialog [name=location]', 'Kochi');
    await click('.team-edit-dialog button', 'Save changes');
    await page.waitForFunction(() => !document.querySelector('.team-edit-dialog'));
    await page.reload();
    await openUser(`corrected-${stamp}@example.com`);
    assert.equal(await page.$eval('.team-edit-dialog [name=location]', node => node.value), 'Kochi');
    await fill('.team-edit-dialog [name=first_name]', 'Unsaved');
    await click('.team-edit-dialog button', 'Cancel');
    assert.equal((await api(`/api/auth/users/${member.id}/`)).data.first_name, 'SO Corrected');
    await page.screenshot({ path: '/tmp/crm-admin-edit-users-desktop.png', fullPage: true });
    await page.setViewport({ width: 390, height: 844 });
    await openUser(`corrected-${stamp}@example.com`);
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2), 'Users overflow on mobile');
    await page.screenshot({ path: '/tmp/crm-admin-edit-users-mobile.png', fullPage: true });
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => !document.querySelector('.team-edit-dialog'));
    const uploader = members.find(member => member.role === 'META_UPLOADER');
    await openUser(uploader.email);
    await fill('.team-edit-dialog [name=password]', 'short');
    await fill('.team-edit-dialog [name=confirmPassword]', 'short');
    assert.equal(await page.$eval('.team-edit-dialog [name=password]', node => node.checkValidity()), false);
    await fill('.team-edit-dialog [name=password]', 'Replacement123!');
    await fill('.team-edit-dialog [name=confirmPassword]', 'Different123!');
    await click('.team-edit-dialog button', 'Save changes');
    await page.waitForFunction(() => document.querySelector('.team-edit-dialog [role=alert]')?.textContent.includes('Passwords do not match'));
    await fill('.team-edit-dialog [name=confirmPassword]', 'Replacement123!');
    await click('.team-edit-dialog button', 'Save changes');
    await page.waitForFunction(() => !document.querySelector('.team-edit-dialog'));
    await openUser(uploader.email);
    assert.equal(await page.$eval('.team-edit-dialog [name=password]', node => node.value), '', 'Password must not be returned or retained');
    await fill('.team-edit-dialog [name=password]', 'Cancelled123!');
    await fill('.team-edit-dialog [name=confirmPassword]', 'Cancelled123!');
    await click('.team-edit-dialog button', 'Cancel');
    const disabled = members.find(member => member.role === 'CRE');
    const impact = (await api(`/api/auth/users/${disabled.id}/offboarding-impact/`)).data;
    assert.equal((await api(`/api/auth/users/${disabled.id}/disable/`, 'POST', { impact_version: impact.version, routes: [] })).status, 200);
    await page.reload();
    await page.waitForSelector('.team-filters');
    await page.evaluate(() => {
      const select = [...document.querySelectorAll('.team-filters select')].find(select => [...select.options].some(option => option.value === 'DISABLED'));
      select.value = 'DISABLED'; select.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await openUser(disabled.email);
    await fill('.team-edit-dialog [name=last_name]', 'Updated while disabled');
    await click('.team-edit-dialog button', 'Save changes');
    await page.waitForFunction(() => !document.querySelector('.team-edit-dialog'));
    assert.equal((await api(`/api/auth/users/${disabled.id}/`)).data.is_active, false);
    assert.ok(await page.evaluate(() => document.querySelector('.team-users-scroll').textContent.includes('Enable')));
    assert.equal((await api('/api/auth/login/', 'POST', { email: `corrected-${stamp}@example.com`, password: 'Unchanged123!' })).status, 200, 'Original password must still work');
    for (const [password, expected] of [['Unchanged123!', 400], ['Cancelled123!', 400], ['Replacement123!', 200]]) {
      assert.equal((await api('/api/auth/login/', 'POST', { email: uploader.email, password })).status, expected, 'Password reset/cancel login check');
    }
    assert.deepEqual(errors, []);
    console.log('PASS: all six editable lists, all ten user roles, linked sub-activities, validation, cancel/Escape, failed-save retry, persistence, optional password reset and login, add/remove and desktop/mobile layout.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
