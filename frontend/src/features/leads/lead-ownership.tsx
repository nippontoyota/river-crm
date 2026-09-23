"use client";

import { useState } from "react";
import type { AccountStatus, LeadOwnership } from "@/lib/crm";

export function ownerState(status: AccountStatus | null, needsReassignment: boolean) {
  if (needsReassignment) return "Awaiting reassignment";
  if (!status) return "Not assigned";
  return status === "ACTIVE" ? "Active" : "Inactive owner";
}

function ContactNumber({ label, phone, available = true }: { label: string; phone: string; available?: boolean }) {
  const [message, setMessage] = useState("");
  if (!phone.trim()) return <p><strong>{label}:</strong> Not recorded</p>;
  const copy = async () => {
    try { await navigator.clipboard.writeText(phone); setMessage("Number copied."); }
    catch { setMessage("Unable to copy. Select the number and copy it manually."); }
  };
  return <div className="ownership-contact">
    <p><strong>{label}:</strong> {phone}</p>
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
      <div><p><strong>Assigned PS/SO:</strong> {owner?.name || state}</p>
        {owner && <><p><strong>Account status:</strong> {owner.lifecycle_status === "ACTIVE" ? "Active" : owner.lifecycle_status === "DELETED" ? "Deleted" : "Disabled"}</p>{state !== "Active" && <p><strong>Assignment status:</strong> {state}</p>}<p><strong>PS branch:</strong> {owner.branch || "Not recorded"}</p><ContactNumber key={`${owner.id}-${owner.phone}`} label="PS phone" phone={owner.phone} available={state === "Active"} /></>}
      </div>
      <div>
        {ownership.managers.length ? ownership.managers.map(manager => <div className="ownership-manager" key={manager.id}><p><strong>Branch manager:</strong> {manager.name}</p><p><strong>Manager branch:</strong> {ownership.manager_branch || "Not recorded"}{!ownership.branch.trim() && ownership.manager_branch ? " (PS branch)" : ""}</p><ContactNumber label="Manager phone" phone={manager.phone} /></div>) : <><p><strong>Branch manager:</strong> No branch manager configured—contact admin</p><p><strong>Manager branch:</strong> {ownership.manager_branch || "Not recorded"}</p></>}
      </div>
    </div>
  </section>;
}
