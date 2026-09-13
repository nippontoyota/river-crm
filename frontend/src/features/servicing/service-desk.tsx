"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, getLeadDetail, getSystemConfig, type CurrentUser, type LeadDetail } from "@/lib/crm";
import { formatDateTime } from "@/lib/dates";
import { getServiceRequest, getVehicle, serviceAction, serviceStatuses, type Page, type ServiceRequest, type Vehicle } from "@/lib/service";
import { ServiceHistory, VehicleRegistration } from "./vehicle-panel";

function SalePicker({ selected, onSelect }: { selected: LeadDetail | null; onSelect: (lead: LeadDetail | null) => void }) {
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<{ id: number; name: string; phone: string; sales_outcome: string }[]>([]);
  const [error, setError] = useState("");
  const search = async () => {
    try { const rows = await api<Page<{ id: number; name: string; phone: string; sales_outcome: string }>>(`/api/leads/?q=${encodeURIComponent(query)}`); setMatches(rows.results); setError(rows.results.length ? "" : "No accessible leads found."); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to search sales."); }
  };
  return <div className="service-sale-picker"><label>Link an existing CRM lead <small>Optional</small><div className="service-inline"><input aria-label="Search accessible sales" value={query} onChange={e => setQuery(e.target.value)} placeholder="Customer name or phone" /><button type="button" className="filter" disabled={!query.trim()} onClick={() => void search()}>Find sale</button></div></label>
    {selected && <p>Selected: {selected.name} · {selected.phone} <button className="filter" type="button" onClick={() => onSelect(null)}>Clear</button></p>}
    {matches.map(row => <button type="button" className="service-vehicle-choice" key={row.id} onClick={() => void getLeadDetail(row.id).then(lead => { onSelect(lead); setMatches([]); }).catch(e => setError(e.message))}><b>{row.name} · {row.phone}</b><span>#{row.id} · {row.sales_outcome}</span></button>)}
    {error && <p role="status">{error}</p>}
  </div>;
}

function IntakeFields({ row, branches, branch, setBranch, fixedBranch }: { row?: ServiceRequest; branches: string[]; branch: string; setBranch: (value: string) => void; fixedBranch: boolean }) {
  return <><label>Issue / service required<textarea name="issue" required maxLength={10000} defaultValue={row?.issue} placeholder="Record what the customer needs help with." /></label><div className="service-grid">
    <label>Service branch<select name="branch" value={branch} required disabled={fixedBranch} onChange={e => setBranch(e.target.value)}><option value="">Choose branch</option>{[...new Set([...branches, branch])].filter(Boolean).map(value => <option key={value}>{value}</option>)}</select></label>
    <label>Request source<select name="source" defaultValue={row?.source || (fixedBranch ? "WALKIN" : "PHONE")}>{["PHONE", "WALKIN", "EMAIL", "OTHER"].map(value => <option value={value} key={value}>{value === "WALKIN" ? "Walk-in" : value.charAt(0) + value.slice(1).toLowerCase()}</option>)}</select></label>
    <label>Priority<select name="priority" defaultValue={row?.priority || "NORMAL"}>{["LOW", "NORMAL", "HIGH", "URGENT"].map(value => <option key={value}>{value}</option>)}</select></label>
    <label>Odometer (km) <small>Optional</small><input type="number" name="odometer" min={0} max={2147483647} defaultValue={row?.odometer ?? ""} /></label>
    <label>Preferred appointment <small>Optional</small><input type="datetime-local" name="preferred_appointment" defaultValue={row?.preferred_appointment ? localDateTime(row.preferred_appointment) : ""} /></label>
  </div></>;
}

function localDateTime(value: string) {
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

function intakePayload(form: HTMLFormElement, branch: string) {
  const data = Object.fromEntries(new FormData(form));
  return { ...data, branch, odometer: data.odometer === "" ? null : Number(data.odometer), preferred_appointment: data.preferred_appointment ? new Date(String(data.preferred_appointment)).toISOString() : null };
}

function NewRequest({ user, branches, onSaved, onCancel }: { user: CurrentUser; branches: string[]; onSaved: (row: ServiceRequest) => void; onCancel: () => void }) {
  const [chassis, setChassis] = useState("");
  const [vehicle, setVehicle] = useState<Vehicle | null>(null);
  const [unknown, setUnknown] = useState(false);
  const [lead, setLead] = useState<LeadDetail | null>(null);
  const [branch, setBranch] = useState(user.role === "SERVICE" ? user.location || "" : "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const lookup = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError(""); setVehicle(null); setUnknown(false); setAcknowledged(false);
    try { const rows = await api<Page<Vehicle>>(`/api/vehicles/?chassis=${encodeURIComponent(chassis)}`); if (rows.results[0]) setVehicle(await getVehicle(rows.results[0])); else setUnknown(true); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to look up chassis."); }
    finally { setBusy(false); }
  };
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); if (!vehicle) return; setBusy(true); setError("");
    try { onSaved(await api<ServiceRequest>("/api/service-requests/", { method: "POST", body: JSON.stringify({ ...intakePayload(event.currentTarget, branch), vehicle: vehicle.id, acknowledge_active: acknowledged }) })); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to record request."); }
    finally { setBusy(false); }
  };
  return <section className="service-card service-intake"><header><div><p className="eyebrow">SERVICE INTAKE</p><h2>Record a service request</h2></div><button className="filter" onClick={onCancel}>Close intake</button></header>
    <form className="service-lookup" onSubmit={lookup}><label>Chassis number<div className="service-inline"><input value={chassis} onChange={e => { setChassis(e.target.value); setVehicle(null); setUnknown(false); }} required maxLength={64} placeholder="Enter scooter chassis number" autoCapitalize="characters" /><button className="button primary" disabled={busy}>Look up scooter</button></div></label></form>
    {error && <p role="alert" className="service-error">{error}</p>}
    {unknown && <><p>No scooter found. Register it to start its service history.</p>{user.role === "CRE" && <SalePicker selected={lead} onSelect={setLead} />}<VehicleRegistration key={lead?.id || "manual"} chassis={chassis} lead={lead || undefined} onSaved={item => { setVehicle(item); setUnknown(false); }} /></>}
    {vehicle && <><VehicleSummary vehicle={vehicle} /><details><summary>Previous service requests ({vehicle.history?.length || 0})</summary><ServiceHistory rows={vehicle.history || []} /></details>
      <form className="service-form" onSubmit={save}><IntakeFields branches={branches} branch={branch} setBranch={setBranch} fixedBranch={user.role === "SERVICE"} />
        <label className="service-check"><input type="checkbox" checked={acknowledged} onChange={e => setAcknowledged(e.target.checked)} />This is a separate issue if another active request exists for this scooter.</label>
        <footer><button className="button primary" disabled={busy}>{busy ? "Saving…" : user.role === "SERVICE" ? "Add to branch queue" : "Save request"}</button></footer>
      </form></>}
  </section>;
}

function VehicleSummary({ vehicle }: { vehicle: Vehicle }) {
  return <div className="service-identity"><div><small>CHASSIS</small><strong>{vehicle.chassis_number}</strong><span>{vehicle.model} · {vehicle.registration_number || "Registration pending"}</span></div><div><b>{vehicle.customer_name}</b><span>{vehicle.customer_phone}</span><span>{vehicle.customer_email}</span></div>{vehicle.sale && <div><small>CRM SALE #{vehicle.sale.id}</small><b>{vehicle.sale.sales_outcome}</b><span>{vehicle.sale.branch || "Branch not recorded"}</span></div>}</div>;
}

function VehicleCorrection({ vehicle, onSaved }: { vehicle: Vehicle; onSaved: (vehicle: Vehicle) => void }) {
  const [lead, setLead] = useState<LeadDetail | null>(null);
  const [unlink, setUnlink] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setBusy(true); setError("");
    const fields = Object.fromEntries(new FormData(event.currentTarget));
    try { onSaved(await api<Vehicle>(`/api/vehicles/${vehicle.id}/`, { method: "PATCH", body: JSON.stringify({ ...fields, related_lead: unlink ? null : lead?.id || vehicle.related_lead }) })); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to correct vehicle."); }
    finally { setBusy(false); }
  };
  return <details className="service-correction"><summary>Correct vehicle details or CRM link</summary><SalePicker selected={lead} onSelect={item => { setLead(item); setUnlink(false); }} />
    <form className="service-form" onSubmit={save}><div className="service-grid"><label>Chassis number<input name="chassis_number" required defaultValue={vehicle.chassis_number} maxLength={64} /></label><label>Model<input name="model" required defaultValue={vehicle.model} maxLength={100} /></label><label>Registration number<input name="registration_number" defaultValue={vehicle.registration_number} maxLength={30} /></label><label>Customer name<input name="customer_name" defaultValue={vehicle.customer_name} required /></label><label>Phone<input name="customer_phone" defaultValue={vehicle.customer_phone} required pattern="[0-9]{10}" maxLength={10} /></label><label>Email<input type="email" name="customer_email" defaultValue={vehicle.customer_email} /></label></div>
    <label className="service-check"><input type="checkbox" checked={unlink} onChange={e => { setUnlink(e.target.checked); setLead(null); }} />Remove the current CRM link</label><label>Correction reason<textarea name="reason" required maxLength={500} /></label>{error && <p role="alert">{error}</p>}<button className="button primary" disabled={busy}>Save correction</button></form>
    {vehicle.corrections?.map((item, index) => <p key={index}>{formatDateTime(item.created_at)} · {item.reason}</p>)}
  </details>;
}

function RequestDetail({ initial, user, branches, onChanged, onClose }: { initial: ServiceRequest; user: CurrentUser; branches: string[]; onChanged: () => void; onClose: () => void }) {
  const [row, setRow] = useState(initial);
  const [note, setNote] = useState("");
  const [branch, setBranch] = useState(initial.branch);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const operator = user.role === "ADMIN" || user.role === "SERVICE";
  const ce = user.role === "CRE" && row.created_by === user.id;
  const active = ["FORWARDED", "IN_PROGRESS", "WAITING"].includes(row.status);
  const execute = async (action: string, values: Record<string, unknown> = {}) => {
    setBusy(true); setError("");
    try { setRow(await serviceAction(row, action, { note, ...values })); setNote(""); onChanged(); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to update request."); }
    finally { setBusy(false); }
  };
  const refresh = async () => { try { const updated = await getServiceRequest(row.id); setRow(updated); setBranch(updated.branch); setError(""); } catch (e) { setError(e instanceof Error ? e.message : "Unable to refresh request."); } };
  const saveIntake = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setBusy(true); setError("");
    try { setRow(await api<ServiceRequest>(`/api/service-requests/${row.id}/`, { method: "PATCH", body: JSON.stringify({ ...intakePayload(event.currentTarget, branch), revision: row.revision }) })); setEditing(false); onChanged(); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to save intake."); }
    finally { setBusy(false); }
  };
  return <section className="service-card service-detail"><header><div><p className="eyebrow">{row.ticket_number} · {row.branch}</p><h2>{row.customer_snapshot.customer_name}</h2><span className={`service-status status-${row.status}`}>{serviceStatuses[row.status]}</span></div><div className="service-inline"><button className="filter" onClick={() => void refresh()}>Refresh</button><button className="filter" onClick={onClose}>Close request</button></div></header>
    {error && <p className="service-error" role="alert">{error}</p>}
    {row.vehicle_details && <VehicleSummary vehicle={row.vehicle_details} />}
    <p className="subtext">Recorded by {row.created_by_name} · {formatDateTime(row.created_at)} · {row.priority} priority · {row.source}</p>
    <h3>Requested service</h3><p className="service-prose">{row.issue}</p>
    <p>{row.odometer !== null ? `${row.odometer.toLocaleString()} km` : "Odometer not recorded"} · {row.preferred_appointment ? `Preferred visit: ${formatDateTime(row.preferred_appointment)}` : "No preferred appointment"}</p>
    <details><summary>Details recorded at intake</summary><p>{row.customer_snapshot.customer_name} · {row.customer_snapshot.customer_phone} · {row.customer_snapshot.customer_email}</p><p>{row.vehicle_snapshot.chassis_number} · {row.vehicle_snapshot.model} · {row.vehicle_snapshot.registration_number}</p></details>
    {!row.branch_staff_available && !["RESOLVED", "CANCELLED"].includes(row.status) && <p className="service-warning">No active service staff in {row.branch}. The request remains in its branch queue; Admin can assign staff or transfer it.</p>}
    {ce && row.status === "RECORDED" && <><button className="filter" onClick={() => setEditing(value => !value)}>{editing ? "Cancel edit" : "Edit intake"}</button>{editing && <form className="service-form" onSubmit={saveIntake}><IntakeFields row={row} branches={branches} branch={branch} setBranch={setBranch} fixedBranch={false} /><button className="button primary" disabled={busy}>Save intake details</button></form>}<button className="button primary" disabled={busy || editing} onClick={() => void execute("forward")}>Forward to {row.branch}</button></>}
    {row.resolution_notes && <div className="service-resolution"><h3>Resolution</h3><p className="service-prose">{row.resolution_notes}</p><small>{row.resolved_at && formatDateTime(row.resolved_at)}</small></div>}
    {(operator || ce) && <div className="service-actions"><label>Progress note / reason<textarea aria-label="Progress note or reason" value={note} maxLength={10000} onChange={e => setNote(e.target.value)} placeholder="Record progress, a waiting reason, or the resolution." /></label><div className="service-action-buttons">
      <button className="filter" disabled={busy || !note.trim()} onClick={() => void execute("note")}>Add note</button>
      {operator && active && <>{row.status !== "IN_PROGRESS" && <button className="button primary" disabled={busy} onClick={() => void execute("progress", { status: "IN_PROGRESS" })}>{row.status === "FORWARDED" ? "Start work" : "Resume work"}</button>}{row.status === "IN_PROGRESS" && <button className="filter" disabled={busy || !note.trim()} onClick={() => void execute("progress", { status: "WAITING" })}>Mark waiting</button>}{row.status !== "FORWARDED" && <button className="button primary" disabled={busy || !note.trim()} onClick={() => void execute("resolve")}>Resolve request</button>}</>}
      {operator && row.status === "RESOLVED" && <button className="filter" disabled={busy || !note.trim()} onClick={() => void execute("reopen")}>Reopen request</button>}
      {((operator && active) || (ce && row.status === "RECORDED")) && <button className="filter" disabled={busy || !note.trim()} onClick={() => void execute("cancel")}>Cancel request</button>}
    </div>{user.role === "ADMIN" && active && <div className="service-inline"><label>Transfer to branch<select value={branch} onChange={e => setBranch(e.target.value)}>{[...new Set([...branches, branch])].map(value => <option key={value}>{value}</option>)}</select></label><button className="filter" disabled={busy || !note.trim() || branch === row.branch} onClick={() => void execute("transfer", { branch })}>Transfer request</button></div>}</div>}
    <h3>Request timeline</h3><ol className="service-timeline">{row.events?.map(item => <li key={item.id}><b>{item.action.replaceAll("_", " ")} · {item.actor_name}</b><small>{formatDateTime(item.created_at)} · {String(item.after.branch || "")} · {serviceStatuses[String(item.after.status)] || ""}</small>{item.note && <p className="service-prose">{item.note}</p>}</li>)}</ol>
    <details><summary>Scooter service history</summary><ServiceHistory rows={row.history || []} /></details>
    {user.role === "ADMIN" && row.vehicle_details && <VehicleCorrection key={row.vehicle_details.chassis_number} vehicle={row.vehicle_details} onSaved={() => void refresh()} />}
  </section>;
}

export function ServiceDesk({ user }: { user: CurrentUser }) {
  const [rows, setRows] = useState<Page<ServiceRequest>>({ count: 0, results: [], next: null, previous: null });
  const [branches, setBranches] = useState<string[]>([]);
  const [status, setStatus] = useState("");
  const [branch, setBranch] = useState("");
  const [query, setQuery] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);
  const [version, setVersion] = useState(0);
  const [creating, setCreating] = useState(false);
  const [detail, setDetail] = useState<ServiceRequest | null>(null);
  const [vehicle, setVehicle] = useState<Vehicle | null>(null);
  const [chassis, setChassis] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const open = useCallback(async (id: number) => { try { setDetail(await getServiceRequest(id)); setCreating(false); setError(""); } catch (e) { setError(e instanceof Error ? e.message : "Unable to open request."); } }, []);
  useEffect(() => { getSystemConfig().then(config => setBranches(config.lists?.branches || [])).catch(e => setError(e.message)); }, []);
  useEffect(() => { const listener = (event: Event) => { void open((event as CustomEvent<number>).detail); }; window.addEventListener("service:open", listener); return () => window.removeEventListener("service:open", listener); }, [open]);
  useEffect(() => {
    let alive = true;
    const id = new URLSearchParams(window.location.search).get("request");
    if (id && /^\d+$/.test(id)) getServiceRequest(Number(id)).then(row => { if (alive) setDetail(row); }).catch(e => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    const refresh = () => {
      if (document.hidden) return;
      const params = new URLSearchParams({ page: String(page), status, branch, q: query, date_from: dateFrom, date_to: dateTo });
      api<Page<ServiceRequest>>(`/api/service-requests/?${params}`, { signal: controller.signal }).then(data => { setRows(data); setError(""); }).catch(e => { if (e.name !== "AbortError") setError(e.message); }).finally(() => setLoading(false));
    };
    const debounce = window.setTimeout(refresh, 200);
    const timer = window.setInterval(refresh, 30000);
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => { controller.abort(); clearTimeout(debounce); clearInterval(timer); window.removeEventListener("focus", refresh); document.removeEventListener("visibilitychange", refresh); };
  }, [page, status, branch, query, dateFrom, dateTo, version]);
  const lookup = async (event: FormEvent) => {
    event.preventDefault(); setError(""); setVehicle(null);
    try { const result = await api<Page<Vehicle>>(`/api/vehicles/?chassis=${encodeURIComponent(chassis)}`); if (!result.results.length) { setError("No scooter found. Use New service request to register it."); return; } setVehicle(await getVehicle(result.results[0])); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to look up scooter."); }
  };
  return <div className="service-desk"><header className="service-page-heading"><div><p className="eyebrow">{user.role === "SERVICE" ? user.location : user.role === "CRE" ? "CE SERVICE INTAKE" : "SERVICE OVERVIEW"}</p><h1>Services</h1><p className="subtext">{user.role === "CRE" ? "Record requests, forward to a branch, and follow their progress." : user.role === "SERVICE" ? "Manage your branch’s requests and review each scooter’s history." : "Track requests and resolution across branches."}</p></div>{["CRE", "SERVICE"].includes(user.role) && <button className="button primary" onClick={() => { setCreating(true); setDetail(null); }}>＋ New service request</button>}</header>
    {error && <p className="service-error" role="alert">{error}</p>}
    {creating && <NewRequest user={user} branches={branches} onCancel={() => setCreating(false)} onSaved={row => { setCreating(false); setVersion(v => v + 1); void open(row.id); }} />}
    {detail && <RequestDetail key={`${detail.id}-${detail.revision}`} initial={detail} user={user} branches={branches} onClose={() => setDetail(null)} onChanged={() => setVersion(v => v + 1)} />}
    <section className="service-card"><form className="service-lookup" onSubmit={lookup}><label>Scooter history by chassis<div className="service-inline"><input value={chassis} onChange={e => { setChassis(e.target.value); setVehicle(null); }} required maxLength={64} placeholder="Exact chassis number" /><button className="filter">View history</button></div></label></form>
      {vehicle && <><VehicleSummary vehicle={vehicle} /><ServiceHistory rows={vehicle.history || []} />{user.role === "ADMIN" && <VehicleCorrection key={vehicle.chassis_number} vehicle={vehicle} onSaved={updated => void getVehicle(updated).then(setVehicle).catch(e => setError(e.message))} />}</>}
    </section>
    <section className="service-card service-queue"><div className="service-tabs" aria-label="Request status"><button className={!status ? "active" : ""} onClick={() => { setStatus(""); setPage(1); }}>All requests</button>{Object.entries(serviceStatuses).filter(([value]) => user.role !== "SERVICE" || value !== "RECORDED").map(([value, label]) => <button key={value} className={status === value ? "active" : ""} onClick={() => { setStatus(value); setPage(1); }}>{label}</button>)}</div>
      <div className="service-filters"><label>Search<input value={query} onChange={e => { setQuery(e.target.value); setPage(1); }} placeholder="Customer, chassis, ticket, or issue" /></label>{user.role !== "SERVICE" && <label>Branch<select value={branch} onChange={e => { setBranch(e.target.value); setPage(1); }}><option value="">All branches</option>{branches.map(value => <option key={value}>{value}</option>)}</select></label>}<label>From<input type="date" value={dateFrom} onChange={e => { setDateFrom(e.target.value); setPage(1); }} /></label><label>To<input type="date" value={dateTo} min={dateFrom} onChange={e => { setDateTo(e.target.value); setPage(1); }} /></label></div>
      <div className="service-table-wrap"><table className="service-table"><thead><tr><th>Request / customer</th><th>Scooter / issue</th><th>Branch</th><th>Status</th><th>Received</th></tr></thead><tbody>{rows.results.map(row => <tr key={row.id}><td><button className="service-ticket" onClick={() => void open(row.id)}>{row.ticket_number}</button><b>{row.customer_snapshot.customer_name}</b><small>{row.customer_snapshot.customer_phone}</small></td><td><b className="service-chassis">{row.vehicle_snapshot.chassis_number}</b><span className="service-issue-preview">{row.issue}</span><small>{row.vehicle_snapshot.model}</small></td><td>{row.branch}{!row.branch_staff_available && !["RESOLVED", "CANCELLED"].includes(row.status) && <small className="service-no-staff">No active service staff</small>}</td><td><span className={`service-status status-${row.status}`}>{serviceStatuses[row.status]}</span><small>{row.priority}</small></td><td>{formatDateTime(row.created_at)}</td></tr>)}</tbody></table></div>
      {!rows.results.length && <p className="service-empty">{loading ? "Loading service requests…" : "No requests match this view."}</p>}
      <footer><span>{rows.count} requests · Page {page}</span><div className="service-inline"><button className="filter" disabled={!rows.previous} onClick={() => setPage(value => value - 1)}>Previous</button><button className="filter" disabled={!rows.next} onClick={() => setPage(value => value + 1)}>Next</button></div></footer>
    </section>
  </div>;
}
