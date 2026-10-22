// Run against `npm run build && npm run start -- --hostname 127.0.0.1 --port 3100`.
// Uses an installed Chromium and Node's built-in CDP/WebSocket support, no npm additions.
// All localhost:8000 API requests are intercepted; no real account or database is used.
const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const { mkdtempSync, rmSync } = require("node:fs");
const { tmpdir } = require("node:os");
const { join } = require("node:path");
const { setTimeout: sleep } = require("node:timers/promises");

const origin = "http://127.0.0.1:3100";
const profile = mkdtempSync(join(tmpdir(), "crm-loading-browser-"));
const browser = spawn(process.env.CHROME_EXECUTABLE || "/snap/bin/chromium", [
  "--headless", "--no-sandbox", "--disable-gpu", "--remote-debugging-port=0",
  `--user-data-dir=${profile}`, "about:blank",
], { stdio: ["ignore", "ignore", "pipe"] });

const page = results => ({ count: results.length, next: null, previous: null, results });
const user = role => ({ id: 1, role, first_name: "Loading", last_name: "Fixture", email: "loading@example.invalid", location: "Kochi", is_active: true });
const lead = name => ({ id: 1, name, phone: "9000000000", source: "WEBSITE", source_label: "Website", status: "FRESH",
  model_interest: "Indie", branch: "Kochi", enquiry_date: "2026-10-22", created_at: "2026-10-22T06:00:00Z",
  assigned_so: null, assigned_ps: null, assigned_ps_name: "", assigned_so_name: "", qualification: null, call_count: 0 });
const summary = Object.fromEntries(["total", "fresh", "followups", "missed", "pending", "qualified", "booked", "walkin", "won", "lost",
  "won_lost", "untouched", "called", "scheduled", "etbr_enquired", "etbr_test_drive_completed", "etbr_booked", "etbr_retailed"].map(key => [key, 1]));

