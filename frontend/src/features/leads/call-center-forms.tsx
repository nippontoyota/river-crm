"use client";

import { useEffect, useState, type FormEvent } from "react";
import { getOfficers, sourceName, statusName, type SystemConfig } from "@/lib/crm";
import { getSharedLead, recordInteraction, updateSharedLead, stateName, type Interaction, type SharedDetail, type SharedComplaint, type SharedService } from "@/lib/call-center";
import { useSubmission } from "./call-center-actions";

type TicketSelection = { kind: "COMPLAINT_NOTE"; ticket: SharedComplaint } | { kind: "SERVICE_NOTE"; ticket: SharedService };
export type InboundAction = "NOTE" | "CALLBACK" | "COMPLAINT" | "SERVICE" | TicketSelection;
const errorMessage = (e: unknown) => e instanceof Error ? e.message : "Unable to save. Try again.";
const field = (data: FormData, key: string) => String(data.get(key) || "");
const istTime = (value: string) => new Date(`${value}:00+05:30`).toISOString();

export function InboundForm({ lead, action, config, handler, onSaved, onCancel }: { lead: SharedDetail | null; action: InboundAction; config: SystemConfig; handler: string; onSaved: (row: Interaction) => void; onCancel: () => void }) {
  const kind = typeof action === "string" ? action : action.kind;
  const [category, setCategory] = useState("AFTER_SALES");
  const [defer, setDefer] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submission = useSubmission();
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); if (busy) return;
    const data = new FormData(event.currentTarget);
    setBusy(true); setError("");
    try {
      const payload: Record<string, unknown> = { kind, lead_id: lead?.id ?? null, ...(lead ? { lead_version: lead.updated_at } : {}), confirm_customer: data.get("confirm_customer") === "on", caller_name: field(data, "caller_name"), caller_phone: field(data, "caller_phone"), reason: field(data, "reason"), notes: field(data, "notes"), acknowledge_active: data.get("acknowledge_active") === "on" };
      if (kind === "CALLBACK") payload.callback_at = istTime(field(data, "callback_at"));
      if (typeof action !== "string") {
        payload.ticket_id = action.ticket.id;
        payload.ticket_version = "revision" in action.ticket ? String(action.ticket.revision) : action.ticket.updated_at;
        payload.confirm_ticket = data.get("confirm_ticket") === "on";
      }
      if (lead && !defer && kind === "COMPLAINT") payload.complaint = { category, subtype: field(data, "subtype"), branch: field(data, "branch"), priority: field(data, "priority"), subject: field(data, "subject"), description: field(data, "notes"), model_interest: lead.model === "—" ? "" : lead.model };
      if (lead && !defer && kind === "SERVICE") payload.service = { vehicle: Number(field(data, "vehicle")), branch: field(data, "branch"), priority: field(data, "priority"), issue: field(data, "notes"), ...(field(data, "appointment") ? { preferred_appointment: istTime(field(data, "appointment")) } : {}) };
      onSaved(await recordInteraction(submission(payload)));
    } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  };
  const title = { NOTE: "Record inbound call", CALLBACK: "Schedule callback", COMPLAINT: "New complaint", SERVICE: "New service request", COMPLAINT_NOTE: "Add message to complaint", SERVICE_NOTE: "Add message to service request" }[kind];
  return <form className="sales-form-card call-center-form" onSubmit={save}>
    <h3>{title}</h3><p><strong>Call handled by:</strong> {handler}</p>
    {lead ? <label className="call-center-check"><input type="checkbox" name="confirm_customer" required />Caller confirmed: {lead.name} · {lead.phone} · Lead #{lead.id} · {lead.branch || "Branch not recorded"}</label> : <p className="call-center-notice">This call will be saved as unmatched for admin review. No sales lead is created.</p>}
    <div className="sales-form-grid"><label>Caller name<input name="caller_name" maxLength={160} defaultValue={lead?.name || ""} /></label><label>Incoming phone number<input name="caller_phone" type="tel" required maxLength={40} defaultValue={lead?.phone || ""} /></label></div>
    <p className="subtext">An alternate caller number is recorded with this call; the registered customer number stays unchanged.</p>
    <label>Reason for calling<input name="reason" required maxLength={160} placeholder="e.g. Returning a missed call" /></label>
    {kind === "CALLBACK" && <><p className="call-center-notice"><strong>Next action owner:</strong> {lead?.callback_destination.available ? `${lead.callback_destination.owner?.name} (${lead.callback_destination.role === "SO" ? "PS/SO" : "CE"})` : "Awaiting routing · Admin will review"}</p><label>Callback time (IST)<input type="datetime-local" name="callback_at" required /></label></>}
    {typeof action !== "string" && <><p><strong>Selected ticket:</strong> {action.ticket.ticket_number} · {action.ticket.status}</p><label className="call-center-check"><input key={"revision" in action.ticket ? action.ticket.revision : action.ticket.updated_at} type="checkbox" name="confirm_ticket" required />Caller confirmed this is the correct ticket{!action.ticket.confirmed_link ? " (suggested by matching phone)" : ""}</label></>}
    {lead && ["COMPLAINT", "SERVICE"].includes(kind) && <><label className="call-center-check"><input type="checkbox" checked={defer} onChange={e => setDefer(e.target.checked)} />Details incomplete · Save call for admin review</label>
      {!defer && <div className="sales-form-grid"><label>{kind === "SERVICE" ? "Service branch" : "Complaint branch"}<select name="branch" required defaultValue={lead.branch}><option value="">Select branch</option>{config.lists.branches?.map(branch => <option key={branch}>{branch}</option>)}</select></label>
      <label>Priority<select name="priority" defaultValue={kind === "SERVICE" ? "NORMAL" : "MEDIUM"}>{(kind === "SERVICE" ? ["LOW", "NORMAL", "HIGH", "URGENT"] : ["LOW", "MEDIUM", "HIGH", "CRITICAL"]).map(value => <option key={value}>{value}</option>)}</select></label>
      {kind === "COMPLAINT" ? <><label>Complaint type<select value={category} onChange={e => setCategory(e.target.value)}>{Object.keys(config.complaint_subtypes).map(key => <option key={key} value={key}>{key.replaceAll("_", " ")}</option>)}</select></label><label>Subtype<select name="subtype" required key={category}><option value="">Select subtype</option>{config.complaint_subtypes[category]?.map(value => <option key={value}>{value}</option>)}</select></label><label>Subject<input name="subject" required maxLength={200} /></label></> : <><label>Customer vehicle<select name="vehicle" required><option value="">Select confirmed vehicle</option>{lead.vehicles.map(vehicle => <option key={vehicle.id} value={vehicle.id}>{vehicle.chassis_number} · {vehicle.model} · {vehicle.registration_number || "Registration not recorded"}</option>)}</select></label><label>Preferred appointment (IST)<input name="appointment" type="datetime-local" /></label>{!lead.vehicles.length && <p>No registered vehicle. Save the call for review so the vehicle can be identified.</p>}</>}
      </div>}
      {!defer && <label className="call-center-check"><input type="checkbox" name="acknowledge_active" />I reviewed existing tickets; this is a separate issue if another ticket is still open.</label>}
    </>}
    <label>Customer message / notes<textarea name="notes" required maxLength={10000} rows={4} /></label>
    {error && <p className="form-error" role="alert">{error}</p>}
    <footer><button className="filter" type="button" onClick={onCancel} disabled={busy}>Cancel</button><button className="button primary" disabled={busy}>{busy ? "Saving…" : "Save inbound call"}</button></footer>
  </form>;
}

