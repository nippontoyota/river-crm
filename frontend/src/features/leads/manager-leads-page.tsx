"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getLeadDetail, getManagerLeads, getSystemConfig, sourceName, statusName, type Lead, type LeadDetail } from "@/lib/crm";
import { DateInput } from "@/components/date-input";
import { formatDate, formatDateTime, todayInIST, toDateInputValue } from "@/lib/dates";

const emptyFilters = { q: "", source: "", status: "", model: "", category: "", cre: "", ps: "", date_from: "", date_to: "", range: "", sales_outcome: "", flagged: "", followup: "", risk: "", status_group: "" };

function initialFilters(initialQuery: string) {
  const params = new URLSearchParams(initialQuery);
  return {
    q: params.get("q") || "",
    source: params.get("source") || "",
    status: params.get("status") || "",
    model: params.get("model") || "",
    category: params.get("category") || "",
    cre: params.get("cre") || "",
    ps: params.get("ps") || "",
    date_from: formatDate(params.get("date_from")),
    date_to: formatDate(params.get("date_to")),
    range: params.get("range") || "",
    sales_outcome: params.get("sales_outcome") || "",
    flagged: params.get("flagged") || "",
    followup: params.get("followup") || "",
    risk: params.get("risk") || "",
    status_group: params.get("status_group") || "",
  };
}

