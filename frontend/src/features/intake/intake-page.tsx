'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { api, getSystemConfig } from '@/lib/crm';
import { formatDateTime } from '@/lib/dates';
import { customerFields, fetchMetaLeads, getIntakeHealth, getMappings, getReceipt, getReceipts, intakeStates, reprocessMapping, resolveReceipt, type CustomerValues, type Entry, type IntakeConnection, type IntakeHealth, type IntakeReceipt, type Mapping, type ReceiptDetail } from '@/lib/intake';
import { MappingEditor } from './mapping-editor';

const terminal = ['IMPORTED', 'LINKED', 'DISMISSED'];
const displayTime = (value: string | null | undefined) => value ? formatDateTime(value) : 'Not yet';
const emptyEntries: Entry[] = [];

export function IntakePage() {
  const [checkedAt, setCheckedAt] = useState(0);
  const [tab, setTab] = useState<'receipts' | 'connections' | 'mappings'>('receipts');
  const [filters, setFilters] = useState({ origin: '', form: '', state: 'NEEDS_REVIEW', reason: '', date_from: '', date_to: '' });
  const [page, setPage] = useState(1);
  const [receipts, setReceipts] = useState<IntakeReceipt[]>([]);
  const [count, setCount] = useState(0);
  const [health, setHealth] = useState<IntakeHealth | null>(null);
  const [mappings, setMappings] = useState<Mapping[]>([]);
  const [mappingReceipt, setMappingReceipt] = useState<IntakeReceipt | null>(null);
  const [detail, setDetail] = useState<ReceiptDetail | null>(null);
  const [dirty, setDirty] = useState(false);
  const [corrections, setCorrections] = useState<CustomerValues>({});
  const [linkId, setLinkId] = useState('');
  const [mappingForm, setMappingForm] = useState('');
  const [mappingVersion, setMappingVersion] = useState('');
  const [sample, setSample] = useState<Entry[]>(emptyEntries);
  const [sampleText, setSampleText] = useState('[{"id":"Full Name","label":"Full Name","value":"Sample Customer"},{"id":"Mobile","label":"Mobile","value":"9876543210"}]');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [sources, setSources] = useState<string[]>([]);
  const [connectionDraft, setConnectionDraft] = useState({ name: '', origin: 'WEBSITE', source: '', secret_ref: '', activated_at: '' });
  const [formDraft, setFormDraft] = useState({ connection: '', name: '', external_id: '', page_id: '', activated_at: '' });
  const generation = useRef(0);
  const refresh = useCallback(async () => {
    const request = ++generation.current;
    const params = new URLSearchParams({ page: String(page) });
    Object.entries(filters).forEach(([k, v]) => { if (v) params.set(k, v); });
    try {
      const [list, status, versions] = await Promise.all([getReceipts(params), getIntakeHealth(), getMappings()]);
      if (request !== generation.current) return;
      setCheckedAt(Date.now()); setReceipts(list.results); setCount(list.count); setHealth(status); setMappings(versions);
    } catch (e) { if (request === generation.current) setError(e instanceof Error ? e.message : 'Unable to load intake.'); }
  }, [filters, page]);
  useEffect(() => {
    const initial = window.setTimeout(() => void refresh(), 0);
    const tick = () => { if (document.visibilityState === 'visible') void refresh(); };
    const timer = window.setInterval(tick, 30_000);
    document.addEventListener('visibilitychange', tick);
    return () => { window.clearTimeout(initial); window.clearInterval(timer); document.removeEventListener('visibilitychange', tick); };
  }, [refresh]);
  useEffect(() => { void getSystemConfig().then(config => setSources(config.lists.sources || [])).catch(() => {}); }, []);
  const run = async (work: () => Promise<void>) => {
    setBusy(true); setError(''); setNotice('');
    try { await work(); await refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Action failed.'); }
    finally { setBusy(false); }
  };
  const open = (id: string) => void run(async () => { const receipt = await getReceipt(id); setDetail(receipt); setCorrections(receipt.mapped_values); setDirty(false); setLinkId(''); });
  const resolve = (action: 'correct' | 'link' | 'create_separately' | 'dismiss' | 'retry') => detail && void run(async () => {
    const next = await resolveReceipt(detail.id, action, action === 'correct' ? corrections : undefined, action === 'link' ? Number(linkId) : undefined);
    setDetail(next); setDirty(false); setCorrections(next.mapped_values); setNotice(`Receipt ${next.state.toLowerCase().replaceAll('_', ' ')}.`);
  });
  useEffect(() => {
    if (!detail) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    const dialog = document.querySelector<HTMLElement>('.intake-dialog');
    dialog?.querySelector<HTMLButtonElement>('button')?.focus();
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setDetail(null);
      if (event.key !== 'Tab' || !dialog) return;
      const controls = Array.from(dialog.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea, a[href], summary')).filter(e => e.offsetParent !== null);
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener('keydown', keyboard);
    return () => { document.removeEventListener('keydown', keyboard); previousFocus?.focus(); };
  // Preserve focus while polling this receipt or editing a field.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail?.id]);
  useEffect(() => {
    if (!detail || dirty || busy) return;
    const id = detail.id;
    let alive = true;
    const tick = () => {
      if (document.visibilityState !== 'visible') return;
      void getReceipt(id).then(next => { if (alive) { setDetail(next); setCorrections(next.mapped_values); } }).catch(() => {});
    };
    const timer = window.setInterval(tick, 30_000);
    document.addEventListener('visibilitychange', tick);
    return () => { alive = false; window.clearInterval(timer); document.removeEventListener('visibilitychange', tick); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail?.id, dirty, busy]);
  const forms = health?.connections.flatMap(c => c.forms) || [];
  const scopedMappings = mappings.filter(m => m.form === Number(mappingForm));
  const activeMapping = mappings.find(m => m.id === Number(mappingVersion)) || scopedMappings[0];
  const heartbeat = (name: string) => {
    const value = health?.heartbeats[name];
    return value ? `${checkedAt - new Date(value).getTime() < 120_000 ? 'Healthy' : 'Stale'} · ${displayTime(value)}` : 'No heartbeat received';
  };
  return <div className="page intake-page">
    <div className="intake-heading"><div><p className="eyebrow">LEAD CONTROL</p><h1>Lead Intake</h1><p className="subtext">Review incoming enquiries, manage form mappings, and monitor delivery. Imported leads enter the assignment pool.</p></div><Link className="button" href="/leads">Open assignment pool</Link></div>
    <div className="intake-actions" role="tablist" aria-label="Intake sections">{(['receipts', 'connections', 'mappings'] as const).map(value => <button role="tab" aria-selected={tab === value} className={`button ${tab === value ? 'primary' : ''}`} key={value} onClick={() => setTab(value)}>{value[0].toUpperCase() + value.slice(1)}</button>)}</div>
    {error && <p role="alert" className="intake-error">{error}</p>}{notice && <p role="status" className="intake-success">{notice}</p>}
    {health && !health.enabled && <p className="intake-banner">Integration acceptance and processing are disabled in the backend environment. Configuration and review remain available.</p>}
    {health?.execution_mode === 'database' && health.processor_delayed && <p role="alert" className="intake-banner">{health.last_processor_success_at ? 'No successful processor run in the last 15 minutes.' : 'No successful processor run recorded yet.'} Imports and reminders may be delayed. Ask your operator to check the scheduled processor.</p>}
    {tab === 'receipts' && <>
      <section className="panel intake-panel"><div className="intake-filters">
        <label>Origin<select value={filters.origin} onChange={e => { setPage(1); setFilters({ ...filters, origin: e.target.value }); }}><option value="">All origins</option><option>META</option><option>WEBSITE</option></select></label>
        <label>Form<select value={filters.form} onChange={e => { setPage(1); setFilters({ ...filters, form: e.target.value }); }}><option value="">All forms</option>{forms.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}</select></label>
        <label>State<select value={filters.state} onChange={e => { setPage(1); setFilters({ ...filters, state: e.target.value }); }}><option value="">All states</option>{intakeStates.map(s => <option key={s}>{s}</option>)}</select></label>
        <label>Review reason<select value={filters.reason} onChange={e => { setPage(1); setFilters({ ...filters, reason: e.target.value }); }}><option value="">All reasons</option>{['validation', 'existing_lead', 'pending_submission', 'connection', 'processing', 'expired', 'retry_exhausted'].map(s => <option key={s}>{s}</option>)}</select></label>
        <label>From<input type="date" value={filters.date_from} onChange={e => { setPage(1); setFilters({ ...filters, date_from: e.target.value }); }} /></label><label>To<input type="date" value={filters.date_to} onChange={e => { setPage(1); setFilters({ ...filters, date_to: e.target.value }); }} /></label>
      </div><div className="intake-table-wrap"><table><thead><tr><th>Customer</th><th>Origin / form</th><th>State</th><th>Received</th><th>Action</th></tr></thead><tbody>{receipts.map(r => <tr key={r.id}>
        <td><b>{r.mapped_values.name || 'Needs mapping'}</b><small>{r.mapped_values.phone || 'Phone unavailable'}</small></td><td>{r.origin}<small>{r.form_name}</small></td><td><span className={`intake-state ${r.state.toLowerCase()}`}>{r.state.replaceAll('_', ' ')}</span><small>{r.review_reason.replaceAll('_', ' ')}</small></td><td>{displayTime(r.received_at)}</td><td><button className="button" disabled={busy} onClick={() => open(r.id)}>{r.state === 'NEEDS_REVIEW' || r.state === 'FAILED' ? 'Review' : 'View details'}</button></td>
      </tr>)}</tbody></table>{!receipts.length && <p className="intake-empty">{filters.state === 'NEEDS_REVIEW' ? 'No receipts need review for these filters.' : 'No receipts match these filters.'}</p>}</div>
      <div className="intake-actions"><span>{count} receipts · Page {page}</span><button className="button" disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</button><button className="button" disabled={page * 50 >= count} onClick={() => setPage(page + 1)}>Next</button></div></section>
    </>}
    {tab === 'connections' && <>
      <section className="panel intake-panel"><h2>Delivery health</h2>{health?.execution_mode === 'database' ? <><p>Last processor attempt: {displayTime(health.last_processor_attempt_at)}</p><p>Last successful run: {displayTime(health.last_processor_success_at)}</p><p>Automatic Meta checks about every {Math.ceil(health.meta_scan_interval_seconds / 60)} minutes.</p><p>Webhook receipts and uploads processed about every 5 minutes.</p><p className="subtext">Valid enquiries become Fresh, unassigned leads. Duplicates and incomplete enquiries stay in Receipts for review. Request recovery is optional and queues a scan for the next processor run. Large scans can take several runs.</p></> : <><p>Worker: {heartbeat('worker')}</p><p>Scheduler: {heartbeat('scheduler')}</p><p className="subtext">Meta sends new enquiries automatically. The background worker imports them into ITS; missed deliveries are checked every 15 minutes. Valid new leads appear in the assignment pool. Duplicate or incomplete enquiries stay in Receipts for review.</p></>}
      {health?.connections.map(c => <article className="intake-connection" key={c.id}><div className="intake-heading"><div><h3>{c.name} · {c.origin}</h3><p>{c.enabled ? 'Enabled' : 'Disabled'} · Source: {c.source} · Credentials {c.credentials_ready ? 'configured (access not verified here)' : 'missing'}</p></div><button className="button" disabled={busy} onClick={() => void run(async () => { await api(`/api/intake/connections/${c.id}/`, { method: 'PATCH', body: JSON.stringify({ enabled: !c.enabled }) }); })}>{c.enabled ? 'Disable connection' : 'Enable connection'}</button></div>
        <p>Latest receipt: {displayTime(c.last_receipt_at)} · Latest import: {displayTime(c.last_import_at)}</p><p>Oldest backlog: {Math.floor(c.backlog_age_seconds / 60)} minutes · Failed: {c.counts.FAILED || 0} · Needs review: {c.counts.NEEDS_REVIEW || 0}</p>
        {c.paused_reason && <p className="intake-error">Processing paused: {c.paused_reason} <button className="button" disabled={busy} onClick={() => void run(async () => { await api(`/api/intake/connections/${c.id}/resume/`, { method: 'POST' }); })}>Resume after credentials are corrected</button></p>}
        <label>ITS source<select value={c.source} disabled={busy} onChange={e => void run(async () => { await api(`/api/intake/connections/${c.id}/`, { method: 'PATCH', body: JSON.stringify({ source: e.target.value }) }); })}>{sources.map(s => <option key={s}>{s}</option>)}</select></label>
        {c.forms.map(f => <div className="intake-form-line" key={f.id}><div><b>{f.name}</b><small>{f.page_id ? `Page ${f.page_id} · ` : ''}Form {f.external_id}</small><small>Active from {displayTime(f.activated_at)} · Last successful form scan {displayTime(f.last_reconciled_at)}</small>{c.origin === 'META' && health?.execution_mode === 'database' && <small role="status">Scan: {f.fetch_status}{f.fetch_requested_at ? ` · Requested ${displayTime(f.fetch_requested_at)}` : ''}</small>}{c.origin === 'META' && f.scan_delayed && <small role="alert" className="intake-error">Meta scan delayed: no successful scan in the last {Math.ceil(health.meta_scan_stale_after_seconds / 60)} minutes.</small>}{f.reconcile_error && <small className="intake-error">Scan failed: {f.reconcile_error}. Temporary failures retry automatically. For access errors, ask your operator to verify the token and lead permissions, then resume the connection.</small>}</div><div className="intake-actions">{c.origin === 'META' && health?.execution_mode === 'database' && <button className="button primary" disabled={busy || !health.enabled || !c.enabled || !f.enabled || !c.credentials_ready || !!c.paused_reason || ['queued', 'running'].includes(f.fetch_status)} onClick={() => void run(async () => { await fetchMetaLeads(f.id); setNotice(`Recovery queued for ${f.name}. It will start on the next processor run; larger imports may take several runs.`); })}>{f.fetch_status === 'queued' ? 'Recovery queued' : f.fetch_status === 'running' ? 'Scanning…' : 'Request recovery'}</button>}<button className="button" disabled={busy} onClick={() => void run(async () => { await api(`/api/intake/forms/${f.id}/`, { method: 'PATCH', body: JSON.stringify({ enabled: !f.enabled }) }); })}>{f.enabled ? 'Disable form' : 'Enable form'}</button></div></div>)}
      </article>)}</section>
      <section className="panel intake-panel"><h2>Add a connection</h2><p className="subtext">Your operator supplies the secret reference from the backend environment. Credentials are never shown here. Connections and forms start disabled.</p><form onSubmit={e => { e.preventDefault(); void run(async () => { await api<IntakeConnection>('/api/intake/connections/', { method: 'POST', body: JSON.stringify({ ...connectionDraft, activated_at: new Date(connectionDraft.activated_at).toISOString() }) }); setNotice('Connection created. Add the selected forms below.'); }); }}><div className="intake-grid">
        <label>Name<input required value={connectionDraft.name} onChange={e => setConnectionDraft({ ...connectionDraft, name: e.target.value })} /></label><label>Origin<select value={connectionDraft.origin} onChange={e => setConnectionDraft({ ...connectionDraft, origin: e.target.value })}><option>WEBSITE</option><option>META</option></select></label><label>Source<select required value={connectionDraft.source} onChange={e => setConnectionDraft({ ...connectionDraft, source: e.target.value })}><option value="">Choose source</option>{sources.map(s => <option key={s}>{s}</option>)}</select></label><label>Secret reference<input required value={connectionDraft.secret_ref} onChange={e => setConnectionDraft({ ...connectionDraft, secret_ref: e.target.value })} /></label><label>Activation time<input required type="datetime-local" value={connectionDraft.activated_at} onChange={e => setConnectionDraft({ ...connectionDraft, activated_at: e.target.value })} /></label></div><button className="button primary" disabled={busy}>Create disabled connection</button></form></section>
      <section className="panel intake-panel"><h2>Add a selected form</h2><form onSubmit={e => { e.preventDefault(); void run(async () => { await api('/api/intake/forms/', { method: 'POST', body: JSON.stringify({ ...formDraft, connection: Number(formDraft.connection), activated_at: new Date(formDraft.activated_at).toISOString() }) }); setNotice('Form created. Configure its mapping before enabling it.'); }); }}><div className="intake-grid"><label>Connection<select required value={formDraft.connection} onChange={e => setFormDraft({ ...formDraft, connection: e.target.value })}><option value="">Choose connection</option>{health?.connections.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>{(['name', 'external_id', 'page_id', 'activated_at'] as const).map(key => <label key={key}>{key.replaceAll('_', ' ')}<input required={key !== 'page_id'} type={key === 'activated_at' ? 'datetime-local' : 'text'} value={formDraft[key]} onChange={e => setFormDraft({ ...formDraft, [key]: e.target.value })} /></label>)}</div><button className="button primary" disabled={busy}>Create disabled form</button></form></section>
    </>}
    {tab === 'mappings' && <section className="panel intake-panel"><h2>Field mappings</h2><div className="intake-grid"><label>Mapping scope<select value={mappingForm} onChange={e => { setMappingForm(e.target.value); setMappingVersion(''); }}><option value="">Choose a form</option>{forms.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}</select></label><label>Version history<select value={activeMapping?.id || ''} onChange={e => setMappingVersion(e.target.value)}><option value="">New mapping</option>{scopedMappings.map(m => <option key={m.id} value={m.id}>{m.template_name || 'Form mapping'} · v{m.version} · {displayTime(m.created_at)}</option>)}</select></label></div>
      <details><summary>Enter sample fields</summary><label>Sample entries (JSON)<textarea rows={5} value={sampleText} onChange={e => setSampleText(e.target.value)} /></label><button className="button" onClick={() => { try { const value = JSON.parse(sampleText); if (!Array.isArray(value)) throw new Error('Use a list of entries.'); setSample(value); } catch { setError('Use a JSON list of id, label and value entries.'); } }}>Use sample</button></details>
      {mappingForm && <MappingEditor key={`${mappingForm}:${activeMapping?.id || 'new'}`} entries={sample} form={Number(mappingForm)} mapping={activeMapping} onSaved={m => { setMappingVersion(String(m.id)); setNotice(`Mapping version ${m.version} saved.`); void refresh(); }} />}
      {mappingReceipt && activeMapping?.form === mappingReceipt.form && <div className="intake-actions"><span>{mappingReceipt.mapped_values.name || 'Enquiry'} · {mappingReceipt.mapped_values.phone || 'Phone unavailable'}</span><button className="button" disabled={busy} onClick={() => void run(async () => { const result = await reprocessMapping(activeMapping.id, [mappingReceipt.id]); setNotice(result.queued ? `Enquiry queued with mapping version ${activeMapping.version}.` : 'Enquiry was not queued because it is already resolved, expired, or processing.'); setMappingReceipt(null); })}>Reprocess this enquiry</button></div>}
    </section>}
    {detail && <div className="intake-overlay" onClick={() => setDetail(null)}><section className="panel intake-dialog" role="dialog" aria-modal="true" aria-labelledby="receipt-title" onClick={e => e.stopPropagation()}><div className="intake-heading"><div><h2 id="receipt-title">{detail.mapped_values.name || 'Review enquiry'}</h2><small>{detail.id}</small><p>{detail.state.replaceAll('_', ' ')} · {detail.form_name}</p></div><button className="button" onClick={() => setDetail(null)}>Close</button></div>
      {error && <p role="alert" className="intake-error">{error}</p>}{notice && <p role="status" className="intake-success">{notice}</p>}
      <p>Submitted: {displayTime(detail.submitted_at)} · Received: {displayTime(detail.received_at)} · Mapping: {detail.mapping_version || 'automatic'}</p>
      {detail.state === 'IMPORTED' && <p className="intake-success">This enquiry has been imported into ITS. No review is needed.</p>}
      {Object.entries(detail.errors).map(([k, v]) => <p key={k} className="intake-error">{k}: {v}</p>)}
      {detail.lead && <p>Related lead: <Link href={`/all-leads?q=${encodeURIComponent(detail.mapped_values.phone || '')}`}>Lead #{detail.lead}</Link></p>}
      <div className="intake-grid">{customerFields.map(field => <label key={field}>{field.replaceAll('_', ' ')}<input type={field === 'enquiry_date' ? 'date' : 'text'} disabled={terminal.includes(detail.state)} value={corrections[field] || ''} onChange={e => { setDirty(true); setCorrections({ ...corrections, [field]: e.target.value || (field === 'enquiry_date' ? null : '') }); }} /></label>)}</div>
      {!terminal.includes(detail.state) && <><div className="intake-actions"><button className="button primary" disabled={busy || detail.state === 'PROCESSING'} onClick={() => resolve('correct')}>Save corrections and reprocess</button><button className="button" disabled={busy || detail.answers_expired} onClick={() => resolve('retry')}>Retry</button><button className="button" disabled={busy} onClick={() => resolve('dismiss')}>Dismiss enquiry</button></div>
        <h3>Duplicate review</h3>{detail.matching_leads.map(l => <p key={l.id}>#{l.id} · {l.name} · {l.phone} · {l.status} · CE {l.assigned_so || 'unassigned'}</p>)}{detail.pending_receipts.map(r => <p key={r.id}>Pending receipt {r.id} · {r.state} · {displayTime(r.received_at)}</p>)}
        <div className="intake-actions"><label>Existing lead ID<input type="number" min="1" value={linkId} onChange={e => setLinkId(e.target.value)} /></label><button className="button" disabled={busy || !linkId} onClick={() => resolve('link')}>Link to existing lead</button><button className="button" disabled={busy || detail.answers_expired || Object.keys(detail.errors).some(k => k !== 'duplicate')} onClick={() => resolve('create_separately')}>Create separately as duplicate</button></div>
        <button className="button" onClick={() => { setMappingReceipt(detail); setSample(detail.answers); setMappingForm(String(detail.form)); setMappingVersion(detail.mapping_version ? String(detail.mapping_version) : ''); setDetail(null); setTab('mappings'); }}>Map this form’s answers</button>
      </>}
      <details><summary>Incoming answers and attribution</summary>{detail.answers.map(e => <p key={e.id}>{e.label}: {String(e.value ?? '')}</p>)}<p>Ignored labels: {detail.ignored_labels.join(', ') || 'None'}</p>{Object.entries(detail.attribution).map(([k, v]) => <p key={k}>{k}: {v}</p>)}{detail.campaign_name && <p>Campaign: {detail.campaign_name}</p>}</details>
      <h3>Activity history</h3>{detail.history.map(event => <p key={event.id}>{event.action.replaceAll('_', ' ')} · {event.actor_name} · {displayTime(event.created_at)}</p>)}
    </section></div>}
  </div>;
}
