/* Run against a local frontend with WEB_BASE=http://localhost:3075.
   PUPPETEER_MODULE can point to an existing puppeteer-core installation.
   All API requests are intercepted; no CRM accounts or records are changed. */
const assert = require('node:assert/strict');
const puppeteer = require(process.env.PUPPETEER_MODULE || 'puppeteer-core');
const webBase = process.env.WEB_BASE || 'http://localhost:3075';
const query = 'branch=kochi&branch=thrissur&range=custom&date_from=2026-09-01&date_to=2026-09-30&source=META';
const officers = [{ id: 2, name: 'Rahul P M', branch: 'Kochi', role: 'SO' }, { id: 3, name: 'Rahul P M', branch: 'Thrissur', role: 'SO' }];
for (let id = 4; id <= 14; id++) officers.push({ id, name: `Officer ${id}`, branch: 'Kochi', role: 'SO' });
const records = Array.from({ length: 30 }, (_, i) => ({ id: i + 1, name: `RNR Customer ${i + 1}`, analysis_status: 'RNR', status: 'PENDING', so_id: 2 }));
for (const [analysis_status, status, loss_reason, so_id] of [['Lost Lead', 'LOST', 'Dropped', 2], ['Lost Lead', 'LOST', 'Reason not recorded', null], ['Fresh', 'FRESH', '', 3], ['Line Busy', 'PENDING', '', 2], ['Need time', 'PENDING', '', 2], ['Booking Done', 'WALKIN', '', 2]]) {
  records.push({ id: records.length + 1, name: `${analysis_status} Customer`, analysis_status, status, loss_reason, so_id });
}
for (const officer of officers.slice(2)) records.push({ id: records.length + 1, name: `Customer of ${officer.name}`, analysis_status: 'Fresh', status: 'FRESH', so_id: officer.id });
records.forEach(row => Object.assign(row, { phone: '9876543210', branch: 'Kochi', enquiry_date: '2026-09-15', so: officers.find(o => o.id === row.so_id)?.name, calls: 30, last_call: '2026-09-30T10:00:00Z' }));
const psCounts = items => ({ passed_to_ps: items.filter(row => row.so_id !== null).length, untouched_by_ps: items.filter(row => row.so_id !== null && row.status === 'FRESH').length });
const counts = (items, field) => [...new Set(items.map(row => row[field]))].map(key => ({ key, label: key, count: items.filter(row => row[field] === key).length })).sort((a, b) => b.count - a.count || a.key.localeCompare(b.key));
const statuses = counts(records, 'analysis_status');
const lost = records.filter(row => row.status === 'LOST');
const lead_analysis = { ...psCounts(records), total: records.length, lost_total: lost.length, statuses, loss_reasons: counts(lost, 'loss_reason'), officers: [...officers, { id: null, name: 'Unassigned Sales Officer', branch: '' }].map(officer => {
  const owned = records.filter(row => row.so_id === officer.id);
  return { ...psCounts(owned), key: officer.id === null ? '__unassigned__' : String(officer.id), name: officer.name, branch: officer.branch, total: owned.length, statuses: Object.fromEntries(counts(owned, 'analysis_status').map(row => [row.key, row.count])) };
}) };
const history = Array.from({ length: 30 }, (_, i) => ({ id: i + 1, kind: 'call', occurred_at: `2026-08-0${i < 5 ? 1 : 2}T10:${String(i).padStart(2, '0')}:00Z`, actor: 'Rahul P M', actor_role: 'SO', before: {}, after: { outcome: 'RNR', remarks: `Earlier call ${i + 1}` }, provenance: 'live' }));
[
  { kind: 'created', after: {} },
  { kind: 'so_updated', before: { status: 'FRESH' }, after: { status: 'QUALIFIED' } },
  { kind: 'call', after: { status: 'QUALIFIED', outcome: 'Need Test Drive', remarks: 'Customer requested a weekend test drive.' } },
  { kind: 'status_changed', before: { status: 'QUALIFIED' }, after: { status: 'WALKIN' } },
  { kind: 'booking_cancelled', before: { status: 'WALKIN', sales_outcome: 'BOOKED' }, after: { status: 'LOST', sales_outcome: 'LOST' } },
  { kind: 'reopened', before: { status: 'LOST' }, after: { status: 'FRESH' } },
  { kind: 'status_changed', provenance: 'legacy', after: { status: 'RNR' } },
  { kind: 'assigned_ps', before: { assigned_ps: 2 }, after: { assigned_ps: 3 } },
  { kind: 'qualification_updated', before: { trade_in: false }, after: { trade_in: true } },
].forEach((event, index) => Object.assign(history[index], event));
const paginate = (items, params) => { const page = Number(params.get('page') || 1); return { count: items.length, results: items.slice((page - 1) * 25, page * 25), next: page * 25 < items.length ? '?page=2' : null, previous: page > 1 ? '?page=1' : null }; };