const fieldsFor = (lead: SharedDetail) => ({ name: lead.name, phone: lead.phone, email: lead.email || "", source: lead.sourceCode, source_label: lead.sourceLabel || "", campaign: lead.campaign || "", activity: lead.activity || "", sub_activity: lead.sub_activity || "", model_interest: lead.model === "—" ? "" : lead.model, city: lead.city || "", pincode: lead.pincode || "", branch: lead.branch || "", enquiry_date: lead.enquiryDate || "", category: lead.category, status: lead.statusCode });
const transitions: Record<string, string[]> = { FRESH: ["RNR", "SWITCHED_OFF", "CALLBACK", "PENDING", "QUALIFIED", "UNQUALIFIED", "LOST"], RNR: ["SWITCHED_OFF", "CALLBACK", "PENDING", "QUALIFIED", "UNQUALIFIED", "LOST"], SWITCHED_OFF: ["RNR", "CALLBACK", "PENDING", "QUALIFIED", "UNQUALIFIED", "LOST"], CALLBACK: ["RNR", "SWITCHED_OFF", "PENDING", "QUALIFIED", "UNQUALIFIED", "WALKIN", "LOST"], PENDING: ["RNR", "SWITCHED_OFF", "CALLBACK", "QUALIFIED", "UNQUALIFIED", "WALKIN", "LOST"], QUALIFIED: ["WALKIN", "WON", "LOST"], WALKIN: ["WON", "LOST"] };