export function ManagerLeadsPage({ initialQuery = "" }: { initialQuery?: string }) {
  const [filters, setFilters] = useState(() => initialFilters(initialQuery));
  const today = todayInIST();
  const selectedTo = toDateInputValue(filters.date_to);
  const historicalFromMax = selectedTo && selectedTo < today ? filters.date_to : today;
  const [page, setPage] = useState<{ count: number; next: string | null; previous: string | null; results: Lead[] } | null>(null);
  const [detail, setDetail] = useState<LeadDetail | null>(null);
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [sourceOptions, setSourceOptions] = useState<string[]>(["WALKIN"]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const requestId = useRef(0);
  const query = useMemo(() => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (!value) return;
      if (key.startsWith("date_") && !toDateInputValue(value)) return;
      params.set(key, key.startsWith("date_") ? toDateInputValue(value) : value);
    });
    return params.toString();
  }, [filters]);
  const setFilter = (key: keyof typeof filters, value: string) => setFilters(current => ({ ...current, [key]: value }));
  const load = useCallback(async () => { const request = ++requestId.current; setLoading(true); setError(""); try { const result = await getManagerLeads(query); if (request === requestId.current) setPage(result); } catch (err) { if (request === requestId.current) setError(err instanceof Error ? err.message : "Unable to load branch leads."); } finally { if (request === requestId.current) setLoading(false); } }, [query]);
  useEffect(() => { void getSystemConfig().then(config => { setModelOptions(config.lists.models || []); setSourceOptions(config.lists.sources || ["WALKIN"]); }).catch(() => { setModelOptions([]); setSourceOptions(["WALKIN"]); }); }, []);
  useEffect(() => { const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, [load]);
  useEffect(() => { const suffix = query ? `?${query}` : ""; window.history.replaceState(null, "", `/manager/leads${suffix}`); }, [query]);
  const openLead = (lead: Lead) => void getLeadDetail(lead.id).then(setDetail).catch(err => setError(err instanceof Error ? err.message : "Unable to load lead details."));

  return <section className="page manager-page manager-leads-page">
    <div className="sales-hero manager-hero"><div><p className="eyebrow">BRANCH LEADS</p><h1>Read-only pipeline <span>review</span></h1><p className="subtext">Every row is scoped to your branch. Use analytics drilldowns or filters to inspect the branch pipeline.</p></div><button className="filter" onClick={() => void load()}>Refresh</button></div>
    {error && <div className="empty-state">{error}</div>}
    <section className="panel manager-filter-bar manager-lead-filters"><label>Search<input value={filters.q} onChange={event => setFilter("q", event.target.value)} placeholder="Name, phone, model" /></label><label>Source<select value={filters.source} onChange={event => setFilter("source", event.target.value)}><option value="">All sources</option>{sourceOptions.map(item => <option value={item} key={item}>{sourceName(item)}</option>)}</select></label><label>Status<select value={filters.status} onChange={event => setFilter("status", event.target.value)}><option value="">All statuses</option>{["FRESH", "RNR", "SWITCHED_OFF", "CALLBACK", "PENDING", "QUALIFIED", "WALKIN", "WON", "LOST", "UNQUALIFIED"].map(item => <option value={item} key={item}>{statusName(item)}</option>)}</select></label><label>Category<select value={filters.category} onChange={event => setFilter("category", event.target.value)}><option value="">All categories</option><option value="HOT">Hot</option><option value="WARM">Warm</option><option value="COLD">Cold</option></select></label><label>Model<select value={filters.model} onChange={event => setFilter("model", event.target.value)}><option value="">{modelOptions.length ? "All models" : "No admin models"}</option>{modelOptions.map(item => <option value={item} key={item}>{item}</option>)}</select></label><label>From<DateInput value={filters.date_from} max={historicalFromMax} onChange={value => setFilter("date_from", value)} ariaLabel="From date, DD/MM/YYYY" /></label><label>To<DateInput value={filters.date_to} min={filters.date_from || undefined} max={today} onChange={value => setFilter("date_to", value)} ariaLabel="To date, DD/MM/YYYY" /></label><button className="filter" onClick={() => setFilters({ ...emptyFilters })}>Clear</button></section>
    <article className="panel sales-table-panel manager-table-card"><header className="sales-table-heading"><div><p className="eyebrow">FILTERED LEADS</p><h2>{loading ? "Loading..." : `${page?.count || 0} branch leads`}</h2></div></header><div className="sales-table-scroll"><table className="sales-table manager-table"><thead><tr><th>Lead</th><th>Customer</th><th>Source</th><th>Model</th><th>CRE</th><th>PS/SO</th><th>Status</th><th>Outcome</th><th>Enquiry</th><th>Action</th></tr></thead><tbody>{loading ? <tr><td colSpan={10} className="sales-empty">Loading...</td></tr> : page?.results.length ? page.results.map(lead => <tr key={lead.id}><td><b>#{String(lead.id).padStart(6, "0")}</b><small>{lead.branch || "No branch"}</small></td><td><b>{lead.name}</b><small>{lead.phone}</small></td><td>{lead.source}</td><td>{lead.model}</td><td>{lead.assignedSoName || "-"}</td><td>{lead.assignedPsName || "-"}</td><td><span className={`sales-status ${lead.statusCode.toLowerCase()}`}>{lead.status}</span></td><td>{lead.salesOutcome}</td><td>{lead.enquiredAt || "-"}</td><td><button className="sales-row-action" onClick={() => openLead(lead)}>Open</button></td></tr>) : <tr><td colSpan={10} className="sales-empty"><strong>No branch leads match these filters.</strong><span>Clear filters or return from analytics.</span></td></tr>}</tbody></table></div></article>
    {detail && <div className="modal-layer" role="presentation"><section className="modal sales-detail-modal manager-detail-modal" role="dialog" aria-modal="true" aria-labelledby="manager-lead-detail"><header className="sales-detail-header"><div><p className="eyebrow">READ ONLY</p><h2 id="manager-lead-detail">{detail.name}</h2><p className="subtext">{detail.phone} - {detail.model} - {detail.branch || "No branch"}</p></div><button className="modal-close" onClick={() => setDetail(null)} aria-label="Close">×</button></header><div className="sales-detail-scroll"><section className="sales-info-card"><h3>Lead details</h3><div className="sales-info-grid"><span><small>Status</small><b>{detail.status}</b></span><span><small>Sales outcome</small><b>{detail.salesOutcome}</b></span><span><small>Source</small><b>{detail.source}</b></span><span><small>CRE</small><b>{detail.assignedSoName || "-"}</b></span><span><small>PS/SO</small><b>{detail.assignedPsName || "-"}</b></span><span><small>Enquiry date</small><b>{detail.enquiredAt || "-"}</b></span></div></section><section className="sales-history"><h3>Call history</h3>{detail.callHistory.length ? detail.callHistory.map(call => <div className="sales-history-row" key={call.id}><span className="history-dot" /><div><b>{call.outcome || statusName(call.status)}</b><small>{call.remarks || "No remarks"}</small><small>By {call.so_name || "-"} - {formatDateTime(call.created_at)}</small></div></div>) : <p className="subtext">No calls recorded.</p>}</section><section className="sales-history"><h3>Follow-ups</h3>{detail.followUpHistory.length ? detail.followUpHistory.map(item => <div className="sales-history-row" key={item.id}><span className="history-dot follow" /><div><b>{formatDateTime(item.scheduled_for)}</b><small>{item.resolved_at ? `Resolved ${formatDateTime(item.resolved_at)}` : "Open"}</small></div></div>) : <p className="subtext">No follow-ups recorded.</p>}</section></div><footer className="sales-detail-footer"><button className="button primary" onClick={() => setDetail(null)}>Close</button></footer></section></div>}
  </section>;
}
