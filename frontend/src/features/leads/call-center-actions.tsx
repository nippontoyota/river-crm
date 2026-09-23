"use client";

import { useEffect, useRef, useState } from "react";
import { getCallbacks, getInteractions, recordInteraction, kindName, stateName, type CallbackTask, type Interaction } from "@/lib/call-center";
import { formatDateTime } from "@/lib/dates";
import type { Page } from "@/lib/service";

export function useSubmission() {
  const attempt = useRef({ signature: "", id: "" });
  return (values: Record<string, unknown>) => {
    const signature = JSON.stringify(values);
    if (signature !== attempt.current.signature) attempt.current = { signature, id: crypto.randomUUID() };
    return { ...values, submission_id: attempt.current.id };
  };
}

export function CallCenterPagination({ result, page, onPage }: { result: { count: number; next: string | null; previous: string | null }; page: number; onPage: (page: number) => void }) {
  return <nav className="lead-pagination" aria-label="Result pages"><span>{result.count} records · Page {page}</span><div><button className="filter" type="button" disabled={!result.previous} onClick={() => onPage(page - 1)}>Previous</button><button className="filter" type="button" disabled={!result.next} onClick={() => onPage(page + 1)}>Next</button></div></nav>;
}

export function CallbackAction({ task, leadVersion, onSaved, onCancel, shared = false }: { shared?: boolean; task: CallbackTask; leadVersion: string; onSaved: () => void; onCancel: () => void }) {
  const [mode, setMode] = useState("CALLBACK_COMPLETE");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submission = useSubmission();
  return <form className="sales-form-card call-center-form" onSubmit={async event => {
    event.preventDefault(); if (busy) return;
    const fields = new FormData(event.currentTarget);
    setBusy(true); setError("");
    try {
      await recordInteraction(submission({ kind: mode, lead_id: task.lead_id, lead_version: leadVersion, confirm_customer: true, follow_up_id: task.id, follow_up_version: task.version, notes: String(fields.get("notes")), ...(mode === "CALLBACK_RESCHEDULE" ? { callback_at: new Date(`${fields.get("callback_at")}:00+05:30`).toISOString() } : {}) }), !shared);
      onSaved();
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to update callback."); }
    finally { setBusy(false); }
  }}><h3>Callback for {task.customer}</h3><p><strong>Task owner:</strong> {task.owner_name}</p>
    <label>Action<select value={mode} onChange={e => setMode(e.target.value)}><option value="CALLBACK_COMPLETE">Mark completed</option><option value="CALLBACK_RESCHEDULE">Reschedule this callback</option></select></label>
    {mode === "CALLBACK_RESCHEDULE" && <label>New callback time (IST)<input name="callback_at" type="datetime-local" required /></label>}
    <label>Remarks<textarea name="notes" required maxLength={10000} /></label>
    {error && <p role="alert" className="form-error">{error}</p>}
    <footer><button type="button" className="filter" onClick={onCancel}>Cancel</button><button className="button primary" disabled={busy}>{busy ? "Saving…" : "Save callback"}</button></footer>
  </form>;
}

export function InboundCallbacks({ all = false }: { all?: boolean }) {
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<Page<CallbackTask> | null>(null);
  const [active, setActive] = useState<CallbackTask | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let current = true;
    getCallbacks(page).then(data => { if (current) { setResult(data); setError(""); } }).catch(e => { if (current) setError(e.message); });
    return () => { current = false; };
  }, [page, revision]);
  return <section className="panel call-center-callbacks"><header className="call-center-heading"><div><h2>{all ? "All inbound callbacks" : "Inbound callbacks assigned to you"}</h2><p className="subtext">These tasks remain visible regardless of sales status.</p></div><button className="filter" onClick={() => setRevision(v => v + 1)}>Refresh callbacks</button></header>
    {error && <p className="form-error" role="alert">{error}</p>}
    {!result && !error && <p role="status">Loading callbacks…</p>}
    {result?.results.map(task => <article className="call-center-task" key={task.id}><div><strong>{task.customer}</strong><p>{task.phone} · Lead #{task.lead_id}</p><p><strong>Callback:</strong> {formatDateTime(task.scheduled_for)} · {task.owner_name}{task.reminder_held ? " · Reminder held for admin review" : ""}</p>{task.notes?.map((note, i) => <p key={i}>{note}</p>)}</div><button className="filter" onClick={() => setActive(task)}>Update callback</button></article>)}
    {result && !result.count && <p>{all ? "No open inbound callbacks." : "No inbound callbacks assigned to you."}</p>}
    {active && <CallbackAction key={active.id} task={active} leadVersion={active.lead_version} onCancel={() => setActive(null)} onSaved={() => { setActive(null); setRevision(v => v + 1); }} />}
    {result && <CallCenterPagination result={result} page={page} onPage={value => { setResult(null); setPage(value); }} />}
  </section>;
}

export function InteractionHistory({ leadId, pending = false, refresh = 0, onReview }: { leadId?: number; pending?: boolean; refresh?: number; onReview?: (row: Interaction) => void }) {
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<Page<Interaction> | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let current = true;
    const params = new URLSearchParams({ page: String(page), ...(leadId ? { lead: String(leadId) } : {}), ...(pending ? { pending: "true" } : {}) });
    getInteractions(`?${params}`).then(data => { if (current) { setResult(data); setError(""); } }).catch(e => { if (current) setError(e instanceof Error ? e.message : "Unable to load history."); });
    return () => { current = false; };
  }, [leadId, page, pending, refresh, retry]);
  return <section className="sales-info-card"><h3>{pending ? "Unmatched enquiries & routing exceptions" : "Inbound history & shared updates"}</h3>
    {error && <p role="alert" className="form-error">{error} <button className="filter" onClick={() => { setError(""); setResult(null); setRetry(v => v + 1); }}>Retry</button></p>}
    {!result && !error && <p role="status">Loading history…</p>}
    {result?.results.map(row => <article className="call-center-history" key={row.id}><h4>{kindName(row.kind)} · {row.customer || "Unmatched caller"}</h4><p><strong>Handled by:</strong> {row.handled_by_name} · {formatDateTime(row.created_at)}</p><p><strong>State:</strong> {stateName(row.state)}{row.lead_id ? ` · Lead #${row.lead_id}` : ""}</p>{row.caller_phone && <p><strong>Caller phone:</strong> {row.caller_phone}</p>}{row.reason && <p><strong>Reason:</strong> {row.reason}</p>}<p className="call-center-notes">{row.notes}</p>{row.complaint_id && <p>Complaint reference: #{row.complaint_id}</p>}{row.service_request_id && <p>Service reference: #{row.service_request_id}</p>}{onReview && <button className="filter" onClick={() => onReview(row)}>Review enquiry</button>}</article>)}
    {result && !result.count && <p>{pending ? "No enquiries awaiting review." : "No inbound history recorded."}</p>}
    {result && <CallCenterPagination result={result} page={page} onPage={value => { setResult(null); setPage(value); }} />}
  </section>;
}
