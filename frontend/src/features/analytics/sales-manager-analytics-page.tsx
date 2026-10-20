"use client";
import { useCrmRefresh } from "@/lib/use-crm-refresh";

import { EtbrTiles } from "@/components/etbr-tiles";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { exportSalesManagerAnalytics, getLeadDetail, getManagerLeads, getSalesManagerAnalytics, getSalesManagerPSFollowups, getSystemConfig, managerStatusName, sourceName, type Lead, type LeadDetail, type ManagerAnalytics, type ManagerFilterOption, type ManagerPerformanceRow, type ManagerPSFollowupRow, type ManagerRoleRow } from "@/lib/crm";
import { DateInput } from "@/components/date-input";
import { formatDate, formatDateTime, todayInIST, toDateInputValue } from "@/lib/dates";

const metricFilters: Record<string, Record<string, string>> = {
  untouched: { ps_handling: "untouched" },
  booked: { sales_outcome: "BOOKED" },
  retailed: { sales_outcome: "RETAILED" },
  lost: { status_group: "lost_or_unqualified" },
  conversion: { sales_outcome: "RETAILED" },
};

function metricDelta(value?: number) {
  if (!value) return "0";
  return `${value > 0 ? "+" : ""}${value}`;
}

function leadHref(filters: Record<string, string>, extra: Record<string, string> = {}) {
  const params = new URLSearchParams({ ...filters, ...extra });
  return `/manager/leads${params.toString() ? `?${params}` : ""}`;
}

function RoleTable({ rows, filters, onExport }: { rows: ManagerRoleRow[]; filters: Record<string, string>; onExport: (section: string) => void }) {
  const router = useRouter();
  return <article className="panel manager-table-card"><header className="manager-card-head"><div><p className="eyebrow">SALES CONVERSION</p><h2>PS/SO performance</h2></div><button className="filter" onClick={() => onExport("ps")}>Export CSV</button></header><div className="manager-table-scroll"><table className="sales-table manager-table"><thead><tr><th>Name</th><th>Total</th><th>Calls</th><th>Booked</th><th>Retailed</th><th>Lost</th><th>Conv.</th><th>Last call</th></tr></thead><tbody>{rows.length ? rows.map(row => { const href = leadHref(filters, { ps: String(row.id) }); return <tr className="manager-clickable-row" key={row.id} role="link" tabIndex={0} onClick={() => router.push(href)} onKeyDown={event => { if (event.key === "Enter") router.push(href); }}><td><b>{row.name}</b><small>{row.email}</small></td><td>{row.total}</td><td>{row.calls}</td><td>{row.booked}</td><td>{row.retailed}</td><td>{row.lost}</td><td><span className="manager-rate">{row.conversion_rate}%</span></td><td>{formatDateTime(row.last_activity) || "-"}</td></tr>; }) : <tr><td colSpan={8} className="sales-empty">No users have branch activity in this period.</td></tr>}</tbody></table></div></article>;
}

function PerformanceTable({ title, section, labelKey, rows, filters, onExport }: { title: string; section: "source" | "colors"; labelKey: "source" | "color"; rows: (ManagerPerformanceRow & Record<string, string | number>)[]; filters: Record<string, string>; onExport: (section: string) => void }) {
  const router = useRouter();
  return <article className="panel manager-table-card"><header className="manager-card-head"><div><p className="eyebrow">CONVERSION MIX</p><h2>{title}</h2></div><button className="filter" onClick={() => onExport(section)}>Export CSV</button></header><div className="manager-table-scroll"><table className="sales-table manager-table"><thead><tr><th>{labelKey === "source" ? "Source" : "Color"}</th><th>Total</th><th>Booked</th><th>Retailed</th><th>Lost</th><th>Conv.</th></tr></thead><tbody>{rows.length ? rows.map(row => { const name = String(row[labelKey] || "Unknown"); const clickable = labelKey === "source" || name !== "Color not set"; const href = leadHref(filters, { [labelKey]: name }); return <tr className={clickable ? "manager-clickable-row" : ""} key={name} role={clickable ? "link" : undefined} tabIndex={clickable ? 0 : undefined} onClick={clickable ? () => router.push(href) : undefined} onKeyDown={clickable ? event => { if (event.key === "Enter") router.push(href); } : undefined}><td><b>{labelKey === "source" ? sourceName(name) : name}</b></td><td>{row.total}</td><td>{row.booked}</td><td>{row.retailed}</td><td>{row.lost}</td><td><span className="manager-rate">{row.conversion_rate}%</span></td></tr>; }) : <tr><td colSpan={6} className="sales-empty">No rows for this period.</td></tr>}</tbody></table></div></article>;
}

