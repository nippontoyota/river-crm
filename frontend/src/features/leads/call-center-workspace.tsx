"use client";

import { useEffect, useRef, useState } from "react";
import { getSystemConfig, type CurrentUser, type SystemConfig } from "@/lib/crm";
import { formatDateTime } from "@/lib/dates";
import { getCallSummary, getSharedLead, getSharedTickets, stateName, type CallbackTask, type Interaction, type SharedComplaint, type SharedDetail, type SharedService } from "@/lib/call-center";
import type { Page } from "@/lib/service";
import { CustomerLookup } from "./customer-lookup";
import { LeadOwnershipPanel } from "./lead-ownership";
import { CallbackAction, CallCenterPagination, InboundCallbacks, InteractionHistory } from "./call-center-actions";
import { InboundForm, ReviewEnquiry, SharedLeadEditor, type InboundAction } from "./call-center-forms";

export function CallCenterWorkspace({ user }: { user: CurrentUser }) {
  const [lead, setLead] = useState<SharedDetail | null>(null);
  const [lookup, setLookup] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [configError, setConfigError] = useState("");
  const [action, setAction] = useState<InboundAction | null>(null);
  const [editing, setEditing] = useState(false);
  const [task, setTask] = useState<CallbackTask | null>(null);
  const [review, setReview] = useState<Interaction | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [summary, setSummary] = useState<Awaited<ReturnType<typeof getCallSummary>> | null>(null);
  const request = useRef(0);
  const isAdmin = user.role === "ADMIN";
  const handler = `${user.first_name} ${user.last_name}`.trim() || user.email;

  const loadConfig = () => { setConfigError(""); void getSystemConfig().then(setConfig).catch(e => setConfigError(e.message)); };
  useEffect(() => {
    let current = true;
    getSystemConfig().then(data => { if (current) setConfig(data); }).catch(e => { if (current) setConfigError(e.message); });
    return () => { current = false; };
  }, []);
  useEffect(() => {
    let current = true;
    getCallSummary().then(data => { if (current) setSummary(data); }).catch(e => { if (current) setError(e.message); });
    return () => { current = false; };
  }, [refresh]);
  const open = async (id: number, preserveDraft = false) => {
    const current = ++request.current;
    setLoading(true); setError("");
    if (!preserveDraft) { setLead(null); setAction(null); setEditing(false); setTask(null); }
    try { const data = await getSharedLead(id); if (current === request.current) setLead(data); }
    catch (e) { if (current === request.current) setError(e instanceof Error ? e.message : "Unable to open customer."); }
    finally { if (current === request.current) setLoading(false); }
  };
  useEffect(() => {
    let current = true;
    const id = Number(new URLSearchParams(window.location.search).get("lead"));
    const initialRequest = request.current;
    if (id > 0) getSharedLead(id).then(data => { if (current && request.current === initialRequest) setLead(data); }).catch(e => { if (current && request.current === initialRequest) setError(e.message); });
    return () => { current = false; };
  }, []);
  const refreshRecord = async () => {
    if (!lead) return;
    const selected = action;
    const expected = request.current + 1;
    await open(lead.id, true);
    if (request.current !== expected) return;
    setRefresh(v => v + 1);
    if (selected && typeof selected !== "string") {
      try {
        const data = await getSharedTickets(lead.id, selected.kind === "COMPLAINT_NOTE" ? "complaint" : "service", 1, selected.ticket.id);
        if (request.current !== expected) return;
        if (!data.results.length) throw new Error("This ticket no longer matches the selected customer. Review the enquiry before continuing.");
        const updated: InboundAction = selected.kind === "COMPLAINT_NOTE" ? { kind: selected.kind, ticket: data.results[0] as SharedComplaint } : { kind: selected.kind, ticket: data.results[0] as SharedService };
        setAction(current => current === selected ? updated : current);
        setNotice("Ticket refreshed. Review its latest status and messages, then confirm it again. Your draft is preserved.");
      } catch (e) { if (request.current === expected) setError(e instanceof Error ? e.message : "Unable to refresh ticket."); }
    }
  };
  const saved = (row: Interaction) => { setAction(null); setNotice(`Inbound call #${row.id} saved · ${stateName(row.state)}. Lead ownership is unchanged.`); setRefresh(v => v + 1); if (lead) void open(lead.id, true); };
  const chooseAction = (next: InboundAction) => { setAction(next); setEditing(false); setTask(null); setNotice(""); };

  return <section className="page sales-workspace call-center-workspace">
    <header className="sales-hero"><div><p className="eyebrow">SHARED CUSTOMER ASSISTANCE</p><h1>Call center / All customers</h1><p className="subtext">Assist callers across all branches. Assigned lead ownership stays with the responsible team.</p></div><div className="sales-hero-actions"><button className="button primary" onClick={() => { setReview(null); setLookup(true); }}>Find customer</button><a className="filter" href={isAdmin ? "/all-leads" : "/my-leads"}>{isAdmin ? "Assigned leads" : "My assigned leads"}</a><button className="filter" onClick={() => { request.current++; setLead(null); setReview(null); setEditing(false); setTask(null); setAction("NOTE"); }}>Record unmatched call</button></div></header>
    <p className="call-center-notice"><strong>Inbound calls handled today:</strong> {summary?.inbound_calls_today ?? "…"}{isAdmin ? " · All handlers" : ` · ${handler}`}</p>
    {isAdmin && summary && <details className="sales-info-card"><summary>Inbound activity by handler</summary>{summary.by_handler.map(row => <p key={row.handled_by}>{`${row.handled_by__first_name} ${row.handled_by__last_name}`.trim() || row.handled_by__email}: {row.count}</p>)}</details>}
    {configError && <p className="form-error" role="alert">{configError} <button className="filter" onClick={loadConfig}>Retry form options</button></p>}
    {error && <p className="form-error" role="alert">{error}</p>}{notice && <p className="call-center-notice" role="status">{notice}</p>}{loading && <p role="status">Loading current customer record…</p>}
    {lookup && <CustomerLookup onClose={() => setLookup(false)} onOpenLead={selected => { setLookup(false); void open(selected.id); }} onUnmatched={() => { setLookup(false); setLead(null); setReview(null); setAction("NOTE"); }} />}
    {review && <ReviewEnquiry key={review.id} row={review} lead={lead} onFind={() => setLookup(true)} onCancel={() => setReview(null)} onSaved={() => { setReview(null); setRefresh(v => v + 1); setNotice("Admin review saved."); }} />}
    {lead && <>
      <header className="call-center-heading"><div><h2>{lead.name} · #{String(lead.id).padStart(6, "0")}</h2><p><strong>Registered phone:</strong> {lead.phone} · <strong>Status:</strong> {lead.status}</p></div><button className="filter" onClick={() => void refreshRecord()} disabled={loading}>Refresh record · Keep draft</button></header>
      <p className="call-center-notice"><strong>Assigned CE:</strong> {lead.assignedSoName || (lead.needsCreReassignment ? "Awaiting reassignment" : "Not assigned")} · <strong>Call handled by:</strong> {handler}{lead.assignedSoId !== user.id ? " · You are handling this call for the assigned team." : ""}</p>
      <LeadOwnershipPanel ownership={lead.ownership} />
      <div className="call-center-action-bar" aria-label="Customer actions"><button className="filter" disabled={!config} onClick={() => chooseAction("NOTE")}>Record inbound call</button><button className="filter" disabled={!config || !lead.outcomePolicy.can_update} onClick={() => { setEditing(true); setAction(null); setTask(null); }}>Update lead</button><button className="filter" disabled={!config} onClick={() => chooseAction("CALLBACK")}>Schedule callback</button><button className="filter" disabled={!config} onClick={() => chooseAction("COMPLAINT")}>Complaint</button><button className="filter" disabled={!config} onClick={() => chooseAction("SERVICE")}>Service request</button></div>
      {!lead.outcomePolicy.can_update && <p className="subtext">Closed enquiry: inbound assistance and tickets remain available. Ask Admin to reopen sales progress.</p>}
    </>}
    {action && !config && !configError && <p role="status">Loading form options…</p>}
    {action && config && <InboundForm key={`${lead?.id || "unmatched"}-${typeof action === "string" ? action : `${action.kind}-${action.ticket.id}`}`} lead={lead} action={action} config={config} handler={handler} onSaved={saved} onCancel={() => setAction(null)} />}
    {editing && lead && config && <SharedLeadEditor key={lead.id} lead={lead} config={config} onCancel={() => setEditing(false)} onSaved={updated => { setLead(updated); setEditing(false); setRefresh(v => v + 1); setNotice(`${updated.name} updated · Assigned CE: ${updated.assignedSoName || "Not assigned"} · Assigned PS/SO: ${updated.assignedPsName || "Not assigned"}.`); }} />}
    {task && lead && <CallbackAction shared key={task.id} task={task} leadVersion={lead.updated_at} onCancel={() => setTask(null)} onSaved={() => { setTask(null); setRefresh(v => v + 1); void open(lead.id, true); }} />}
    {lead && <>
      <section className="sales-info-card"><h3>Upcoming follow-ups</h3>{lead.callbacks.length ? lead.callbacks.map(item => <div className="call-center-task" key={item.id}><p><strong>{item.owner_name}:</strong> {formatDateTime(item.scheduled_for)} · {item.origin === "INBOUND" ? "Inbound callback" : "Outbound follow-up"}{item.reminder_held ? " · Held for review" : ""}</p><button className="filter" onClick={() => { setTask(item); setAction(null); setEditing(false); }}>Update this follow-up</button></div>) : <p>No upcoming follow-ups.</p>}</section>
      <TicketHistory key={`tickets-${lead.id}`} lead={lead} refresh={refresh} onAction={chooseAction} />
      <details className="sales-info-card"><summary>Customer information & qualification</summary><dl className="lookup-facts">{[["Name", lead.name], ["Phone", lead.phone], ["Email", lead.email], ["Model", lead.model], ["Branch", lead.branch], ["City", lead.city], ["Pincode", lead.pincode], ["Enquiry date", lead.enquiredAt], ["Source", lead.source], ["Source detail", lead.sourceLabel], ["Campaign", lead.campaign], ["Activity", lead.activity], ["Sub-activity", lead.sub_activity], ["Category", lead.category]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value || "Not recorded"}</dd></div>)}</dl>{lead.qualification && <dl className="lookup-facts">{Object.entries(lead.qualification).filter(([key]) => key !== "updated_at").map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd className="call-center-notes">{typeof value === "boolean" ? value ? "Yes" : "No" : value || "Not recorded"}</dd></div>)}</dl>}</details>
      <details className="sales-info-card"><summary>Outbound call history · {lead.callHistory.length}</summary>{lead.callHistory.map(call => <article className="call-center-history" key={call.id}><p><strong>Call made by:</strong> {call.so_name} · {formatDateTime(call.created_at)}</p><p><strong>Outcome:</strong> {call.outcome || call.status}</p><p className="call-center-notes">{call.remarks}</p></article>)}</details>
      <InteractionHistory key={`interactions-${lead.id}`} leadId={lead.id} refresh={refresh} />
      <details className="sales-info-card"><summary>Recent change history</summary>{lead.auditHistory.map((entry, index) => <p key={index}>{formatDateTime(entry.created_at)} · {entry.actor} · {entry.event.replaceAll("_", " ")}</p>)}</details>
    </>}
    <InboundCallbacks all={isAdmin} key={`callbacks-${refresh}`} />
    {isAdmin ? <InteractionHistory pending refresh={refresh} onReview={row => { setReview(row); setAction(null); setEditing(false); if (row.lead_id) void open(row.lead_id); else setLead(null); }} /> : !lead && <InteractionHistory refresh={refresh} />}
  </section>;
}

