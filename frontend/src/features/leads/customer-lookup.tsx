"use client";

import { useEffect, useRef, useState } from "react";
import { lookupCustomer, statusName, type CustomerLookupPage } from "@/lib/crm";
import { formatDate } from "@/lib/dates";
import { LeadOwnershipPanel, ownerState } from "./lead-ownership";

export function CustomerLookup({ onClose, onOpenLead, onUnmatched }: { onUnmatched?: () => void; onClose: () => void; onOpenLead: (lead: { id: number }) => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const request = useRef(0);
  const [searchBy, setSearchBy] = useState("phone");
  const [submittedMode, setSubmittedMode] = useState("phone");
  const [phone, setPhone] = useState("");
  const [searchedPhone, setSearchedPhone] = useState("");
  const [result, setResult] = useState<CustomerLookupPage | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const node = dialog.current;
    const requests = request;
    node?.showModal();
    return () => { requests.current++; node?.close(); };
  }, []);

  const search = async (value: string, nextPage = 1, mode = searchBy) => {
    const current = ++request.current;
    setLoading(true); setError(""); setResult(null);
    try {
      const data = await lookupCustomer(value, nextPage, mode);
      if (current !== request.current) return;
      setResult(data); setPage(nextPage); setSearchedPhone(value); setSubmittedMode(mode);
    } catch (requestError) {
      if (current === request.current) setError(requestError instanceof Error ? requestError.message : "Unable to look up this customer. Try again.");
    } finally { if (current === request.current) setLoading(false); }
  };

  return <dialog ref={dialog} className="modal sales-detail-modal customer-lookup-modal" aria-labelledby="customer-lookup-title" onCancel={onClose}>
    <header className="sales-detail-header"><div><h2 id="customer-lookup-title">Find customer across all branches</h2><p className="subtext">Search by registered phone, customer name, or lead ID. Select the enquiry confirmed by the caller.</p></div><button type="button" className="modal-close" onClick={onClose} aria-label="Close customer lookup">×</button></header>
    <div className="sales-detail-scroll">
      <form className="sales-form-card customer-lookup-form" onSubmit={event => { event.preventDefault(); void search(phone.trim()); }}>
        <label>Search by<select value={searchBy} onChange={event => setSearchBy(event.target.value)} disabled={loading}><option value="phone">Registered phone</option><option value="name">Customer name</option><option value="lead_id">Lead ID</option></select></label><label>{searchBy === "phone" ? "Customer phone number" : searchBy === "name" ? "Customer name" : "Lead ID"}<input type={searchBy === "phone" ? "tel" : "text"} required maxLength={160} value={phone} onChange={event => setPhone(event.target.value)} placeholder={searchBy === "phone" ? "10 digits or +91" : searchBy === "name" ? "At least 3 characters" : "e.g. #000123"} disabled={loading} /></label>
        <button className="button primary" disabled={loading}>{loading ? "Searching…" : "Search"}</button>
      </form>
      {loading && <p role="status">Looking up enquiries…</p>}
      {error && <p className="form-error" role="alert">{error}</p>}
      {result && <>
        <p role="status">{result.count ? `${result.count} matching ${result.count === 1 ? "enquiry" : "enquiries"} for ${searchedPhone}` : `No enquiries found for ${searchedPhone}.`}</p>
        {result.results.map(lead => <article className="customer-lookup-result" key={lead.id}>
          <header><div><h3>{lead.name}</h3><p>Lead #{String(lead.id).padStart(6, "0")} · {statusName(lead.status)}</p></div>{lead.can_open && <button type="button" className="filter" onClick={() => onOpenLead(lead)}>Select enquiry</button>}</header>
          <dl className="lookup-facts"><div><dt>Customer phone</dt><dd>{lead.phone}</dd></div><div><dt>Enquiry date</dt><dd>{formatDate(lead.enquiry_date) || "Not recorded"}</dd></div><div><dt>Branch</dt><dd>{lead.branch || "Not recorded"}</dd></div><div><dt>Assigned CE</dt><dd>{lead.assigned_ce?.name || ownerState(null, lead.needs_cre_reassignment)}{lead.assigned_ce && (lead.needs_cre_reassignment || lead.assigned_ce.lifecycle_status !== "ACTIVE") && <small>{ownerState(lead.assigned_ce.lifecycle_status, lead.needs_cre_reassignment)}</small>}</dd></div></dl>
          <LeadOwnershipPanel ownership={lead.ownership} />
          {!lead.can_open && <p className="subtext">Shared enquiry · Assigned ownership is unchanged</p>}
        </article>)}
        {(result.next || result.previous) && <nav className="lead-pagination" aria-label="Customer lookup pages"><span>Page {page}</span><div><button type="button" className="filter" disabled={loading || !result.previous} onClick={() => void search(searchedPhone, page - 1, submittedMode)}>Previous</button><button type="button" className="filter" disabled={loading || !result.next} onClick={() => void search(searchedPhone, page + 1, submittedMode)}>Next</button></div></nav>}
      </>}
      {onUnmatched && <button type="button" className="filter" onClick={onUnmatched}>Cannot identify enquiry · Record unmatched call</button>}
    </div>
  </dialog>;
}
