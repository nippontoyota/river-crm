/* Run against a local frontend with WEB_BASE=http://localhost:3075.
   PUPPETEER_MODULE can point to an existing puppeteer-core installation.
   All API requests are intercepted; no CRM accounts or records are changed. */
const assert = require('node:assert/strict');
const puppeteer = require(process.env.PUPPETEER_MODULE || 'puppeteer-core');
const webBase = process.env.WEB_BASE || 'http://localhost:3075';
const query = 'branch=kochi&branch=thrissur&range=custom&date_from=2026-09-01&date_to=2026-09-30&source=META';
const officers = [{ id: 2, name: 'Rahul P M', branch: 'Kochi', role: 'SO' }, { id: 3, name: 'Rahul P M', branch: 'Thrissur', role: 'SO' }];
const records = Array.from({ length: 30 }, (_, i) => ({ id: i + 1, name: `RNR Customer ${i + 1}`, analysis_status: 'RNR', status: 'PENDING', so_id: 2 }));
for (const [analysis_status, status, loss_reason, so_id] of [['Lost Lead', 'LOST', 'Dropped', 2], ['Lost Lead', 'LOST', 'Reason not recorded', null], ['Fresh', 'FRESH', '', 3], ['Line Busy', 'PENDING', '', 2], ['Need time', 'PENDING', '', 2], ['Booking Done', 'WALKIN', '', 2]]) {
  records.push({ id: records.length + 1, name: `${analysis_status} Customer`, analysis_status, status, loss_reason, so_id });
}
records.forEach(row => Object.assign(row, { phone: '9876543210', branch: 'Kochi', enquiry_date: '2026-09-15', so: officers.find(o => o.id === row.so_id)?.name, calls: 30, last_call: '2026-09-30T10:00:00Z' }));
const counts = (items, field) => [...new Set(items.map(row => row[field]))].map(key => ({ key, label: key, count: items.filter(row => row[field] === key).length })).sort((a, b) => b.count - a.count || a.key.localeCompare(b.key));
const statuses = counts(records, 'analysis_status');
const lost = records.filter(row => row.status === 'LOST');
const lead_analysis = { total: records.length, lost_total: lost.length, statuses, loss_reasons: counts(lost, 'loss_reason'), officers: [...officers, { id: null, name: 'Unassigned Sales Officer', branch: '' }].map(officer => {
  const owned = records.filter(row => row.so_id === officer.id);
  return { key: officer.id === null ? '__unassigned__' : String(officer.id), name: officer.name, branch: officer.branch, total: owned.length, statuses: Object.fromEntries(counts(owned, 'analysis_status').map(row => [row.key, row.count])) };
}) };
const history = Array.from({ length: 30 }, (_, i) => ({ id: i + 1, kind: 'call', occurred_at: '2026-08-01T10:00:00Z', actor: 'Rahul P M', actor_role: 'SO', before: {}, after: { outcome: 'RNR', remarks: `Earlier call ${i + 1}` }, provenance: 'live' }));
const paginate = (items, params) => { const page = Number(params.get('page') || 1); return { count: items.length, results: items.slice((page - 1) * 25, page * 25), next: page * 25 < items.length ? '?page=2' : null, previous: page > 1 ? '?page=1' : null }; };

