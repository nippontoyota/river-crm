const assert = require("node:assert/strict");
const { test } = require("node:test");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

// Exercise the hook's event lifecycle and actual API helpers without adding a
// DOM/test-framework dependency. Browser rendering is checked separately.
function load(relative, globals = {}, imports = {}) {
  const filename = path.join(__dirname, "..", "src", relative);
  const compiled = ts.transpileModule(fs.readFileSync(filename, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const loaded = { exports: {} };
  const context = { module: loaded, exports: loaded.exports, process, Headers, URLSearchParams, FormData,
    ...globals, require: name => imports[name] ?? (name.startsWith("@/")
      ? load(`${name.slice(2)}.ts`, globals, imports) : require(name)) };
  vm.runInNewContext(compiled, context, { filename });
  return loaded.exports;
}

const settle = async () => { await new Promise(setImmediate); };
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function mountRefresh(refresh, enabled = true) {
  const effects = [];
  const window = new EventTarget();
  const document = new EventTarget();
  document.visibilityState = "visible";
  let timer, cleared = false;
  window.setInterval = (callback, ms) => { assert.equal(ms, 30000); timer = callback; return 1; };
  window.clearInterval = id => { assert.equal(id, 1); cleared = true; };
  const { useCrmRefresh } = load("lib/use-crm-refresh.ts", { window, document }, {
    react: { useRef: value => ({ current: value }), useEffect: effect => effects.push(effect) },
  });
  useCrmRefresh(refresh, enabled);
  const cleanups = effects.map(effect => effect());
  return { window, document, tick: () => timer?.(), cleared: () => cleared,
    unmount: () => cleanups.forEach(cleanup => cleanup?.()) };
}

test("refresh coalesces focus/timer events and follows an in-flight mutation once", async () => {
  const first = deferred();
  let calls = 0;
  const hook = mountRefresh(() => { calls++; return calls === 1 ? first.promise : Promise.resolve(); });
  hook.window.dispatchEvent(new Event("focus"));
  await settle();
  hook.tick();
  hook.window.dispatchEvent(new Event("focus"));
  hook.window.dispatchEvent(new Event("crm-data-changed"));
  hook.window.dispatchEvent(new Event("crm-data-changed"));
  assert.equal(calls, 1);
  first.resolve();
  await settle();
  assert.equal(calls, 2);
  hook.unmount();
  assert.equal(hook.cleared(), true);
});

test("hidden tabs pause, visibility resumes, failures recover, and cleanup drops queued work", async () => {
  const pending = deferred();
  let calls = 0;
  const hook = mountRefresh(() => { calls++; return calls === 1 ? Promise.reject(new Error("offline")) : pending.promise; });
  hook.document.visibilityState = "hidden";
  hook.tick();
  await settle();
  assert.equal(calls, 0);
  hook.document.visibilityState = "visible";
  hook.document.dispatchEvent(new Event("visibilitychange"));
  await settle();
  hook.tick();
  await settle();
  assert.equal(calls, 2);
  hook.window.dispatchEvent(new Event("crm-data-changed"));
  hook.unmount();
  pending.resolve();
  await settle();
  hook.window.dispatchEvent(new Event("focus"));
  assert.equal(calls, 2);
});

test("storage invalidation refreshes other tabs; disabled refresh does no work", async () => {
  let calls = 0;
  const hook = mountRefresh(() => { calls++; });
  for (const key of ["unrelated", "crm-data-changed"]) {
    const event = new Event("storage");
    event.key = key;
    hook.window.dispatchEvent(event);
  }
  await settle();
  assert.equal(calls, 1);
  hook.unmount();
  const disabled = mountRefresh(() => { calls++; }, false);
  disabled.window.dispatchEvent(new Event("crm-data-changed"));
  disabled.tick();
  await settle();
  assert.equal(calls, 1);
  disabled.unmount();
});

test("lead and assignment reads propagate cancellation without retrying aborted requests", async () => {
  let calls = 0;
  const crm = load("lib/crm.ts", { fetch: (_url, options) => {
    calls++;
    return new Promise((_resolve, reject) => options.signal.addEventListener("abort",
      () => reject(new DOMException("Cancelled", "AbortError")), { once: true }));
  } });
  const reads = [signal => crm.getLeadsPage("?q=old", signal), signal => crm.getMyDashboard({ q: "old" }, signal),
    signal => crm.getManagerLeads("q=old", signal), signal => crm.getCres(signal),
    signal => crm.getOfficers("Kochi", signal), signal => crm.getAdminAnalytics(signal),
    signal => crm.getUnassignedCeCount(signal)];
  for (const read of reads) {
    const controller = new AbortController();
    const request = read(controller.signal);
    controller.abort();
    await assert.rejects(request, { name: "AbortError" });
  }
  assert.equal(calls, reads.length);
});

test("session checks share only in-flight work and revalidate after completion", async () => {
  const response = deferred();
  let calls = 0;
  const crm = load("lib/crm.ts", { fetch: () => { calls++; return response.promise; } });
  const first = crm.getCurrentUser();
  const second = crm.getCurrentUser();
  assert.equal(first, second);
  response.resolve({ ok: true, status: 200, json: async () => ({ user: { id: 1, role: "CRE" } }) });
  await first;
  assert.equal(calls, 1);
  await crm.getCurrentUser();
  assert.equal(calls, 2);
});
