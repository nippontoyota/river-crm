"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, type LeadDetail } from "@/lib/crm";
import { getVehicle, type Page, type ServiceRequest, type Vehicle, serviceStatuses } from "@/lib/service";
import { formatDateTime } from "@/lib/dates";

export function ServiceHistory({ rows }: { rows: ServiceRequest[] }) {
  return <div className="service-history">{rows.length ? rows.map(row => <article key={row.id}>
    <header><b>{row.ticket_number} · {row.branch}</b><span className={`service-status status-${row.status}`}>{serviceStatuses[row.status]}</span></header>
    <small>{formatDateTime(row.created_at)} · {row.created_by_name}</small><p>{row.issue}</p>
    {row.resolution_notes && <p><b>Resolution:</b> {row.resolution_notes}</p>}
    {!!row.events?.length && <details><summary>Progress and notes</summary>{row.events.map(event => <p key={event.id}><b>{event.action} · {event.actor_name}</b><br /><small>{formatDateTime(event.created_at)}</small>{event.note && <><br />{event.note}</>}</p>)}</details>}
  </article>) : <p className="subtext">No previous service requests.</p>}</div>;
}

export function VehicleRegistration({ chassis = "", lead, onSaved, onCancel }: { chassis?: string; lead?: LeadDetail; onSaved: (vehicle: Vehicle) => void; onCancel?: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setBusy(true); setError("");
    const data = Object.fromEntries(new FormData(event.currentTarget));
    try { onSaved(await api<Vehicle>("/api/vehicles/", { method: "POST", body: JSON.stringify({ ...data, ...(lead ? { related_lead: lead.id } : {}) }) })); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to register scooter."); }
    finally { setBusy(false); }
  };
  return <form className="service-form" onSubmit={save}><h3>Register scooter</h3>
    <div className="service-grid"><label>Chassis number<input name="chassis_number" required maxLength={64} defaultValue={chassis} autoCapitalize="characters" /></label>
    <label>Model<input name="model" required maxLength={100} defaultValue={lead?.model || ""} /></label>
    <label>Registration number <small>Optional</small><input name="registration_number" maxLength={30} /></label>
    {!lead && <><label>Customer name<input name="customer_name" required maxLength={160} /></label><label>Phone<input name="customer_phone" type="tel" required pattern="[0-9]{10}" maxLength={10} /></label><label>Email <small>Optional</small><input name="customer_email" type="email" /></label></>}
    </div>{lead && <p className="subtext">Linked to {lead.name} · {lead.phone}. Customer details come from this sale.</p>}
    {error && <p role="alert" className="service-error">{error}</p>}<footer>{onCancel && <button type="button" className="filter" onClick={onCancel}>Cancel</button>}<button className="button primary" disabled={busy}>{busy ? "Saving…" : "Register scooter"}</button></footer>
  </form>;
}

export function VehiclePanel({ lead }: { lead: LeadDetail }) {
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [selected, setSelected] = useState<Vehicle | null>(null);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { let alive = true; api<Page<Vehicle>>(`/api/vehicles/?lead=${lead.id}`).then(data => { if (alive) setVehicles(data.results); }).catch(e => { if (alive) setError(e.message); }); return () => { alive = false; }; }, [lead.id]);
  return <section className="service-vehicle-panel"><header><div><h3>Vehicle & service history</h3><p className="subtext">Record the chassis before marking this sale Retailed.</p></div><button type="button" className="filter" onClick={() => setAdding(true)}>＋ Add scooter</button></header>
    {error && <p role="alert">{error}</p>}
    {vehicles.map(vehicle => <button type="button" className="service-vehicle-choice" key={vehicle.id} onClick={() => void getVehicle(vehicle).then(setSelected).catch(e => setError(e.message))}><b>{vehicle.chassis_number}</b><span>{vehicle.model} · {vehicle.registration_number || "Registration pending"}</span></button>)}
    {!vehicles.length && <p className="subtext">No chassis recorded yet.</p>}
    {adding && <VehicleRegistration lead={lead} onSaved={vehicle => { setVehicles(rows => [vehicle, ...rows]); setAdding(false); }} onCancel={() => setAdding(false)} />}
    {selected && <><h4>{selected.chassis_number} · Service history</h4><ServiceHistory rows={selected.history || []} /></>}
  </section>;
}
