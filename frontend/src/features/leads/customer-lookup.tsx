"use client";

import { useEffect, useRef, useState } from "react";
import { lookupCustomer, statusName, type CustomerLookupPage } from "@/lib/crm";
import { formatDate } from "@/lib/dates";
import { LeadOwnershipPanel, ownerState } from "./lead-ownership";

export function CustomerLookup({ onClose, onOpenLead }: { onClose: () => void; onOpenLead: (lead: { id: number }) => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const request = useRef(0);
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

  const search = async (value: string, nextPage = 1) => {
    const current = ++request.current;
    setLoading(true); setError(""); setResult(null);
    try {
      const data = await lookupCustomer(value, nextPage);
      if (current !== request.current) return;
      setResult(data); setPage(nextPage); setSearchedPhone(value);
    } catch (requestError) {
      if (current === request.current) setError(requestError instanceof Error ? requestError.message : "Unable to look up this customer. Try again.");
    } finally { if (current === request.current) setLoading(false); }
  };

  return <dialog ref={dialog} className="modal sales-detail-modal customer-lookup-modal" aria-labelledby="customer-lookup-title" onCancel={onClose}>
    <header className="sales-detail-header"><div><h2 id="customer-lookup-title">Customer lookup</h2><p className="subtext">Find enquiries across all branches using a complete customer phone number.</p></div><button type="button" className="modal-close" onClick={onClose} aria-label="Close customer lookup">×</button></header>
    <div className="sales-detail-scroll">
      <form className="sales-form-card customer-lookup-form" onSubmit={event => { event.preventDefault(); void search(phone.trim()); }}>
        <label>Customer phone number<input type="tel" autoComplete="tel" required maxLength={40} value={phone} onChange={event => setPhone(event.target.value)} placeholder="10 digits or +91" disabled={loading} /></label>
        <button className="button primary" disabled={loading}>{loading ? "Searching…" : "Search"}</button>
      </form>
      {loading && <p role="status">Looking up enquiries…</p>}
      {error && <p className="form-error" role="alert">{error}</p>}
      {result && <>
        <p role="status">{result.count ? `${result.count} matching ${result.count === 1 ? "enquiry" : "enquiries"} for ${searchedPhone}` : `No enquiries found for ${searchedPhone}.`}</p>
        {result.results.map(lead => <article className="customer-lookup-result" key={lead.id}>
          <header><div><h3>{lead.name}</h3><p>Lead #{String(lead.id).padStart(6, "0")} · {statusName(lead.status)}</p></div>{lead.can_open && <button type="button" className="filter" onClick={() => onOpenLead(lead)}>Open lead</button>}</header>
          <dl className="lookup-facts"><div><dt>Customer phone</dt><dd>{lead.phone}</dd></div><div><dt>Enquiry date</dt><dd>{formatDate(lead.enquiry_date) || "Not recorded"}</dd></div><div><dt>Branch</dt><dd>{lead.branch || "Not recorded"}</dd></div><div><dt>Assigned CE</dt><dd>{lead.assigned_ce?.name || ownerState(null, lead.needs_cre_reassignment)}{lead.assigned_ce && (lead.needs_cre_reassignment || lead.assigned_ce.lifecycle_status !== "ACTIVE") && <small>{ownerState(lead.assigned_ce.lifecycle_status, lead.needs_cre_reassignment)}</small>}</dd></div></dl>
          <LeadOwnershipPanel ownership={lead.ownership} />
          {!lead.can_open && <p className="subtext">Team enquiry · Ownership information only</p>}
        </article>)}
        {(result.next || result.previous) && <nav className="lead-pagination" aria-label="Customer lookup pages"><span>Page {page}</span><div><button type="button" className="filter" disabled={loading || !result.previous} onClick={() => void search(searchedPhone, page - 1)}>Previous</button><button type="button" className="filter" disabled={loading || !result.next} onClick={() => void search(searchedPhone, page + 1)}>Next</button></div></nav>}
      </>}
    </div>
  </dialog>;
}