export function SharedLeadEditor({ lead, config, onSaved, onCancel }: { lead: SharedDetail; config: SystemConfig; onSaved: (lead: SharedDetail) => void; onCancel: () => void }) {
  const [base] = useState(() => fieldsFor(lead));
  const [values, setValues] = useState(base);
  const [version, setVersion] = useState(lead.updated_at);
  const [latest, setLatest] = useState(lead);
  const [officers, setOfficers] = useState<{ id: number; first_name: string; last_name: string; email: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [optionsError, setOptionsError] = useState("");
  const submission = useSubmission();
  const qualifying = values.status === "QUALIFIED" && base.status !== "QUALIFIED";
  useEffect(() => {
    if (!qualifying || !values.branch) return;
    let current = true;
    getOfficers(values.branch).then(rows => { if (current) { setOfficers(rows); setOptionsError(""); } }).catch(e => { if (current) { setOfficers([]); setOptionsError(e.message); } });
    return () => { current = false; };
  }, [qualifying, values.branch]);
  const set = (key: keyof typeof values, value: string) => setValues(old => ({ ...old, [key]: value }));
  const options = (items: string[] | undefined, current: string) => [...new Set([current, ...items || []].filter(Boolean))].map(value => <option key={value} value={value}>{value}</option>);
  return <form className="sales-form-card call-center-form" onSubmit={async event => {
    event.preventDefault(); if (busy) return;
    const data = new FormData(event.currentTarget); setBusy(true); setError("");
    const payload: Record<string, unknown> = Object.fromEntries(Object.entries(values).filter(([key, value]) => value !== base[key as keyof typeof base]));
    if (payload.enquiry_date === "") payload.enquiry_date = null;
    payload.lead_version = version;
    if (qualifying) Object.assign(payload, { call_outcome: "QUALIFIED", city: values.branch, ps_officer_id: Number(field(data, "ps_officer_id")), qualification: { variant: field(data, "variant"), buying_timeline: field(data, "buying_timeline"), finance_type: field(data, "finance_type"), trade_in: null, test_drive: "", notes: field(data, "qualification_notes") } });
    if (field(data, "remarks")) payload.remarks = field(data, "remarks");
    try { onSaved(await updateSharedLead(lead.id, submission(payload))); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }}><h3>Update lead #{lead.id}</h3><p><strong>Assigned CE:</strong> {latest.assignedSoName || "Not assigned"} · <strong>Assigned PS/SO:</strong> {latest.assignedPsName || "Not assigned"}</p>
    <div className="sales-form-grid">
      {([['name', 'Customer name'], ['phone', 'Registered phone'], ['email', 'Email'], ['city', 'City'], ['pincode', 'Pincode'], ['source_label', 'Source detail'], ['campaign', 'Campaign']] as const).map(([key, label]) => <label key={key}>{label}<input value={values[key]} onChange={e => set(key, e.target.value)} required={key === "name" || key === "phone"} type={key === "email" ? "email" : "text"} pattern={key === "phone" ? "[0-9]{10}" : key === "pincode" ? "[1-9][0-9]{5}" : undefined} maxLength={key === "phone" ? 10 : key === "pincode" ? 6 : 160} /></label>)}
      <label>Lead source<select value={values.source} onChange={e => set("source", e.target.value)}>{[...new Set([values.source, ...config.lists.sources || []])].map(value => <option key={value} value={value}>{sourceName(value)}</option>)}</select></label>
      <label>Model<select value={values.model_interest} onChange={e => set("model_interest", e.target.value)} required={qualifying}><option value="">Select model</option>{options(config.lists.models, values.model_interest)}</select></label>
      <label>Branch<select value={values.branch} onChange={e => set("branch", e.target.value)} required={qualifying}><option value="">Select branch</option>{options(config.lists.branches, values.branch)}</select></label>
      <label>Activity<select value={values.activity} onChange={e => setValues(old => ({ ...old, activity: e.target.value, sub_activity: "" }))}><option value="">None</option>{options(config.lists.activities, values.activity)}</select></label>
      <label>Sub-activity<select value={values.sub_activity} onChange={e => set("sub_activity", e.target.value)}><option value="">None</option>{options(config.lists.subActivities?.[values.activity], values.sub_activity)}</select></label>
      <label>Enquiry date<input type="date" value={values.enquiry_date} onChange={e => set("enquiry_date", e.target.value)} /></label>
      <label>Category<select value={values.category} onChange={e => set("category", e.target.value)}>{["HOT", "WARM", "COLD"].map(value => <option key={value}>{value}</option>)}</select></label>
      <label>Lead status<select value={values.status} onChange={e => set("status", e.target.value)}>{[...new Set([base.status, ...transitions[base.status] || []])].map(value => <option key={value} value={value}>{statusName(value)}</option>)}</select></label>
    </div>
    {qualifying && <div className="sales-form-grid"><label>Assigned PS/SO<select name="ps_officer_id" required defaultValue={lead.assignedPsId || ""} key={values.branch}><option value="">Select PS/SO</option>{officers.map(user => <option key={user.id} value={user.id}>{`${user.first_name} ${user.last_name}`.trim() || user.email}</option>)}</select></label><label>Color variant<select name="variant" required><option value="">Select variant</option>{options(config.lists.colorVariants, "")}</select></label><label>Buying plan<select name="buying_timeline" required>{["Immediate", "1–2 Months", "2–3 Months", "Greater than 3 months"].map(value => <option key={value}>{value}</option>)}</select></label><label>Finance<select name="finance_type" required><option>Inhouse</option><option>Outright</option></select></label><label>Qualification notes<textarea name="qualification_notes" required maxLength={10000} /></label></div>}
    {optionsError && <p role="alert">{optionsError}</p>}
    <p className="subtext">Schedule a callback before moving to Pending, Callback, or Walk-in. Updating progress preserves existing reminders.</p>
    <label>Change remarks<textarea name="remarks" maxLength={500} required={values.status !== base.status} /></label>
    {error && <p className="form-error" role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    <footer><button type="button" className="filter" disabled={busy} onClick={async () => { try { const fresh = await getSharedLead(lead.id); setVersion(fresh.updated_at); setLatest(fresh); setMessage(`Latest saved name: ${fresh.name}; status: ${fresh.status}. Your draft is preserved. Review it before saving.`); } catch (e) { setError(errorMessage(e)); } }}>Refresh record · Keep draft</button><button type="button" className="filter" onClick={onCancel}>Cancel</button><button className="button primary" disabled={busy || !!optionsError}>{busy ? "Saving…" : "Save lead changes"}</button></footer>
  </form>;
}

export function ReviewEnquiry({ row, lead, onFind, onSaved, onCancel }: { row: Interaction; lead: SharedDetail | null; onFind: () => void; onSaved: () => void; onCancel: () => void }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submission = useSubmission();
  return <form className="sales-form-card call-center-form" onSubmit={async event => {
    event.preventDefault(); if (busy) return;
    const data = new FormData(event.currentTarget); setBusy(true); setError("");
    try {
      await recordInteraction(submission({ kind: "REVIEW", interaction_id: row.id, interaction_version: row.updated_at, lead_id: lead?.id ?? null, ...(lead ? { lead_version: lead.updated_at } : {}), confirm_customer: data.get("confirm_customer") === "on", notes: field(data, "notes"), review_state: row.kind === "CALLBACK" && field(data, "callback_at") ? "RECORDED" : "RESOLVED", ...(field(data, "callback_at") ? { callback_at: istTime(field(data, "callback_at")) } : {}) }));
      onSaved();
    } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }}><h3>Review enquiry #{row.id} · {stateName(row.state)}</h3><p>{row.caller_name} · {row.caller_phone}</p><p className="call-center-notes">{row.notes}</p><button className="filter" type="button" onClick={onFind}>Find matching enquiry</button>
    {lead && <label className="call-center-check"><input type="checkbox" name="confirm_customer" required />Confirmed enquiry: {lead.name} · {lead.phone} · #{lead.id}</label>}
    {row.kind === "CALLBACK" && <label>Callback time (IST) · Leave empty to close without a callback<input type="datetime-local" name="callback_at" /></label>}
    <p className="subtext">Assign an active CE/PS through the Assignment screen before routing a callback. For a complaint or service enquiry, create or link its ticket in the customer workspace before closing review.</p>
    <label>Review outcome<textarea name="notes" required maxLength={10000} /></label>{error && <p className="form-error" role="alert">{error}</p>}
    <footer><button className="filter" type="button" onClick={onCancel}>Cancel</button><button className="button primary" disabled={busy}>{busy ? "Saving…" : "Save review"}</button></footer>
  </form>;
}
