"use client";

import { useState } from "react";
import type { AccountStatus, LeadOwnership } from "@/lib/crm";

export function ownerState(status: AccountStatus | null, needsReassignment: boolean) {
  if (needsReassignment) return "Awaiting reassignment";
  if (!status) return "Not assigned";
  return status === "ACTIVE" ? "Active" : "Inactive owner";
}

function ContactNumber({ phone, available = true }: { phone: string; available?: boolean }) {
  const [message, setMessage] = useState("");
  if (!phone.trim()) return <p className="subtext">Phone not recorded</p>;
  const copy = async () => {
    try { await navigator.clipboard.writeText(phone); setMessage("Number copied."); }
    catch { setMessage("Unable to copy. Select the number and copy it manually."); }
  };
  return <div className="ownership-contact">
    <span>{phone}</span>
    {available ? <div className="ownership-actions"><a className="filter" href={`tel:${phone.replace(/[^+0-9]/g, "")}`}>Call</a><button type="button" className="filter" onClick={() => void copy()}>Copy number</button></div> : <small>Unavailable for contact</small>}
    {message && <small role="status">{message}</small>}
  </div>;
}

export function LeadOwnershipPanel({ ownership }: { ownership: LeadOwnership }) {
  const owner = ownership.assigned_ps;
  const state = ownerState(owner?.lifecycle_status ?? null, ownership.needs_so_reassignment);
  return <section className="sales-info-card ownership-panel" aria-label="Ownership & contacts">
    <h3>Ownership &amp; contacts</h3>
    <div className="ownership-grid">
      <div><h4>Assigned PS/SO</h4><b>{owner?.name || state}</b>
        {owner && <><p>{state} · Account {owner.lifecycle_status === "ACTIVE" ? "active" : owner.lifecycle_status === "DELETED" ? "deleted" : "disabled"}</p><p>PS branch: {owner.branch || "Not recorded"}</p><ContactNumber key={`${owner.id}-${owner.phone}`} phone={owner.phone} available={state === "Active"} /></>}
      </div>
      <div><h4>Branch managers</h4><p>Branch: {ownership.manager_branch || "Not recorded"}{!ownership.branch.trim() && ownership.manager_branch ? " (PS branch)" : ""}</p>
        {ownership.managers.length ? ownership.managers.map(manager => <div className="ownership-manager" key={manager.id}><b>{manager.name}</b><ContactNumber phone={manager.phone} /></div>) : <p>No branch manager configured—contact admin</p>}
      </div>
    </div>
  </section>;
}
