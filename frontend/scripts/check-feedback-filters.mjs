import assert from 'node:assert/strict';
// Run against a local Next dev server and a headless Chromium started with --remote-debugging-port=9224.
// All API responses are mocked; no CRM data is read or changed. Pass --ceo to check the CEO route.
const baseURL = process.env.FRONTEND_URL || 'http://localhost:3100';
const role = process.argv.includes('--ceo') ? 'CEO' : 'ADMIN';
const target = await (await fetch(`${process.env.CDP_URL || 'http://127.0.0.1:9224'}/json/new?about:blank`, {method:'PUT'})).json();
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise(resolve => ws.addEventListener('open', resolve));
let seq = 0;
const pending = new Map();
ws.addEventListener('message', e => { const msg = JSON.parse(e.data); if (msg.id) { const item = pending.get(msg.id); pending.delete(msg.id); msg.error ? item.reject(msg.error) : item.resolve(msg.result); } });
function send(method, params = {}) { return new Promise((resolve, reject) => { const id = ++seq; pending.set(id, {resolve, reject}); ws.send(JSON.stringify({id, method, params})); }); }
async function evaluate(expression) { const r = await send('Runtime.evaluate', {expression, returnByValue:true, awaitPromise:true}); if(r.exceptionDetails) throw Error(JSON.stringify(r.exceptionDetails)); return r.result.value; }
async function until(expression) { for(let i=0;i<120;i++) { if(await evaluate(expression)) return; await new Promise(r=>setTimeout(r,100)); } console.log(await evaluate('({url:location.href,text:document.body.innerText,errors:window.__errors,requests:window.__feedbackRequests})')); throw Error('Timed out: '+expression); }
const fixture = `
const originalFetch = window.fetch;
window.__errors=[];window.addEventListener('error',e=>window.__errors.push(e.message));
window.__feedbackRequests = [];
window.__summaryRequests = 0;
window.__rows = Array.from({length:5}, (_,i)=>['TDF','PBF','PSF','SVC','GEN'][i]).flatMap(kind => ['completed','due','overdue','upcoming','unreachable','declined','invalid_number','unassigned'].map((bucket,i)=>({id:100*['TDF','PBF','PSF','SVC','GEN'].indexOf(kind)+i+1,kind,bucket,customer:kind+' '+bucket,phone:'9000000000',branch:'kochi',caller_name:'Caller',status:bucket==='completed'?'COMPLETED':'OPEN',sales_outcome:'PENDING',lead_status:'QUALIFIED',next_call_at:'2026-10-15T09:00:00Z',original_due_at:'2026-10-15T09:00:00Z',unsuccessful_attempts:0,origin:'AUTOMATIC'})));
const counts = {total:8,completed:1,due:1,overdue:1,upcoming:1,unreachable:1,declined:1,invalid_number:1,unassigned:1,completion_rate:12.5,on_time:0,rated:0};
window.fetch = async (input, options={}) => {
 const url = new URL(typeof input==='string'?input:input.url,location.href);
 if(!url.pathname.includes('/api/')) return originalFetch(input,options);
 let data={};
 if(url.pathname.includes('/auth/')) data={user:{id:1,role:'${role}',email:'admin@example.com',first_name:'Admin',last_name:'User',is_active:true}};
 else if(url.pathname.endsWith('/feedback/options/')) data={branches:['kochi'],callers:[],activated_at:'2026-09-16',complaint_categories:{},complaint_subtypes:{}};
 else if(url.pathname.endsWith('/feedback/summary/')) {window.__summaryRequests++; data={summary:counts,types:['TDF','PBF','PSF','SVC','GEN'].map(kind=>({...counts,kind})),backlog:{due:5,overdue:5,unassigned:5},activity:{attempts:0,customers:0},coverage:{leads_with_feedback:40,all_leads:40},origins:{HISTORICAL:{total:0},MANUAL:{total:0}},satisfaction:[],customers:40,comparisons:[]}; await new Promise(r=>setTimeout(r,500));}
 else if(url.pathname.endsWith('/feedback/')) {window.__feedbackRequests.push(url.search);const kind=url.searchParams.get('kind'),bucket=url.searchParams.get('bucket');const results=window.__rows.filter(r=>(!kind||r.kind===kind)&&(!bucket||r.bucket===bucket));data={count:results.length,results,next:null,previous:null};await new Promise(r=>setTimeout(r,bucket==='completed'?250:20));}
 else if(url.pathname.includes('/notifications')) data={count:0,results:[]};
 return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}});
};`;
await send('Page.enable');
await send('Runtime.enable');
await send('Page.addScriptToEvaluateOnNewDocument',{source:fixture});
await send('Page.navigate',{url:baseURL+(role==='CEO'?'/ceo/feedback':'/feedback')});
await until(`document.querySelectorAll('.feedback-type-card').length===5`);
const summaryRequests = await evaluate('window.__summaryRequests');
for(const kind of ['TDF','PBF','PSF','SVC','GEN']) {
 for(let i=0;i<8;i++) {
  const bucket=['completed','due','overdue','upcoming','unreachable','declined','invalid_number','unassigned'][i];
  await evaluate(`document.querySelector('.feedback-type-card.${kind.toLowerCase()} .feedback-type-counts').children[${i}].click()`);
  await until(`document.querySelector('.feedback-table tbody')?.innerText.includes('${kind} ${bucket}') && document.querySelectorAll('.feedback-table tbody tr').length===1`);
  assert.equal(await evaluate(`new URLSearchParams(location.search).get('bucket')`),bucket);
  assert.equal(await evaluate(`document.querySelector('.feedback-type-card.${kind.toLowerCase()} .feedback-type-counts').children[${i}].getAttribute('aria-pressed')`),'true');
 }
 await evaluate(`document.querySelector('.feedback-type-card.${kind.toLowerCase()} .feedback-type-heading').click()`);
 await until(`document.querySelectorAll('.feedback-table tbody tr').length===8`);
 for (const selector of ['.feedback-completion','.feedback-progress','.feedback-type-total>button:first-child']) {
  await evaluate(`document.querySelector('.feedback-type-card.${kind.toLowerCase()} ${selector}').click()`);
  await until(`document.querySelectorAll('.feedback-table tbody tr').length===${selector.includes('first-child')?8:1}`);
 }
}
for (let i=0;i<3;i++) {
 await evaluate(`document.querySelectorAll('.feedback-backlog>button')[${i}].click()`);
 await until(`document.querySelectorAll('.feedback-table tbody tr').length===5`);
 assert.equal(await evaluate(`new URLSearchParams(location.search).get('backlog')`),'true');
}
await evaluate(`document.querySelector('.tdf .feedback-type-counts').children[0].click()`);
await new Promise(r=>setTimeout(r,30));
await evaluate(`document.querySelector('.pbf .feedback-type-counts').children[2].click()`);
await until(`document.querySelector('.feedback-table tbody')?.innerText.includes('PBF overdue')`);
await new Promise(r=>setTimeout(r,350));
assert.ok(await evaluate(`document.querySelector('.feedback-table tbody').innerText.includes('PBF overdue')`));
assert.equal(await evaluate(`window.__summaryRequests`),summaryRequests);
console.log('PASS ('+role+'): 40 status counts, type headings, totals, completion controls, backlog, selected states, rapid switching, no summary reloads.');
await send('Page.close');
ws.close();