async function main() {
  const endpoint = await new Promise((resolve, reject) => {
    let log = "";
    const timeout = setTimeout(() => reject(new Error(`Chromium did not start: ${log.slice(-1200)}`)), 15000);
    browser.once("error", reject);
    browser.once("exit", code => { clearTimeout(timeout); reject(new Error(`Chromium exited ${code}: ${log.slice(-1200)}`)); });
    browser.stderr.on("data", bytes => {
      log += bytes;
      const match = log.match(/DevTools listening on (ws:\/\/\S+)/);
      if (match) { clearTimeout(timeout); resolve(match[1]); }
    });
  });
  const socket = new WebSocket(endpoint);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let sequence = 0, sessionId, role = "ADMIN", holdAnalytics = false, holdOldSearch = false;
  const pending = new Map(), requests = [], held = [], errors = [];
  const send = (method, params = {}, session = sessionId) => new Promise((resolve, reject) => {
    const id = ++sequence;
    const timeout = setTimeout(() => { pending.delete(id); reject(new Error(`CDP timeout: ${method}`)); }, 10000);
    pending.set(id, { resolve: result => { clearTimeout(timeout); resolve(result); }, reject: error => { clearTimeout(timeout); reject(error); } });
    socket.send(JSON.stringify({ id, method, params, ...(session ? { sessionId: session } : {}) }));
  });
  const respond = (requestId, body, status = 200) => send("Fetch.fulfillRequest", { requestId, responseCode: status,
    responseHeaders: [{ name: "Content-Type", value: "application/json" }, { name: "Access-Control-Allow-Origin", value: origin },
      { name: "Access-Control-Allow-Credentials", value: "true" }], body: Buffer.from(JSON.stringify(body)).toString("base64") });
  socket.onmessage = event => {
    const message = JSON.parse(event.data);
    if (message.id) {
      const task = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) task?.reject(new Error(message.error.message)); else task?.resolve(message.result);
      return;
    }
    if (message.method === "Runtime.exceptionThrown") errors.push(message.params.exceptionDetails.text);
    if (message.method !== "Fetch.requestPaused") return;
    const { requestId, request } = message.params;
    const url = new URL(request.url);
    requests.push(url.pathname + url.search);
    assert.equal(request.method, "GET", "Browser checks must not mutate application data");
    let body = page([]);
    if (url.pathname === "/api/auth/me/") body = { user: user(role) };
    if (url.pathname === "/api/system-config/") body = { lists: { branches: ["Kochi"], sources: ["WEBSITE"], models: ["Indie"], colorVariants: ["No Preference", "Blue"] }, rto_options: [], complaint_subtypes: {}, so_lead_sources: ["WEBSITE"] };
    if (["/api/auth/cre-users/", "/api/auth/sales-officers/"].includes(url.pathname)) body = page([user("CRE")]);
    if (url.pathname === "/api/leads/") body = page([lead("Performance fixture")]);
    if (url.pathname === "/api/leads/my-dashboard/") body = { summary, section: "fresh", results: [lead(url.searchParams.get("q") || "Performance fixture")] };
    if (url.pathname === "/api/analytics/admin/") body = { summary, source: [], cre: [], officers: [] };
    if (url.pathname === "/api/analytics/sales-manager/") body = { range: "mtd", branch: "Kochi", summary: { ...summary, delta: {} },
      ps: [{ ...summary, id: 1, name: "Officer fixture", email: "ps@example.invalid", calls: 88 }], cre: [], source: [], models: [],
      colors: [{ ...summary, color: "No Preference" }], status: [], categories: [], monthly: [], funnel: [], lost_reasons: [], stale_leads: [],
      followups: { due: 0, overdue: 0, by_owner: [] }, filters: { ps: [{ id: 1, name: "Officer fixture" }], source: [], models: [], cre: [] } };
    if (url.pathname === "/api/analytics/sales-manager/ps-followups/") body = { rows: [], leads: [] };
    if (url.pathname === "/api/ceo/options/") body = { branches: [{ value: "kochi", label: "Kochi" }], employees: [], roles: [], rtos: [], statuses: [], source: [], campaign: [], model_interest: [], activities: [], sub_activities: {} };
    if (url.pathname === "/api/ceo/branch-sales/") body = page([{ key: "kochi", label: "Kochi", total: 10, booked: 3, retailed: 2, lost: 1, conversion: 20, last_call: "2026-10-22T06:00:00Z", last_call_lead_id: 1 }]);
    if (url.pathname === "/api/ceo/leads/") body = page([{ ...lead("Branch drilldown fixture"), branch: "Kochi" }]);
    if (url.pathname === "/api/ceo/leads/1/") body = { ...lead("Branch call fixture"), related_complaints: [], milestones: [] };
    if (url.pathname === "/api/ceo/leads/1/history/") body = page([]);
    if (url.pathname.endsWith("unread_count/")) body = { count: 0 };
    if ((holdAnalytics && url.pathname === "/api/analytics/admin/") || (holdOldSearch && url.searchParams.get("q") === "old")) {
      held.push(status => respond(requestId, status === 500 ? { detail: "Analytics unavailable" } : body, status).catch(() => {}));
    } else void respond(requestId, body).catch(error => errors.push(error.message));
  };
  try {
    const target = await send("Target.createTarget", { url: "about:blank" });
    ({ sessionId } = await send("Target.attachToTarget", { targetId: target.targetId, flatten: true }));
    await send("Page.enable");
    await send("Runtime.enable");
    await send("Fetch.enable", { patterns: [{ urlPattern: "http://localhost:8000/api/*" }] });
    const evaluate = async expression => (await send("Runtime.evaluate", { expression, returnByValue: true })).result.value;
    const until = async (expression, message) => {
      for (let i = 0; i < 80; i++) { if (await evaluate(expression)) return; await sleep(100); }
      throw new Error(`${message}; requests=${JSON.stringify(requests)}; errors=${JSON.stringify(errors)}; page=${await evaluate("document.body.innerText.slice(0,2000)")}`);
    };
    const navigate = async (nextRole, path, text) => {
      role = nextRole; requests.length = 0;
      await send("Page.navigate", { url: origin + path });
      await until(`document.body.innerText.includes(${JSON.stringify(text)})`, `${nextRole} ${path} did not load`);
      await sleep(300);
      assert.equal(requests.filter(path => path === "/api/auth/me/").length, 1, `${nextRole} should verify its session once`);
    };

    holdAnalytics = true;
    await navigate("ADMIN", "/all-leads", "Performance fixture");
    assert.equal(held.length, 1, "List should render before analytics completes");
    await held.shift()(500);
    await until(`document.body.innerText.includes('Retry assignment data')`, "Support failure should be independently retryable");
    assert.equal(await evaluate(`document.body.innerText.includes('Performance fixture')`), true);
    holdAnalytics = false;
    await evaluate(`[...document.querySelectorAll('button')].find(b => b.textContent.includes('Retry assignment data')).click()`);
    await until(`!document.body.innerText.includes('Loading assignment data') && !document.body.innerText.includes('Retry assignment data')`, "Support retry should recover");
    holdAnalytics = true;
    await navigate("ADMIN", "/leads", "1 matching fresh lead");
    assert.equal(await evaluate(`[...document.querySelectorAll('button')].find(b => b.textContent.includes('Auto assign')).disabled`), true);
    holdAnalytics = false;
    await held.shift()(200);
    await until(`![...document.querySelectorAll('button')].find(b => b.textContent.includes('Auto assign')).disabled`, "Support retry should enable assignment");
    console.log("PASS admin rows render independently; support errors preserve rows and retry safely");

    for (const [nextRole, path, text] of [["CRE", "/my-leads", "Performance fixture"], ["SO", "/my-leads", "Performance fixture"],
      ["SERVICE", "/services", "Branch services"], ["RECEPTIONIST", "/capture", "Capture"], ["CRE", "/complaints", "Log customer complaints"]]) {
      await navigate(nextRole, path, text);
      console.log(`PASS ${nextRole} ${path}: one session check`);
    }
    await navigate("CRE", "/my-leads", "Performance fixture");
    const typeSearch = value => evaluate(`(() => { const input = document.querySelector('input[placeholder*="Search"]');
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, ${JSON.stringify(value)});
      input.dispatchEvent(new Event('input', { bubbles: true })); })()`);
    holdOldSearch = true;
    await typeSearch("old");
    for (let i = 0; i < 30 && !held.length; i++) await sleep(100);
    assert.equal(held.length, 1);
    await typeSearch("new");
    await until(`!!document.querySelector('tbody')?.innerText.includes('new')`, "Newest search should render while old search is pending");
    await held.shift()(200);
    await sleep(300);
    assert.equal(await evaluate(`document.querySelector('tbody').innerText.includes('old')`), false);
    console.log("PASS superseded search cannot overwrite newer results");

    const assertColourRequired = async () => {
      await until(`[...document.querySelectorAll('form select')].some(s => [...s.options].some(o => o.value === 'No Preference'))`, "Colour options should load");
      const field = `[...document.querySelectorAll('form select')].find(s => [...s.options].some(o => o.value === 'No Preference'))`;
      assert.equal(await evaluate(`${field}.required`), true, "Colour selection is required");
      assert.equal(await evaluate(`${field}.value`), "", "Staff must explicitly choose a colour");
      assert.equal(await evaluate(`${field}.checkValidity()`), false, "Blank colour is invalid");
      assert.equal(await evaluate(`${field}.innerText.includes('Color not set')`), false);
      await evaluate(`(() => { const select = ${field}; Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(select, 'No Preference'); select.dispatchEvent(new Event('change', { bubbles: true })); })()`);
      assert.equal(await evaluate(`${field}.checkValidity()`), true, "No Preference is valid");
    };
    await navigate("RECEPTIONIST", "/capture", "Capture");
    await assertColourRequired();
    console.log("PASS receptionist capture requires explicit colour or No Preference");
    for (const nextRole of ["CRE", "SO"]) {
      await navigate(nextRole, "/my-leads", "Performance fixture");
      await evaluate(`[...document.querySelectorAll('button')].find(b => /add.*lead/i.test(b.textContent)).click()`);
      await assertColourRequired();
      console.log(`PASS ${nextRole} lead creation requires explicit colour or No Preference`);
    }
    await navigate("SALES_MANAGER", "/manager/analytics", "Officer fixture");
    const headers = await evaluate(`[...document.querySelector('.manager-table thead').querySelectorAll('th')].map(th => th.textContent)`);
    assert.equal(headers.includes("Calls"), false);
    assert.equal(headers.includes("Last call"), true);
    assert.equal(await evaluate(`[...document.querySelectorAll('tr')].find(row => row.innerText.includes('No Preference')).getAttribute('role')`), "link");
    console.log("PASS SM performance omits Calls and No Preference remains clickable");

    const branchPath = "/ceo/branches?range=custom&date_from=2026-10-01&date_to=2026-10-22&source=WEBSITE";
    await navigate("CEO", branchPath, "Branch performance");
    await until(`document.querySelector('.ceo-table-card tbody')?.innerText.includes('Kochi')`, "CEO branch rows should load");
    assert.deepEqual(await evaluate(`[...document.querySelectorAll('.ceo-table-card th')].map(th => th.textContent)`), ["Branch", "Total", "Booked", "Retailed", "Lost", "Conv.", "Last call"]);
    assert.equal(await evaluate(`!!document.querySelector('.ceo-columns')`), false);
    for (const [column, metric] of [[0, "total"], [1, "total"], [2, "booked"], [3, "retailed"], [4, "lost"], [5, "retailed"]]) {
      if (column) { await navigate("CEO", branchPath, "Branch performance"); await until(`document.querySelector('.ceo-table-card tbody')?.innerText.includes('Kochi')`, "Branch row should reload"); }
      await evaluate(`document.querySelector('.ceo-table-card tbody tr').children[${column}].querySelector('button').click()`);
      await until(`location.pathname === '/ceo/leads' && document.body.innerText.includes('Branch drilldown fixture')`, "Branch metric should open matching leads");
      const query = new URLSearchParams(await evaluate("location.search"));
      assert.equal(query.get("branch"), "kochi"); assert.equal(query.get("branch_metric"), metric);
      assert.equal(query.get("source"), "WEBSITE"); assert.equal(query.get("date_from"), "2026-10-01"); assert.equal(query.get("date_to"), "2026-10-22");
    }
    await navigate("CEO", branchPath, "Branch performance");
    await until(`document.querySelector('.ceo-table-card tbody')?.innerText.includes('Kochi')`, "Branch row should reload for history");
    await evaluate(`document.querySelector('.ceo-table-card tbody tr').children[6].querySelector('button').click()`);
    await until(`document.querySelector('dialog[open]')?.innerText.includes('Lead history')`, "Last call should open customer history");
    assert.equal(requests.some(path => path.startsWith('/api/ceo/leads/1/history/')), true);
    console.log("PASS CEO branch columns, all metric links, preserved filters, and Last call history");

    await navigate("ADMIN", "/my-leads", "SESSION CONFLICT");
    assert.equal(requests.some(path => path.startsWith("/api/leads/my-dashboard/")), false);
    console.log("PASS conflicting role blocks workspace data requests");
    assert.deepEqual(errors, [], "No uncaught browser exceptions");
  } finally { socket.close(); }
}

main().catch(error => { console.error(error); process.exitCode = 1; }).finally(async () => {
  browser.kill();
  await sleep(500);
  rmSync(profile, { recursive: true, force: true });
});