function TicketHistory({ lead, refresh, onAction }: { lead: SharedDetail; refresh: number; onAction: (action: InboundAction) => void }) {
  const [kind, setKind] = useState<"complaint" | "service">("complaint");
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<Page<SharedComplaint | SharedService> | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let current = true;
    getSharedTickets<SharedComplaint | SharedService>(lead.id, kind, page).then(data => { if (current) { setResult(data); setError(""); } }).catch(e => { if (current) setError(e.message); });
    return () => { current = false; };
  }, [lead.id, kind, page, refresh, retry]);
  return <section className="sales-info-card"><h3>Existing complaints & service requests</h3><p className="subtext">Review existing tickets before creating another. Phone matches require confirmation.</p>
    <div className="call-center-action-bar"><button className="filter" aria-pressed={kind === "complaint"} onClick={() => { if (kind !== "complaint") { setKind("complaint"); setPage(1); setResult(null); setError(""); } }}>Complaints</button><button className="filter" aria-pressed={kind === "service"} onClick={() => { if (kind !== "service") { setKind("service"); setPage(1); setResult(null); setError(""); } }}>Service requests</button></div>
    {error && <p role="alert" className="form-error">{error} <button className="filter" onClick={() => setRetry(v => v + 1)}>Retry tickets</button></p>}
    {!result && !error && <p role="status">Loading tickets…</p>}{result && !result.count && <p>No matching {kind === "complaint" ? "complaints" : "service requests"}.</p>}
    {result?.results.map(ticket => <article className="call-center-history" key={ticket.id}><h4>{ticket.ticket_number} · {ticket.status}</h4><p><strong>Branch:</strong> {ticket.branch} · {ticket.confirmed_link ? "Linked enquiry" : "Phone match · Confirm with caller"}</p><p><strong>Recorded by:</strong> {"logged_by_name" in ticket ? ticket.logged_by_name : ticket.created_by_name} · {formatDateTime(ticket.created_at)}</p><p>{"subject" in ticket ? ticket.subject : ticket.issue}</p><details><summary>Ticket details & messages</summary>{"description" in ticket && <p className="call-center-notes">{ticket.description}</p>}{ticket.resolution_notes && <p><strong>Resolution:</strong> {ticket.resolution_notes}</p>}{"notes" in ticket ? ticket.notes.map(note => <p key={note.id}>{formatDateTime(note.created_at)} · {note.author_name}<br />{note.content}</p>) : ticket.events?.map(event => <p key={event.id}>{formatDateTime(event.created_at)} · {event.actor_name} · {event.action}<br />{event.note}</p>)}</details><button className="filter" onClick={() => onAction("notes" in ticket ? { kind: "COMPLAINT_NOTE", ticket } : { kind: "SERVICE_NOTE", ticket })}>Add customer message</button></article>)}
    {result && <CallCenterPagination result={result} page={page} onPage={value => { setResult(null); setPage(value); }} />}
  </section>;
}