(async () => {
  const browser = await puppeteer.launch({ executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium-browser', headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  try {
    const page = await browser.newPage();
    const errors = [], requests = [];
    let failHistoryOnce = false;
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
      else if (url.pathname === '/api/ceo/overview/') data = { lead_analysis, etbr: { E: records.length, T: 0, B: 1, R: 0 }, targets: { available: false }, conversions: { E_T: 0, E_B: 3, E_R: 0, T_B: null, B_R: 0 }, current: {}, activity: {}, complaints: {}, coverage: {}, branches: [{ key: 'kochi', label: 'Kochi', ...psCounts(records), E: records.length, T: 0, B: 1, R: 0, conversion: 0 }], ageing: {} };
      else if (/\/leads\/\d+\/history\/$/.test(url.pathname)) {
        if (failHistoryOnce) { failHistoryOnce = false; return request.respond({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'History temporarily unavailable' }) }); }
        const matching = history.filter(event => !params.get('kind') || event.kind === params.get('kind'));
        data = paginate(params.get('order') === 'newest' ? matching.toReversed() : matching, params);
      }
      else if (/\/leads\/\d+\/$/.test(url.pathname)) data = { ...records.find(row => row.id === Number(url.pathname.split('/')[4])), milestones: [{ kind: 'E', occurred_on: '2026-08-01' }, { kind: 'B', occurred_on: '2026-08-01' }], assigned_ps: 2, assigned_ps_name: 'Rahul P M', assigned_ps_phone: '9876543211' };
      else if (url.pathname === '/api/ceo/leads/') {
        const matches = records.filter(row => (!params.has('ps_handling') || (row.so_id !== null && (params.get('ps_handling') === 'passed' || row.status === 'FRESH'))) && (!params.has('analysis_status') || row.analysis_status === params.get('analysis_status')) && (!params.has('loss_reason') || row.loss_reason === params.get('loss_reason')) && (!params.has('analysis_officer') || (row.so_id === null ? '__unassigned__' : String(row.so_id)) === params.get('analysis_officer')) && (!params.has('q') || row.name.includes(params.get('q'))));
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
      await page.waitForFunction(() => document.querySelector('.ceo-analysis-results .ceo-pagination'));
      assert.equal(new URL(page.url()).pathname, '/ceo');
      const params = requests.filter(url => url.pathname === '/api/ceo/leads/').at(-1).searchParams;
      for (const [key, value] of Object.entries(expected)) assert.equal(params.get(key), value);
      assert.deepEqual(params.getAll('branch'), ['kochi', 'thrissur']);
      assert.equal(params.get('date_from'), '2026-09-01');
      assert.equal(params.get('source'), 'META');
      assert.equal(params.get('metric'), null);
      assert.equal(params.get('scope'), null);
    };
    await checkDrill('.ceo-analysis button[aria-label="View RNR leads"]', { analysis_status: 'RNR' });
    await page.screenshot({ path: '/tmp/ceo-analysis-list-desktop.png' });
    await Promise.all([page.waitForResponse(response => new URL(response.url()).pathname === '/api/ceo/leads/' && new URL(response.url()).searchParams.get('page') === '2'), click('.ceo-analysis-results .ceo-pagination button:last-child')]);
    await page.waitForFunction(() => document.querySelectorAll('.ceo-analysis-results tbody tr').length === 5);
    await click('.ceo-analysis-results tbody tr:first-child td:first-child button');
    await page.waitForSelector('.ceo-detail-grid');
    assert.match(await page.$eval('dialog:last-of-type', node => node.textContent), /Customer & ownership/);
    assert.match(await page.$eval('.ceo-consultant-info', node => node.textContent), /9876543211/);
    await page.waitForSelector('.ceo-history-item');
    assert.equal(await page.$eval('select[aria-label="History order"]', node => node.value), 'oldest');
    assert.match(await page.$eval('.ceo-history-item:first-child', node => node.textContent), /Lead created/);
    assert.deepEqual(await page.$$eval('.ceo-stage-transition', rows => rows.map(node => node.textContent)), ['Fresh→Qualified', 'Qualified→Booked', 'Booked→Lost', 'Lost→Fresh', 'Previous stage not recorded→RNR']);
    assert.equal(await page.$$eval('.ceo-history-item:nth-child(3) .ceo-stage-transition', rows => rows.length), 0);
    assert.match(await page.$eval('.ceo-history-item:nth-child(3)', node => node.textContent), /Stage at time of callQualified/);
    assert.match(await page.$eval('.ceo-history-item:nth-child(9)', node => node.textContent), /No → Yes/);
    assert.match(await page.$eval('.ceo-lead-journey', node => node.textContent), /Test drive completedNot recorded/);
    assert.match(await page.$eval('.ceo-lead-journey', node => node.textContent), /First booking01\/08\/2026/);
    assert.equal(await page.$$eval('.ceo-history-day', rows => rows.length), 2);
    await page.screenshot({ path: '/tmp/ceo-analysis-detail-desktop.png' });
    await page.evaluate(() => [...document.querySelectorAll('dialog:last-of-type button')].find(node => node.textContent === 'View history ↓').click());
    assert.ok(await page.$eval('dialog:last-of-type', node => node.querySelector('.ceo-detail-body[tabindex] h3').getBoundingClientRect().top >= node.querySelector('header').getBoundingClientRect().bottom), 'timeline shortcut clears the sticky header');
    await page.screenshot({ path: '/tmp/ceo-history-desktop.png' });
    assert.equal(await page.$$eval('.ceo-history-item', rows => rows.length), 25);
    await page.evaluate(() => [...document.querySelectorAll('button')].find(node => node.textContent === 'Load more history').click());
    await page.waitForFunction(() => document.querySelectorAll('.ceo-history-item').length === 30);
    assert.equal(await page.$$eval('.ceo-history-day', rows => rows.length), 2, 'same day continues across pages');
    await page.select('select[aria-label="History event type"]', 'status_changed');
    await page.waitForFunction(() => document.querySelectorAll('.ceo-history-item').length === 2);
    assert.equal(requests.filter(url => url.pathname.endsWith('/history/')).at(-1).searchParams.get('page'), '1');
    await page.select('select[aria-label="History order"]', 'newest');
    await page.waitForFunction(() => document.querySelector('.ceo-history-item:first-child')?.textContent.includes('Historical record'));
    await page.select('select[aria-label="History event type"]', 'test_drive_completed');
    await page.waitForFunction(() => document.querySelector('dialog:last-of-type .ceo-empty')?.textContent.includes('No events match'));
    failHistoryOnce = true;
    await page.select('select[aria-label="History event type"]', '');
    await page.waitForFunction(() => document.querySelector('.ceo-error')?.textContent.includes('Retry history'));
    await page.evaluate(() => [...document.querySelectorAll('button')].find(node => node.textContent === 'Retry history').click());
    await page.waitForFunction(() => document.querySelectorAll('.ceo-history-item').length === 25);
    assert.match(await page.$eval('.ceo-history-item:first-child', node => node.textContent), /Earlier call 30/);
    assert.ok(requests.filter(url => url.pathname.endsWith('/history/')).every(url => !url.searchParams.has('date_from')));
    await click('button[aria-label="← Back to matching leads"]');
    assert.equal(await page.$$eval('.ceo-analysis-results tbody tr', rows => rows.length), 5);
    assert.match(await page.$eval('.ceo-analysis-results .ceo-pagination', node => node.textContent), /26–30 of 30/);
    await page.type('.ceo-analysis-results input[type="search"]', 'Customer 29');
    await page.waitForFunction(() => document.querySelector('.ceo-analysis-results .ceo-pagination')?.textContent.includes('1–1 of 1'));
    await click('.ceo-analysis-results tbody tr:first-child td:first-child button');
    await page.waitForSelector('.ceo-detail-grid');
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => document.querySelectorAll('dialog[open]').length === 1);
    assert.equal(await page.$eval('.ceo-analysis-results input[type="search"]', node => node.value), 'Customer 29');
    await click('button[aria-label="← Back to analysis"]');
    assert.equal(await page.$$eval('dialog[open]', rows => rows.length), 0);
    await checkDrill('.ceo-analysis button[aria-label="View 30 RNR leads"]', { analysis_status: 'RNR' });
    await checkDrill('.ceo-analysis-lost button[aria-label="View Dropped leads"]', { analysis_status: 'Lost Lead', loss_reason: 'Dropped' });
    await checkDrill('.ceo-analysis-lost button[aria-label="View 1 Dropped leads"]', { loss_reason: 'Dropped' });
    await checkDrill('.ceo-analysis-officers tbody tr:first-child th button', { analysis_officer: '2' });
    await checkDrill('.ceo-analysis-officers tbody tr:first-child td:nth-child(2) button', { analysis_officer: '2' });
    await checkDrill('.ceo-analysis-officers tbody tr:first-child td:nth-child(5) button', { analysis_officer: '2', analysis_status: 'RNR' });
    await checkDrill('.ceo-analysis-officers tbody tr:nth-child(2) td:nth-child(5) button', { analysis_officer: '3', analysis_status: 'RNR' });
    assert.match(await page.$eval('.ceo-analysis-results', node => node.textContent), /No records match/);
    await checkDrill('.ceo-analysis-officers thead th:nth-child(5) button', { analysis_status: 'RNR' });
    await checkDrill('.ceo-analysis-officers tfoot td:nth-child(5) button', { analysis_status: 'RNR' });
    await checkDrill('.ceo-analysis-officers tfoot td:nth-child(2) button', {});
    await checkDrill('.ceo-analysis-officers tbody tr:first-child td:nth-child(3) button', { analysis_officer: '2', ps_handling: 'passed' });
    await checkDrill('.ceo-analysis-officers tbody tr:nth-child(2) td:nth-child(4) button', { analysis_officer: '3', ps_handling: 'untouched' });
    assert.match(await page.$eval('dialog[open]', node => node.textContent), /Untouched by PS/);
    assert.equal(await page.$$eval('.ceo-analysis-results tbody tr', rows => rows.length), 1);
    await checkDrill('.ceo-analysis-officers thead th:nth-child(4) button', { ps_handling: 'untouched' });
    await checkDrill('.ceo-analysis-officers tfoot td:nth-child(3) button', { ps_handling: 'passed' });
    await checkDrill('.ceo-analysis-officers tfoot td:nth-child(4) button', { ps_handling: 'untouched' });
    await overview();
    await Promise.all([page.waitForResponse(response => new URL(response.url()).pathname === '/api/ceo/leads/'), click('.ceo-table-card button[title="Current PS assignment for enquiries received in the selected dates"]')]);
    await ready();
    assert.equal(new URL(page.url()).pathname, '/ceo/leads');
    const branchParams = requests.filter(url => url.pathname === '/api/ceo/leads/').at(-1).searchParams;
    assert.equal(branchParams.get('branch'), 'kochi');
    assert.equal(branchParams.get('ps_handling'), 'passed');
    assert.equal(branchParams.get('date_from'), '2026-09-01');
    assert.equal(branchParams.get('source'), 'META');
    assert.match(await page.$eval('.ceo-filter-chips', node => node.textContent), /Passed to PS/);
    await overview();
    assert.equal(await page.$$eval('.ceo-analysis-officers tbody tr', rows => rows.length), 10);
    await click('button[aria-label="Officer page 2"]');
    assert.equal(await page.$$eval('.ceo-analysis-officers tbody tr', rows => rows.length), 4);
    await click('.ceo-analysis-officers tbody tr:last-child th button');
    await page.waitForSelector('.ceo-analysis-results .ceo-pagination');
    assert.equal(requests.filter(url => url.pathname === '/api/ceo/leads/').at(-1).searchParams.get('analysis_officer'), '__unassigned__');
    await click('button[aria-label="← Back to analysis"]');
    assert.equal(await page.$eval('button[aria-current="page"]', node => node.textContent), '2');
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
    await click('.ceo-analysis-officers tbody tr:first-child th button');
    await page.waitForSelector('.ceo-analysis-results .ceo-pagination');
    await page.screenshot({ path: '/tmp/ceo-analysis-list-mobile.png' });
    assert.ok(await page.$eval('dialog[open]', node => node.getBoundingClientRect().right <= innerWidth && node.getBoundingClientRect().left >= 0), 'mobile dialog fits viewport');
    await click('.ceo-analysis-results tbody tr:first-child td:first-child button');
    await page.waitForSelector('.ceo-history-item');
    await page.screenshot({ path: '/tmp/ceo-analysis-detail-mobile.png' });
    await page.evaluate(() => [...document.querySelectorAll('dialog:last-of-type button')].find(node => node.textContent === 'View history ↓').click());
    assert.ok(await page.$eval('dialog:last-of-type', node => node.querySelector('.ceo-detail-body[tabindex] h3').getBoundingClientRect().top >= node.querySelector('header').getBoundingClientRect().bottom), 'timeline shortcut clears the sticky header');
    await page.screenshot({ path: '/tmp/ceo-history-mobile.png' });
    assert.ok(await page.$eval('dialog:last-of-type', node => node.scrollWidth <= node.clientWidth + 2), 'mobile history has no horizontal overflow');
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => document.querySelectorAll('dialog[open]').length === 1);
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => !document.querySelector('dialog[open]'));
    const refresh = requests.filter(url => url.searchParams.has('refresh')).length;
    await Promise.all([page.waitForResponse(response => response.url().includes('refresh=')), page.evaluate(() => [...document.querySelectorAll('button')].find(node => node.textContent.includes('Refresh')).click())]);
    await page.waitForFunction(() => !document.querySelector('.ceo-loading'));
    assert.ok(requests.filter(url => url.searchParams.has('refresh')).length > refresh);
    assert.deepEqual(errors, []);
    console.log('PASS: stage transitions, cancellation/reopening, unknown history, milestone accuracy, filtering/order/retry, PS handoff/untouched totals and officer/branch drilldowns, filtered modal links, officer/list pagination, contact details and inline lifetime history, preserved list state on Back/Escape, dashboard filters, refresh, and desktop/mobile layout.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