function LostLeadAnalysis({ total, reasons, filters, refreshKey }: { total: number; reasons: ManagerAnalytics["lost_reasons"]; filters: Record<string, string>; refreshKey: number }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [page, setPage] = useState<{ count: number; next: string | null; previous: string | null; results: Lead[] } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [openLeadId, setOpenLeadId] = useState<number | null>(null);
  const [detail, setDetail] = useState<LeadDetail | null>(null);
  const [detailError, setDetailError] = useState("");
  const detailRequest = useRef(0);
  const baseQuery = new URLSearchParams(filters).toString();
  useEffect(() => {
    if (!selected) return;
    let active = true;
    const query = new URLSearchParams(baseQuery);
    query.set("status_group", "lost_or_unqualified");
    query.set("lost_reason", selected);
    query.set("page", String(pageNumber));
    void getManagerLeads(query.toString()).then(result => { if (active) { setPage(result); setError(""); } })
      .catch(err => { if (active) setError(err instanceof Error ? err.message : "Unable to load lost leads."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [baseQuery, pageNumber, refreshKey, selected]);

  const openHistory = async (id: number) => {
    const request = ++detailRequest.current;
    setOpenLeadId(id); setDetail(null); setDetailError("");
    try { const result = await getLeadDetail(id); if (request === detailRequest.current) setDetail(result); }
    catch (err) { if (request === detailRequest.current) setDetailError(err instanceof Error ? err.message : "Unable to load lead history."); }
  };
  const closeHistory = () => { detailRequest.current += 1; setOpenLeadId(null); setDetail(null); };

  return <section id="manager-section-overview" className="panel manager-lost-analysis manager-section">
    <header className="manager-card-head"><div><p className="eyebrow">OVERVIEW</p><h2>Lost lead analysis</h2><p className="subtext">{total} lost {total === 1 ? "lead" : "leads"} in this period. Select a reason to see its leads and their history.</p></div></header>
    {reasons.length ? <div className="manager-lost-buckets">{reasons.map(({ reason, count }) => <button key={reason} type="button" className={selected === reason ? "active" : ""} aria-pressed={selected === reason} onClick={() => { setSelected(selected === reason ? null : reason); setPageNumber(1); setPage(null); setError(""); setLoading(selected !== reason); }}><span><b>{reason}</b><small>{total ? Math.round(count / total * 100) : 0}% of lost leads</small></span><strong>{count}</strong></button>)}</div> : <p className="subtext">No lost leads match these filters.</p>}
    {selected && <><div className="manager-lost-detail-head"><h3>{selected} · {page?.count ?? reasons.find(row => row.reason === selected)?.count ?? 0} leads</h3><button type="button" className="filter" onClick={() => { setSelected(null); setPage(null); setError(""); }}>Close</button></div>
    {error && <p className="manager-followups-error" role="alert">{error}</p>}
    <div className="manager-table-scroll"><table className="sales-table manager-table"><thead><tr><th>Lead</th><th>Customer</th><th>PS/SO</th><th>Status</th><th>Enquiry</th><th>History</th></tr></thead><tbody>{loading ? <tr><td colSpan={6} className="sales-empty">Loading lost leads...</td></tr> : error ? <tr><td colSpan={6} className="sales-empty">Unable to load lost leads.</td></tr> : page?.results.length ? page.results.map(lead => <tr key={lead.id}><td>#{String(lead.id).padStart(6, "0")}</td><td><b>{lead.name}</b><small>{lead.phone}</small></td><td>{lead.assignedPsName || "—"}</td><td><span className={`sales-status ${lead.statusCode.toLowerCase()}`}>{managerStatusName(lead.statusCode)}</span></td><td>{lead.enquiredAt || "—"}</td><td><button type="button" className="sales-row-action" onClick={() => void openHistory(lead.id)}>Open history</button></td></tr>) : <tr><td colSpan={6} className="sales-empty">No lost leads match these filters.</td></tr>}</tbody></table></div>
    {page && (page.previous || page.next) && <div className="manager-lost-pagination"><span>Page {pageNumber} · {page.count} leads</span><div><button type="button" className="filter" disabled={!page.previous || loading} onClick={() => { setPageNumber(current => current - 1); setPage(null); setLoading(true); }}>Previous</button><button type="button" className="filter" disabled={!page.next || loading} onClick={() => { setPageNumber(current => current + 1); setPage(null); setLoading(true); }}>Next</button></div></div>}</>}
    {openLeadId !== null && <div className="modal-layer" role="presentation"><section className="modal sales-detail-modal manager-detail-modal" role="dialog" aria-modal="true" aria-labelledby="manager-lost-history-title"><button className="modal-close" onClick={closeHistory} aria-label="Close">×</button>{detail ? <><header className="sales-detail-header"><div><p className="eyebrow">LEAD HISTORY</p><h2 id="manager-lost-history-title">{detail.name}</h2><p className="subtext">{detail.phone} · {managerStatusName(detail.statusCode)} · {detail.assignedPsName || "No PS assigned"}</p></div></header><div className="sales-detail-scroll"><section className="sales-history"><h3>Call history</h3>{detail.callHistory.length ? detail.callHistory.map(call => <div className="sales-history-row" key={call.id}><span className="history-dot" /><div><b>{managerStatusName(call.outcome || call.status)}</b><small>{call.remarks || "No remarks"}</small><small>By {call.so_name || "—"} · {formatDateTime(call.created_at)}</small></div></div>) : <p className="subtext">No calls recorded.</p>}</section><section className="sales-history"><h3>Follow-ups</h3>{detail.followUpHistory.length ? detail.followUpHistory.map(item => <div className="sales-history-row" key={item.id}><span className="history-dot follow" /><div><b>{formatDateTime(item.scheduled_for)}</b><small>{item.resolved_at ? `Resolved ${formatDateTime(item.resolved_at)}` : "Open"}</small></div></div>) : <p className="subtext">No follow-ups recorded.</p>}</section><section className="sales-history"><h3>Activity history</h3>{detail.auditHistory.length ? detail.auditHistory.map((item, index) => <div className="sales-history-row" key={index}><span className="history-dot" /><div><b>{item.event.replaceAll("_", " ")}</b><small>{item.actor || "System"} · {formatDateTime(item.created_at)}</small></div></div>) : <p className="subtext">No activity recorded.</p>}</section></div></> : <div className="sales-detail-scroll"><h2 id="manager-lost-history-title">Lead history</h2><p role={detailError ? "alert" : undefined}>{detailError || "Loading lead history..."}</p></div>}</section></div>}
  </section>;
}

const psFollowupColumns = [
  ["total", "Total Leads", "total_leads"],
  ["test_drive", "Test Drive", "test_drive"],
  ["unattended", "Unattended", "unattended"],
  ["overdue", "Overdue", "overdue"],
  ["f1", "F1", "f1"],
  ["f2", "F2", "f2"],
  ["f3", "F3", "f3"],
  ["f4", "F4", "f4"],
  ["f5", "F5", "f5"],
] as const;

function PSFollowupsSection({ filters, primaryPs, setPrimaryPs, officers, refreshKey }: { filters: Record<string, string>; primaryPs: string; setPrimaryPs: (value: string) => void; officers: ManagerFilterOption[]; refreshKey: number }) {
  const sectionRef = useRef<HTMLElement>(null);
  const [enabled, setEnabled] = useState(false);
  const [comparePs, setComparePs] = useState("");
  const [priority, setPriority] = useState("");
  const [rows, setRows] = useState<ManagerPSFollowupRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [bucket, setBucket] = useState<{ ps: ManagerPSFollowupRow; key: string; label: string } | null>(null);
  const [customers, setCustomers] = useState<Awaited<ReturnType<typeof getSalesManagerPSFollowups>>["leads"]>([]);
  const [modalLoading, setModalLoading] = useState(false);
  const [detail, setDetail] = useState<LeadDetail | null>(null);
  const query = useMemo(() => ({ ...filters, ...(primaryPs ? { ps: primaryPs } : {}), ...(primaryPs && comparePs ? { compare_ps: comparePs } : {}), ...(priority ? { priority } : {}) }), [comparePs, filters, primaryPs, priority]);
  const followupRequest = useRef(0);
  const load = useCallback(async () => { const request = ++followupRequest.current; setLoading(true); setError(""); try { const result = await getSalesManagerPSFollowups(query); if (request === followupRequest.current) setRows(result.rows); } catch (err) { if (request === followupRequest.current) setError(err instanceof Error ? err.message : "Unable to load PS follow-ups."); } finally { if (request === followupRequest.current) setLoading(false); } }, [query]);
  useEffect(() => {
    if (!sectionRef.current || !("IntersectionObserver" in window)) { setEnabled(true); return; }
    const observer = new IntersectionObserver(([entry]) => { if (entry.isIntersecting) { setEnabled(true); observer.disconnect(); } }, { rootMargin: "300px" });
    observer.observe(sectionRef.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => { if (!enabled) return; const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, [enabled, load, refreshKey]);
  const close = () => { setBucket(null); setCustomers([]); setDetail(null); };
  const openBucket = async (psRow: ManagerPSFollowupRow, key: string, label: string) => {
    setBucket({ ps: psRow, key, label }); setDetail(null); setCustomers([]); setModalLoading(true); setError("");
    try { setCustomers((await getSalesManagerPSFollowups({ ...filters, ps: String(psRow.id), ...(priority ? { priority } : {}), bucket: key })).leads); }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to load customers."); close(); }
    finally { setModalLoading(false); }
  };
  const openLead = async (id: number) => { setModalLoading(true); try { setDetail(await getLeadDetail(id)); } catch (err) { setError(err instanceof Error ? err.message : "Unable to load lead details."); } finally { setModalLoading(false); } };
  const exportRows = (extra: Record<string, string> = {}) => { setError(""); void exportSalesManagerAnalytics("ps_followups", { ...query, ...extra }).catch(err => setError(err instanceof Error ? err.message : "Export failed.")); };

  return <>
    <article ref={sectionRef} id="manager-section-followups" className="panel manager-table-card manager-followups-card">
      <header className="manager-followups-head"><div><p className="eyebrow">FOLLOW-UP DISCIPLINE</p><h2>PS Followups</h2><p>Unattended means the assigned PS has logged no calls. Overdue counts leads with an open PS follow-up past its scheduled time. F1–F5 track scheduled follow-up history.</p></div><div className="manager-followups-actions"><label><span>Primary PS</span><select value={primaryPs} onChange={event => { setPrimaryPs(event.target.value); setComparePs(""); }}><option value="">All PS/SO</option>{officers.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label><span>Compare PS</span><select disabled={!primaryPs} value={comparePs} onChange={event => setComparePs(event.target.value)}><option value="">Compare PS...</option>{officers.filter(item => String(item.id) !== primaryPs).map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label><span>Priority</span><select value={priority} onChange={event => setPriority(event.target.value)}><option value="">All priorities</option><option value="HOT">Hot</option><option value="WARM">Warm</option><option value="COLD">Cold</option></select></label><button className="filter" onClick={() => exportRows()}>⇩ Export CSV</button><button className="filter" onClick={() => void load()}>↻ Refresh</button></div></header>
      {error && <div className="manager-followups-error" role="alert">{error}</div>}
      <div className="manager-table-scroll"><table className="sales-table manager-followups-table"><thead><tr><th>PS Name</th>{psFollowupColumns.map(([, label]) => <th key={label}>{label}</th>)}</tr></thead><tbody>{!enabled || loading ? <tr><td colSpan={10} className="sales-empty">Loading PS follow-ups...</td></tr> : rows.length ? rows.map(row => <tr key={row.id}><td><b>{row.name}</b><small>{row.email}</small></td>{psFollowupColumns.map(([bucketKey, label, valueKey]) => { const value = row[valueKey]; return <td key={bucketKey}><button className={`manager-followup-count ${bucketKey}`} disabled={!value} onClick={() => void openBucket(row, bucketKey, label)} aria-label={`${row.name}, ${label}: ${value}`}>{value}</button></td>; })}</tr>) : <tr><td colSpan={10} className="sales-empty">No PS users match these filters.</td></tr>}</tbody></table></div>
    </article>
    {bucket && <div className="modal-layer manager-followup-layer" role="presentation"><section className="modal manager-followup-modal" role="dialog" aria-modal="true" aria-labelledby="ps-followup-modal-title">
      <button className="modal-close" onClick={close} aria-label="Close">×</button>
      {detail ? <><header className="sales-detail-header"><div><button className="manager-modal-back" onClick={() => setDetail(null)}>← Back to {bucket.label}</button><h2 id="ps-followup-modal-title">{detail.name}</h2><p className="subtext">{detail.phone} · {detail.model} · {managerStatusName(detail.statusCode)}</p></div></header><div className="sales-detail-scroll"><section className="sales-info-card"><h3>Lead details</h3><div className="sales-info-grid"><span><small>Source</small><b>{detail.source}</b></span><span><small>PS/SO</small><b>{detail.assignedPsName || "-"}</b></span><span><small>Test drive</small><b>{detail.qualification?.test_drive || "No"}</b></span><span><small>Sales outcome</small><b>{detail.salesOutcome}</b></span></div></section><section className="sales-history"><h3>Call history and remarks</h3>{detail.callHistory.length ? detail.callHistory.map(call => <div className="sales-history-row" key={call.id}><span className="history-dot" /><div><b>{managerStatusName(call.outcome || call.status)}</b><small>{call.remarks || "No remarks"}</small><small>By {call.so_name || "-"} · {formatDateTime(call.created_at)}</small></div></div>) : <p className="subtext">No calls recorded.</p>}</section><section className="sales-history"><h3>Scheduled follow-ups</h3>{detail.followUpHistory.length ? detail.followUpHistory.map(item => <div className="sales-history-row" key={item.id}><span className="history-dot follow" /><div><b>{formatDateTime(item.scheduled_for)}</b><small>{item.resolved_at ? `Resolved ${formatDateTime(item.resolved_at)}` : "Open"}</small></div></div>) : <p className="subtext">No scheduled follow-ups.</p>}</section></div></> : <><header className="manager-followup-modal-head"><div><h2 id="ps-followup-modal-title">{bucket.ps.name} – {bucket.label} ({customers.length})</h2><p>Open a customer to view detailed call history and remarks.</p></div><button className="filter" onClick={() => exportRows({ ps: String(bucket.ps.id), bucket: bucket.key })}>⇩ Export CSV</button></header><div className="manager-followup-modal-scroll"><table className="sales-table manager-followup-customers"><thead><tr><th>Customer Name</th><th>Mobile</th><th>Source</th><th>Created At</th><th>Model</th><th>Test Drive</th><th>Status</th></tr></thead><tbody>{modalLoading ? <tr><td colSpan={7} className="sales-empty">Loading customers...</td></tr> : customers.length ? customers.map(customer => <tr key={customer.id} role="button" tabIndex={0} onClick={() => void openLead(customer.id)} onKeyDown={event => { if (event.key === "Enter") void openLead(customer.id); }}><td><b>{customer.name}</b></td><td>{customer.phone}</td><td>{sourceName(customer.source)}</td><td>{formatDateTime(customer.created_at)}</td><td>{customer.model || "-"}</td><td><span className="manager-test-drive">{customer.test_drive}</span></td><td><span className={`sales-status ${customer.status.toLowerCase()}`}>{managerStatusName(customer.status)}</span></td></tr>) : <tr><td colSpan={7} className="sales-empty">No customers in this category.</td></tr>}</tbody></table></div></>}
    </section></div>}
  </>;
}

export function SalesManagerAnalyticsPage() {
  const router = useRouter();
  const [range, setRange] = useState("mtd");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const today = todayInIST();
  const selectedTo = toDateInputValue(dateTo);
  const historicalFromMax = selectedTo && selectedTo < today ? dateTo : today;
  const [source, setSource] = useState("");
  const [configuredSources, setConfiguredSources] = useState<string[]>(["WALKIN"]);
  const [color, setColor] = useState("");
  const [configuredColors, setConfiguredColors] = useState<string[]>([]);
  const [ps, setPs] = useState("");
  const [data, setData] = useState<ManagerAnalytics | null>(null);
  const [dataVersion, setDataVersion] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const requestId = useRef(0);
  const validDateFrom = toDateInputValue(dateFrom);
  const validDateTo = toDateInputValue(dateTo);
  const params = useMemo(() => ({ range, ...(range === "custom" && validDateFrom ? { date_from: validDateFrom } : {}), ...(range === "custom" && validDateTo ? { date_to: validDateTo } : {}), ...(source ? { source } : {}), ...(color ? { color } : {}), ...(ps ? { ps } : {}) }), [color, ps, range, source, validDateFrom, validDateTo]);
  const followupFilters = useMemo<Record<string, string>>(() => ({ range, ...(range === "custom" && validDateFrom ? { date_from: validDateFrom } : {}), ...(range === "custom" && validDateTo ? { date_to: validDateTo } : {}), ...(source ? { source } : {}), ...(color ? { color } : {}) }), [color, range, source, validDateFrom, validDateTo]);
  const drilldownFilters: Record<string, string> = { ...(["today", "mtd"].includes(range) && data?.date_from ? { date_from: String(data.date_from), date_to: String(data.date_to || data.date_from) } : {}), ...(range === "custom" && validDateFrom && data?.date_from ? { date_from: String(data.date_from) } : {}), ...(range === "custom" && validDateTo && data?.date_to ? { date_to: String(data.date_to) } : {}), ...(source ? { source } : {}), ...(color ? { color } : {}), ...(ps ? { ps } : {}) };
  const load = useCallback(async (fresh = false) => { const request = ++requestId.current; setLoading(true); setError(""); try { const result = await getSalesManagerAnalytics({ ...params, include: "filters,ps,source,lost", ...(fresh ? { refresh: "1" } : {}) }); if (request === requestId.current) { setData(result); setDataVersion(version => version + 1); } } catch (err) { if (request === requestId.current) setError(err instanceof Error ? err.message : "Unable to load sales manager analytics."); } finally { if (request === requestId.current) setLoading(false); } }, [params]);
  useEffect(() => { void getSystemConfig().then(config => { setConfiguredSources(config.lists.sources || ["WALKIN"]); setConfiguredColors(config.lists.colorVariants || []); }).catch(() => { setConfiguredSources(["WALKIN"]); setConfiguredColors([]); }); }, []);
  useEffect(() => { const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, [load]);
  useCrmRefresh(() => load());
  const sources = configuredSources;
  const psOptions = data?.filters?.ps || data?.ps || [];
  const exportSection = (section: string) => { setError(""); void exportSalesManagerAnalytics(section, params).catch(err => setError(err instanceof Error ? err.message : "Export failed.")); };
  return <section className="page manager-page manager-analytics-page">
    <div className="sales-hero manager-hero"><div><p className="eyebrow">SALES MANAGER</p><h1>Branch analytics <span>{data?.branch || ""}</span></h1><p className="subtext">Branch lead intake, PS/SO performance and conversion, and sales follow-ups.</p></div><div className="sales-hero-actions"><select className="filter" value={range} onChange={event => setRange(event.target.value)}><option value="mtd">MTD vs previous MTD</option><option value="today">Today</option><option value="custom">Date range</option><option value="all">All time</option></select>{range === "custom" && <><DateInput className="date-input-filter" value={dateFrom} max={historicalFromMax} onChange={setDateFrom} ariaLabel="Analytics start date, DD/MM/YYYY" /><DateInput className="date-input-filter" value={dateTo} min={dateFrom || undefined} max={today} onChange={setDateTo} ariaLabel="Analytics end date, DD/MM/YYYY" /></>}<button className="filter" onClick={() => void load(true)} disabled={loading}>{loading ? "Refreshing…" : "Refresh"}</button></div></div>
    {error && <div className="empty-state">{error}</div>}
    {loading && !data ? <div className="panel sales-analytics-loading">Loading branch analytics...</div> : data && <>
      <section className="manager-filter-bar panel"><label>Source<select value={source} onChange={event => setSource(event.target.value)}><option value="">All sources</option>{sources.map(item => <option value={item} key={item}>{sourceName(item)}</option>)}</select></label><label>Color<select value={color} onChange={event => setColor(event.target.value)}><option value="">All colors</option>{configuredColors.map(item => <option value={item} key={item}>{item}</option>)}</select></label><label>PS/SO<select value={ps} onChange={event => setPs(event.target.value)}><option value="">All PS/SO</option>{psOptions.map(row => <option value={row.id} key={row.id}>{row.name}</option>)}</select></label></section>
      <div className="manager-period-note"><span>{data.range === "mtd" ? "Month to date" : data.range === "today" ? "Today" : data.range === "all" ? "All time" : "Selected dates"}{data.date_from ? ` · ${formatDate(data.date_from)}–${formatDate(data.date_to)}` : ""}</span><span>{data.range === "mtd" ? "Refreshes every 30 seconds while open · " : ""}Updated {formatDateTime(data.generated_at)}{loading ? " · Refreshing…" : ""}</span></div>
      <div className="manager-kpi-heading"><h2>Lead journey</h2><p>Progress for leads enquired in this period. Booked includes leads later retailed.</p></div>
      <section className="manager-kpi-grid" aria-label="Lead journey metrics"><EtbrTiles embedded data={data.summary} actions={{ etbr_enquired: () => router.push(leadHref(drilldownFilters)), etbr_retailed: () => router.push(leadHref(drilldownFilters, { sales_outcome: "RETAILED" })) }} /></section>
      <div className="manager-kpi-heading"><h2>Current position</h2><p>Booked here excludes retailed leads; lost includes not interested.</p></div>
      <section className="manager-kpi-grid" aria-label="Current position metrics">{[["Untouched by PS", data.summary.untouched, "untouched", "No call or customer action recorded by the assigned PS"], ["Currently booked", data.summary.booked, "booked", "Excludes retailed leads"], ["Lost / not interested", data.summary.lost, "lost", "Closed without a sale"], ["Lead to retail", `${data.summary.lead_to_retail_rate}%`, "conversion", "Retailed ÷ all enquiries"]].map(([label, value, key, description]) => <Link prefetch={false} className={`sales-metric manager-metric ${key}`} key={key} title={String(description)} href={leadHref(drilldownFilters, metricFilters[String(key)] || {})}><span>{label}</span><strong>{value}</strong><small>{data.range === "mtd" ? `${metricDelta(data.summary.delta?.[String(key)] as number)}${key === "conversion" ? " pp" : ""} vs previous MTD` : "Selected period"}</small></Link>)}</section>
      <section id="manager-section-ps" className="manager-section"><RoleTable rows={data.ps} filters={drilldownFilters} onExport={exportSection} /></section>
      <section id="manager-section-source" className="manager-two-col manager-section"><PerformanceTable title="Source conversion" section="source" labelKey="source" rows={data.source} filters={drilldownFilters} onExport={exportSection} /><PerformanceTable title="Color conversion" section="colors" labelKey="color" rows={data.colors} filters={drilldownFilters} onExport={exportSection} /></section>
      <PSFollowupsSection filters={followupFilters} primaryPs={ps} setPrimaryPs={setPs} officers={psOptions} refreshKey={dataVersion} />
      <LostLeadAnalysis key={new URLSearchParams(drilldownFilters).toString()} total={data.summary.lost} reasons={data.lost_reasons} filters={drilldownFilters} refreshKey={dataVersion} />
    </>}
  </section>;
}