(async () => {
  const browser = await puppeteer.launch({ executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium-browser', headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  try {
    const page = await browser.newPage();
    const errors = [], requests = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.setViewport({ width: 1440, height: 1000 });
    await page.setRequestInterception(true);
    page.on('request', request => {
      const url = new URL(request.url());
      if (!url.pathname.startsWith('/api/')) {
        return url.origin === new URL(webBase).origin || url.protocol === 'data:' ? request.continue() : request.abort();
      }
      requests.push(url);
      const params = url.searchParams;
      let data;
      if (url.pathname === '/api/auth/me/') data = { user: { id: 1, first_name: 'CEO', last_name: 'Preview', email: 'ceo@example.com', role: 'CEO' } };
      else if (url.pathname === '/api/ceo/options/') data = { branches: [{ value: 'kochi', label: 'Kochi' }, { value: 'thrissur', label: 'Thrissur' }], employees: officers, roles: [], rtos: [], statuses: [], source: ['META'], campaign: [], model_interest: [], activities: [], sub_activities: {} };
      else if (url.pathname === '/api/ceo/overview/') data = { lead_analysis, etbr: { E: records.length, T: 0, B: 1, R: 0 }, targets: { available: false }, conversions: { E_T: 0, E_B: 3, E_R: 0, T_B: null, B_R: 0 }, current: {}, activity: {}, complaints: {}, coverage: {}, branches: [], ageing: {} };
      else if (/\/leads\/\d+\/history\/$/.test(url.pathname)) data = paginate(history, params);
      else if (/\/leads\/\d+\/$/.test(url.pathname)) data = { ...records.find(row => row.id === Number(url.pathname.split('/')[4])), milestones: [], assigned_ps: 2 };
      else if (url.pathname === '/api/ceo/leads/') {
        const matches = records.filter(row => (!params.has('analysis_status') || row.analysis_status === params.get('analysis_status')) && (!params.has('loss_reason') || row.loss_reason === params.get('loss_reason')) && (!params.has('analysis_officer') || (row.so_id === null ? '__unassigned__' : String(row.so_id)) === params.get('analysis_officer')) && (!params.has('q') || row.name.includes(params.get('q'))));
        data = paginate(matches, params);
      } else { errors.push(`Unexpected API: ${url.pathname}`); data = {}; }
      return request.respond({ status: 200, contentType: 'application/json', headers: { 'Access-Control-Allow-Origin': new URL(webBase).origin, 'Access-Control-Allow-Credentials': 'true' }, body: JSON.stringify(data) });
    });
    const ready = () => page.waitForFunction(() => !document.querySelector('.ceo-loading') && document.querySelector('.ceo-page'));
    const overview = async () => { await page.goto(`${webBase}/ceo?${query}`); await page.waitForSelector('.ceo-analysis-officers tbody tr'); await ready(); };
    const click = async selector => { await page.waitForSelector(selector); await page.click(selector); };
    const checkDrill = async (selector, expected) => {
      await overview();
      await Promise.all([page.waitForResponse(response => new URL(response.url()).pathname === '/api/ceo/leads/'), click(selector)]);
      await page.waitForFunction(() => location.pathname === '/ceo/leads');
      await ready();
      const params = new URL(page.url()).searchParams;
      for (const [key, value] of Object.entries(expected)) assert.equal(params.get(key), value);
      assert.deepEqual(params.getAll('branch'), ['kochi', 'thrissur']);
      assert.equal(params.get('date_from'), '2026-09-01');
      assert.equal(params.get('source'), 'META');
      assert.equal(params.get('metric'), null);
      assert.equal(params.get('scope'), null);
    };
    await checkDrill('.ceo-analysis button[aria-label="View RNR leads"]', { analysis_status: 'RNR' });
    await Promise.all([page.waitForResponse(response => new URL(response.url()).pathname === '/api/ceo/leads/' && new URL(response.url()).searchParams.get('page') === '2'), click('.ceo-pagination button:last-child')]);
    await page.waitForFunction(() => location.search.includes('page=2') && !document.querySelector('.ceo-loading') && document.querySelectorAll('.ceo-table-card tbody tr').length === 5);
    assert.equal(await page.$$eval('.ceo-table-card tbody tr', rows => rows.length), 5);
    await click('.ceo-table-card tbody tr:first-child td:first-child button');
    await page.waitForSelector('.ceo-detail-grid');
    assert.match(await page.$eval('dialog', node => node.textContent), /Customer & ownership/);
    await click('dialog>header button');
    await page.evaluate(() => [...document.querySelectorAll('button')].find(node => node.textContent === 'View history').click());
    await page.waitForSelector('.ceo-history-item');
    assert.equal(await page.$$eval('.ceo-history-item', rows => rows.length), 25);
    await page.evaluate(() => [...document.querySelectorAll('button')].find(node => node.textContent === 'Load more history').click());
    await page.waitForFunction(() => document.querySelectorAll('.ceo-history-item').length === 30);
    assert.ok(requests.filter(url => url.pathname.endsWith('/history/')).every(url => !url.searchParams.has('date_from')));
    await click('dialog>header button');
    await page.goBack();
    await page.goBack();
    await page.waitForSelector('.ceo-analysis');
    await checkDrill('.ceo-analysis button[aria-label="View 30 RNR leads"]', { analysis_status: 'RNR' });
    await checkDrill('.ceo-analysis-lost button[aria-label="View Dropped leads"]', { analysis_status: 'Lost Lead', loss_reason: 'Dropped' });
    await checkDrill('.ceo-analysis-lost button[aria-label="View 1 Dropped leads"]', { loss_reason: 'Dropped' });
    await checkDrill('.ceo-analysis-officers tbody tr:first-child th button', { analysis_officer: '2' });
    await checkDrill('.ceo-analysis-officers tbody tr:first-child td:nth-child(2) button', { analysis_officer: '2' });
    await checkDrill('.ceo-analysis-officers tbody tr:first-child td:nth-child(3) button', { analysis_officer: '2', analysis_status: 'RNR' });
    await checkDrill('.ceo-analysis-officers tbody tr:nth-child(2) td:nth-child(3) button', { analysis_officer: '3', analysis_status: 'RNR' });
    assert.match(await page.$eval('.ceo-table-card', node => node.textContent), /No records match/);
    await checkDrill('.ceo-analysis-officers thead th:nth-child(3) button', { analysis_status: 'RNR' });
    await checkDrill('.ceo-analysis-officers tfoot td:nth-child(3) button', { analysis_status: 'RNR' });
    await checkDrill('.ceo-analysis-officers tbody tr:last-child th button', { analysis_officer: '__unassigned__' });
    await checkDrill('.ceo-analysis-officers tfoot td:nth-child(2) button', {});
    await overview();
    await page.screenshot({ path: '/tmp/ceo-analysis-desktop.png', fullPage: true });
    await page.setViewport({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2), 'mobile page overflow');
    const sticky = await page.$eval('.ceo-analysis-officers .ceo-table-scroll', node => {
      node.scrollLeft = 250;
      const cells = node.querySelectorAll('tbody tr:first-child>*');
      return { scrolled: node.scrollLeft, left: cells[0].getBoundingClientRect().left - node.getBoundingClientRect().left, total: cells[1].getBoundingClientRect().left - cells[0].getBoundingClientRect().right };
    });
    assert.ok(sticky.scrolled > 0);
    assert.ok(Math.abs(sticky.left) < 2 && Math.abs(sticky.total) < 2, 'sticky officer and total columns');
    await page.screenshot({ path: '/tmp/ceo-analysis-mobile.png', fullPage: true });
    const refresh = requests.filter(url => url.searchParams.has('refresh')).length;
    await Promise.all([page.waitForResponse(response => response.url().includes('refresh=')), page.evaluate(() => [...document.querySelectorAll('button')].find(node => node.textContent.includes('Refresh')).click())]);
    await page.waitForFunction(() => !document.querySelector('.ceo-loading'));
    assert.ok(requests.filter(url => url.searchParams.has('refresh')).length > refresh);
    assert.deepEqual(errors, []);
    console.log('PASS: category/name/count/total/zero/header links, preserved filters, pagination, details, lifetime history, Back, refresh, and desktop/mobile sticky layout.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
