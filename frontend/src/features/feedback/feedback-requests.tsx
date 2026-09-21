"use client";

import { useEffect, useState, type FormEvent } from "react";
import { api } from "@/lib/crm";
import { formatDateTime } from "@/lib/dates";
import type { FeedbackRequest, HistoricalRecord } from "@/lib/feedback";

type Customer = { id: number; name: string; phone: string; branch: string };
type RequestPage = { results: FeedbackRequest[]; next: string | null; previous: string | null };
const indiaTime = (value: string) => `${value}:00+05:30`;
const errorText = (error: unknown) => error instanceof Error ? error.message : "Unable to save feedback request.";

export function FeedbackRequestForm({ lead, onSaved }: { lead?: { id: number; name: string }; onSaved?: () => void }) {
  const [customer, setCustomer] = useState(lead);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [query, setQuery] = useState("");
  const [reason, setReason] = useState("");
  const [date, setDate] = useState("");
  const [rows, setRows] = useState<FeedbackRequest[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    if (!lead) return;
    const controller = new AbortController();
    api<RequestPage>(`/api/feedback-requests/?lead=${lead.id}`, { signal: controller.signal }).then(data => setRows(data.results)).catch(e => { if (e.name !== "AbortError") setError(e.message); });
    return () => controller.abort();
  }, [lead]);
  useEffect(() => {
    if (lead || query.trim().length < 2) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => { void api<Customer[]>(`/api/feedback-requests/customers/?q=${encodeURIComponent(query)}`, { signal: controller.signal }).then(setCustomers).catch(e => { if (e.name !== "AbortError") setError(e.message); }); }, 250);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [query, lead]);
  const submit = async (event: FormEvent) => {
    event.preventDefault(); if (!customer) return; setBusy(true); setError(""); setNotice("");
    try {
      const row = await api<FeedbackRequest>("/api/feedback-requests/", { method: "POST", body: JSON.stringify({ lead: customer.id, reason, preferred_at: indiaTime(date) }) });
      setRows(previous => [row, ...previous]); setReason(""); setDate(""); setNotice(row.status === "APPROVED" ? "Feedback call scheduled." : "Request sent for manager approval."); onSaved?.();
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };
  return <details className="feedback-request-panel"><summary>Request customer feedback</summary>
    <form onSubmit={submit} className="feedback-request-form">
      {!lead && <><label>Find customer<input aria-label="Find feedback customer" value={query} onChange={e => { setQuery(e.target.value); setCustomer(undefined); setCustomers([]); }} placeholder="Name or phone" /></label><label>Customer<select required value={customer?.id || ""} onChange={e => setCustomer(customers.find(c => c.id === Number(e.target.value)))}><option value="">Choose customer</option>{customers.map(c => <option key={c.id} value={c.id}>{c.name} · {c.phone} · {c.branch}</option>)}</select></label></>}
      <label>Reason for feedback<textarea required maxLength={5000} value={reason} onChange={e => setReason(e.target.value)} /></label>
      <label>Preferred call time · India time<input type="datetime-local" required value={date} onChange={e => setDate(e.target.value)} /></label>
      <button className="button primary" disabled={busy || !customer}>{busy ? "Saving…" : "Request feedback"}</button>
    </form>
    {error && <p className="feedback-error" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {lead && rows.map(row => <article key={row.id}><b>{row.status.toLowerCase()} · {formatDateTime(row.preferred_at)}</b><p>{row.reason}</p>{row.review_notes && <p>{row.reviewer}: {row.review_notes}</p>}</article>)}
  </details>;
}

function ReviewRequest({ row, changed }: { row: FeedbackRequest; changed: () => void }) {
  const [notes, setNotes] = useState("");
  const [date, setDate] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const review = async (decision: string) => {
    setBusy(true); setError("");
    try { await api(`/api/feedback-requests/${row.id}/review/`, { method: "POST", body: JSON.stringify({ revision: row.revision, decision, review_notes: notes, ...(date ? { preferred_at: indiaTime(date) } : {}) }) }); changed(); }
    catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };
  return <article className="feedback-request-review"><h3>{row.customer} · {row.branch}</h3><p>{row.reason}</p><small>{row.requester} · Requested {formatDateTime(row.preferred_at)}</small>
    <label>Review notes · required to reject<textarea maxLength={5000} value={notes} onChange={e => setNotes(e.target.value)} /></label>
    <label>Change call time · India time<input type="datetime-local" value={date} onChange={e => setDate(e.target.value)} /></label>
    <div className="feedback-actions"><button className="filter" disabled={busy} onClick={() => void review("APPROVED")}>Approve request</button><button className="filter" disabled={busy || !notes.trim()} onClick={() => void review("REJECTED")}>Reject request</button></div>
    {error && <p role="alert" className="feedback-error">{error}</p>}
  </article>;
}

export function FeedbackManagement({ admin, changed, version }: { admin: boolean; changed: () => void; version: number }) {
  const [page, setPage] = useState(1);
  const [requests, setRequests] = useState<RequestPage | null>(null);
  const [history, setHistory] = useState<HistoricalRecord[] | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [date, setDate] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    api<RequestPage>(`/api/feedback-requests/?status=PENDING&page=${page}`, { signal: controller.signal }).then(setRequests).catch(e => { if (e.name !== "AbortError") setError(e.message); });
    return () => controller.abort();
  }, [version, page]);
  const preview = async () => {
    setBusy(true); setError(""); setNotice("");
    try { setHistory(await api<HistoricalRecord[]>("/api/feedback/historical-preview/")); setSelected([]); } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };
  const importHistory = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError("");
    try { await api("/api/feedback/historical-import/", { method: "POST", body: JSON.stringify({ records: selected, next_call_at: indiaTime(date) }) }); setHistory(null); setSelected([]); setNotice("Selected historical calls scheduled."); changed(); }
    catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };
  return <section className="panel feedback-management"><h2>Feedback requests</h2><FeedbackRequestForm onSaved={changed} />
    <details><summary>Pending approvals ({requests?.results.length ?? 0} on this page)</summary>{requests?.results.map(row => <ReviewRequest key={row.id} row={row} changed={changed} />)}{!requests?.results.length && <p>No requests awaiting approval.</p>}
      <div className="feedback-actions"><button className="filter" disabled={!requests?.previous} onClick={() => setPage(p => p - 1)}>Previous requests</button><button className="filter" disabled={!requests?.next} onClick={() => setPage(p => p + 1)}>Next requests</button></div>
    </details>
    {admin && <details className="feedback-historical"><summary>Historical catch-up · last 30 days</summary><p>Preview verified events, then select customers to call. Original dates are preserved and these calls are reported separately.</p><button className="filter" disabled={busy} onClick={() => void preview()}>Preview historical events</button>
      {history && <form onSubmit={importHistory}><div className="feedback-table-scroll"><table className="feedback-table"><thead><tr><th>Select</th><th>Customer / event</th><th>Branch / proposed caller</th><th>Original dates</th><th>Eligibility</th></tr></thead><tbody>{history.map(row => <tr key={row.key}><td><input type="checkbox" aria-label={`Select ${row.customer} ${row.kind}`} disabled={!!row.exclusion_reason} checked={selected.includes(row.key)} onChange={e => setSelected(items => e.target.checked ? [...items, row.key] : items.filter(key => key !== row.key))} /></td><td>{row.customer}<small>{row.kind}</small></td><td>{row.branch || "No branch"}<small>{row.proposed_caller?.name || row.unassigned_reason || "—"}</small></td><td>{formatDateTime(row.occurred_at)}<small>Due: {formatDateTime(row.original_due_at)}</small></td><td>{row.exclusion_reason || "Eligible"}</td></tr>)}</tbody></table></div>{!history.length && <p>No verified events in the last 30 days.</p>}<label>Calling date and time · India time<input type="datetime-local" required value={date} onChange={e => setDate(e.target.value)} /></label><button className="button primary" disabled={busy || !selected.length || selected.length > 200}>Schedule {selected.length} selected calls</button></form>}
    </details>}
    {error && <p role="alert" className="feedback-error">{error}</p>}{notice && <p role="status">{notice}</p>}
  </section>;
}
