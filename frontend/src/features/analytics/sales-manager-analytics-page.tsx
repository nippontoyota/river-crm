"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { exportSalesManagerAnalytics, getLeadDetail, getSalesManagerAnalytics, getSalesManagerPSFollowups, getSystemConfig, sourceName, statusName, type LeadDetail, type ManagerAnalytics, type ManagerFilterOption, type ManagerPerformanceRow, type ManagerPSFollowupRow, type ManagerRoleRow } from "@/lib/crm";
import { DateInput } from "@/components/date-input";
import { formatDate, formatDateTime, todayInIST, toDateInputValue } from "@/lib/dates";

const tabs = [
  ["overview", "Overview"],
  ["cre", "CRE"],
  ["ps", "PS/SO"],
  ["source", "Source"],
  ["ops", "Ops risks"],
] as const;

const metricFilters: Record<string, Record<string, string>> = {
  untouched: { status: "FRESH" },
  qualified: { status: "QUALIFIED" },
  booked: { sales_outcome: "BOOKED" },
  retailed: { sales_outcome: "RETAILED" },
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

function RoleTable({ title, section, rows, filters, onExport }: { title: string; section: "cre" | "ps"; rows: ManagerRoleRow[]; filters: Record<string, string>; onExport: (section: string) => void }) {
  const router = useRouter();
  return <article className="panel manager-table-card"><header className="manager-card-head"><div><p className="eyebrow">{section === "cre" ? "LEAD HANDLING" : "SALES CONVERSION"}</p><h2>{title}</h2></div><button className="filter" onClick={() => onExport(section)}>Export CSV</button></header><div className="manager-table-scroll"><table className="sales-table manager-table"><thead><tr><th>Name</th><th>Total</th><th>Calls</th><th>Qualified</th><th>Booked</th><th>Retailed</th><th>Lost</th><th>Conv.</th><th>Last call</th></tr></thead><tbody>{rows.length ? rows.map(row => { const href = leadHref(filters, section === "cre" ? { cre: String(row.id) } : { ps: String(row.id) }); return <tr className="manager-clickable-row" key={row.id} role="link" tabIndex={0} onClick={() => router.push(href)} onKeyDown={event => { if (event.key === "Enter") router.push(href); }}><td><b>{row.name}</b><small>{row.email}</small></td><td>{row.total}</td><td>{row.calls}</td><td>{row.qualified}</td><td>{row.booked}</td><td>{row.retailed}</td><td>{row.lost}</td><td><span className="manager-rate">{row.conversion_rate}%</span></td><td>{formatDateTime(row.last_activity) || "-"}</td></tr>; }) : <tr><td colSpan={9} className="sales-empty">No users have branch activity in this period.</td></tr>}</tbody></table></div></article>;
}

function PerformanceTable({ title, section, labelKey, rows, filters, onExport }: { title: string; section: "source" | "models"; labelKey: "source" | "model"; rows: (ManagerPerformanceRow & Record<string, string | number>)[]; filters: Record<string, string>; onExport: (section: string) => void }) {
  const router = useRouter();
  return <article className="panel manager-table-card"><header className="manager-card-head"><div><p className="eyebrow">CONVERSION MIX</p><h2>{title}</h2></div><button className="filter" onClick={() => onExport(section)}>Export CSV</button></header><div className="manager-table-scroll"><table className="sales-table manager-table"><thead><tr><th>{labelKey === "source" ? "Source" : "Model"}</th><th>Total</th><th>Qualified</th><th>Booked</th><th>Retailed</th><th>Lost</th><th>Conv.</th></tr></thead><tbody>{rows.length ? rows.map(row => { const name = String(row[labelKey] || "Unknown"); const filter: Record<string, string> = labelKey === "source" ? { source: name } : { model: name }; const clickable = labelKey === "source" || name !== "Model not set"; const href = leadHref(filters, filter); return <tr className={clickable ? "manager-clickable-row" : ""} key={name} role={clickable ? "link" : undefined} tabIndex={clickable ? 0 : undefined} onClick={clickable ? () => router.push(href) : undefined} onKeyDown={clickable ? event => { if (event.key === "Enter") router.push(href); } : undefined}><td><b>{labelKey === "source" ? sourceName(name) : name}</b></td><td>{row.total}</td><td>{row.qualified}</td><td>{row.booked}</td><td>{row.retailed}</td><td>{row.lost}</td><td><span className="manager-rate">{row.conversion_rate}%</span></td></tr>; }) : <tr><td colSpan={7} className="sales-empty">No rows for this period.</td></tr>}</tbody></table></div></article>;
}

function ProgressionChart({ funnel }: { funnel: ManagerAnalytics["funnel"] }) {
  const maximum = Math.max(...funnel.map(item => item.count), 1);
  const points = funnel.map((item, index) => ({ ...item, x: 50 + (index * 540) / Math.max(funnel.length - 1, 1), y: 170 - (item.count / maximum) * 125 }));
  return <article className="panel manager-chart-card"><header className="manager-card-head"><div><p className="eyebrow">PIPELINE PROGRESSION</p><h2>Lead to retail movement</h2></div></header><div className="manager-progression-chart"><svg viewBox="0 0 640 220" role="img" aria-label="Lead progression from total leads through retail"><g className="manager-chart-grid"><line x1="50" y1="45" x2="590" y2="45" /><line x1="50" y1="87" x2="590" y2="87" /><line x1="50" y1="128" x2="590" y2="128" /><line x1="50" y1="170" x2="590" y2="170" /></g><polyline className="manager-progression-area" points={`50,170 ${points.map(point => `${point.x},${point.y}`).join(" ")} 590,170`} /><polyline className="manager-progression-line" points={points.map(point => `${point.x},${point.y}`).join(" ")} />{points.map(point => <g key={point.key}><circle cx={point.x} cy={point.y} r="6" /><text className="manager-chart-value" x={point.x} y={point.y - 15}>{point.count}</text><text className="manager-chart-label" x={point.x} y="203">{point.label}</text><text className="manager-chart-rate" x={point.x} y="217">{point.rate}%</text></g>)}</svg></div></article>;
}

function MonthlyBarChart({ monthly }: { monthly: ManagerAnalytics["monthly"] }) {
  const rows = monthly.filter(item => item.month).slice(-8);
  const maximum = Math.max(...rows.map(item => item.total), 1);
  const monthLabel = (value: string | null) => formatDate(value) || "-";
  const bars = [["total", "Leads"], ["qualified", "Qualified"], ["booked", "Booked"], ["retailed", "Retailed"]] as const;
  return <article className="panel manager-chart-card"><header className="manager-card-head"><div><p className="eyebrow">MONTHLY PROGRESSION</p><h2>Volume and conversion</h2></div></header>{rows.length ? <><div className="manager-monthly-chart" role="img" aria-label="Monthly leads, qualified, booked, and retailed bar chart">{rows.map(item => <div className="manager-month-group" key={item.month}><div className="manager-month-bars">{bars.map(([key, label]) => <i className={key} key={key} style={{ height: `${item[key] ? Math.max(6, (item[key] / maximum) * 100) : 0}%` }} title={`${monthLabel(item.month)} ${label}: ${item[key]}`}><span>{item[key]}</span></i>)}</div><small>{monthLabel(item.month)}</small></div>)}</div><div className="manager-chart-legend">{bars.map(([key, label]) => <span key={key}><i className={key} />{label}</span>)}</div></> : <div className="manager-chart-empty">No monthly activity for this period.</div>}</article>;
}

const psFollowupColumns = [
  ["total", "Total Leads", "total_leads"],
  ["test_drive", "Test Drive", "test_drive"],
  ["unattended", "Unattended", "unattended"],
  ["f1", "F1", "f1"],
  ["f2", "F2", "f2"],
  ["f3", "F3", "f3"],
  ["f4", "F4", "f4"],
  ["f5", "F5", "f5"],
] as const;

function PSFollowupsSection({ filters, primaryPs, setPrimaryPs, officers }: { filters: Record<string, string>; primaryPs: string; setPrimaryPs: (value: string) => void; officers: ManagerFilterOption[] }) {
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
  const load = useCallback(async () => { setLoading(true); setError(""); try { setRows((await getSalesManagerPSFollowups(query)).rows); } catch (err) { setError(err instanceof Error ? err.message : "Unable to load PS follow-ups."); } finally { setLoading(false); } }, [query]);
  useEffect(() => {
    if (!sectionRef.current || !("IntersectionObserver" in window)) { setEnabled(true); return; }
    const observer = new IntersectionObserver(([entry]) => { if (entry.isIntersecting) { setEnabled(true); observer.disconnect(); } }, { rootMargin: "300px" });
    observer.observe(sectionRef.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => { if (!enabled) return; const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, [enabled, load]);
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
    <article ref={sectionRef} className="panel manager-table-card manager-followups-card">
      <header className="manager-followups-head"><div><p className="eyebrow">FOLLOW-UP DISCIPLINE</p><h2>PS Followups</h2><p>Customers advance from F1 to F5 as scheduled follow-ups are recorded.</p></div><div className="manager-followups-actions"><label><span>Primary PS</span><select value={primaryPs} onChange={event => { setPrimaryPs(event.target.value); setComparePs(""); }}><option value="">All PS/SO</option>{officers.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label><span>Compare PS</span><select disabled={!primaryPs} value={comparePs} onChange={event => setComparePs(event.target.value)}><option value="">Compare PS...</option>{officers.filter(item => String(item.id) !== primaryPs).map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label><span>Priority</span><select value={priority} onChange={event => setPriority(event.target.value)}><option value="">All priorities</option><option value="HOT">Hot</option><option value="WARM">Warm</option><option value="COLD">Cold</option></select></label><button className="filter" onClick={() => exportRows()}>⇩ Export CSV</button><button className="filter" onClick={() => void load()}>↻ Refresh</button></div></header>
      {error && <div className="manager-followups-error" role="alert">{error}</div>}
      <div className="manager-table-scroll"><table className="sales-table manager-followups-table"><thead><tr><th>PS Name</th>{psFollowupColumns.map(([, label]) => <th key={label}>{label}</th>)}</tr></thead><tbody>{!enabled || loading ? <tr><td colSpan={9} className="sales-empty">Loading PS follow-ups...</td></tr> : rows.length ? rows.map(row => <tr key={row.id}><td><b>{row.name}</b><small>{row.email}</small></td>{psFollowupColumns.map(([bucketKey, label, valueKey]) => { const value = row[valueKey]; return <td key={bucketKey}><button className={`manager-followup-count ${bucketKey}`} disabled={!value} onClick={() => void openBucket(row, bucketKey, label)} aria-label={`${row.name}, ${label}: ${value}`}>{value}</button></td>; })}</tr>) : <tr><td colSpan={9} className="sales-empty">No PS users match these filters.</td></tr>}</tbody></table></div>
    </article>
    {bucket && <div className="modal-layer manager-followup-layer" role="presentation"><section className="modal manager-followup-modal" role="dialog" aria-modal="true" aria-labelledby="ps-followup-modal-title">
      <button className="modal-close" onClick={close} aria-label="Close">×</button>
      {detail ? <><header className="sales-detail-header"><div><button className="manager-modal-back" onClick={() => setDetail(null)}>← Back to {bucket.label}</button><h2 id="ps-followup-modal-title">{detail.name}</h2><p className="subtext">{detail.phone} · {detail.model} · {detail.status}</p></div></header><div className="sales-detail-scroll"><section className="sales-info-card"><h3>Lead details</h3><div className="sales-info-grid"><span><small>Source</small><b>{detail.source}</b></span><span><small>PS/SO</small><b>{detail.assignedPsName || "-"}</b></span><span><small>Test drive</small><b>{detail.qualification?.test_drive || "No"}</b></span><span><small>Sales outcome</small><b>{detail.salesOutcome}</b></span></div></section><section className="sales-history"><h3>Call history and remarks</h3>{detail.callHistory.length ? detail.callHistory.map(call => <div className="sales-history-row" key={call.id}><span className="history-dot" /><div><b>{call.outcome || statusName(call.status)}</b><small>{call.remarks || "No remarks"}</small><small>By {call.so_name || "-"} · {formatDateTime(call.created_at)}</small></div></div>) : <p className="subtext">No calls recorded.</p>}</section><section className="sales-history"><h3>Scheduled follow-ups</h3>{detail.followUpHistory.length ? detail.followUpHistory.map(item => <div className="sales-history-row" key={item.id}><span className="history-dot follow" /><div><b>{formatDateTime(item.scheduled_for)}</b><small>{item.resolved_at ? `Resolved ${formatDateTime(item.resolved_at)}` : "Open"}</small></div></div>) : <p className="subtext">No scheduled follow-ups.</p>}</section></div></> : <><header className="manager-followup-modal-head"><div><h2 id="ps-followup-modal-title">{bucket.ps.name} – {bucket.label} ({customers.length})</h2><p>Open a customer to view detailed call history and remarks.</p></div><button className="filter" onClick={() => exportRows({ ps: String(bucket.ps.id), bucket: bucket.key })}>⇩ Export CSV</button></header><div className="manager-followup-modal-scroll"><table className="sales-table manager-followup-customers"><thead><tr><th>Customer Name</th><th>Mobile</th><th>Source</th><th>Created At</th><th>Model</th><th>Test Drive</th><th>Status</th></tr></thead><tbody>{modalLoading ? <tr><td colSpan={7} className="sales-empty">Loading customers...</td></tr> : customers.length ? customers.map(customer => <tr key={customer.id} role="button" tabIndex={0} onClick={() => void openLead(customer.id)} onKeyDown={event => { if (event.key === "Enter") void openLead(customer.id); }}><td><b>{customer.name}</b></td><td>{customer.phone}</td><td>{sourceName(customer.source)}</td><td>{formatDateTime(customer.created_at)}</td><td>{customer.model || "-"}</td><td><span className="manager-test-drive">{customer.test_drive}</span></td><td><span className={`sales-status ${customer.status.toLowerCase()}`}>{statusName(customer.status)}</span></td></tr>) : <tr><td colSpan={7} className="sales-empty">No customers in this category.</td></tr>}</tbody></table></div></>}
    </section></div>}
  </>;
}

export function SalesManagerAnalyticsPage() {
  const [activeTab, setActiveTab] = useState<(typeof tabs)[number][0]>("overview");
  const [range, setRange] = useState("mtd");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const today = todayInIST();
  const selectedTo = toDateInputValue(dateTo);
  const historicalFromMax = selectedTo && selectedTo < today ? dateTo : today;
  const [source, setSource] = useState("");
  const [configuredSources, setConfiguredSources] = useState<string[]>(["WALKIN"]);
  const [model, setModel] = useState("");
  const [cre, setCre] = useState("");
  const [ps, setPs] = useState("");
  const [data, setData] = useState<ManagerAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [sectionLoading, setSectionLoading] = useState(false);
  const [error, setError] = useState("");
  const loadedSections = useRef(new Set<string>());
  const sectionRequest = useRef(0);
  const validDateFrom = toDateInputValue(dateFrom);
  const validDateTo = toDateInputValue(dateTo);
  const params = useMemo(() => ({ range, ...(range === "custom" && validDateFrom ? { date_from: validDateFrom } : {}), ...(range === "custom" && validDateTo ? { date_to: validDateTo } : {}), ...(source ? { source } : {}), ...(model ? { model } : {}), ...(cre ? { cre } : {}), ...(ps ? { ps } : {}) }), [cre, model, ps, range, source, validDateFrom, validDateTo]);
  const followupFilters = useMemo<Record<string, string>>(() => ({ range, ...(range === "custom" && validDateFrom ? { date_from: validDateFrom } : {}), ...(range === "custom" && validDateTo ? { date_to: validDateTo } : {}), ...(source ? { source } : {}), ...(model ? { model } : {}), ...(cre ? { cre } : {}) }), [cre, model, range, source, validDateFrom, validDateTo]);
  const drilldownFilters: Record<string, string> = { ...(range === "today" && data?.date_from ? { date_from: String(data.date_from), date_to: String(data.date_to || data.date_from) } : {}), ...(range === "custom" && validDateFrom && data?.date_from ? { date_from: String(data.date_from) } : {}), ...(range === "custom" && validDateTo && data?.date_to ? { date_to: String(data.date_to) } : {}), ...(source ? { source } : {}), ...(model ? { model } : {}), ...(cre ? { cre } : {}), ...(ps ? { ps } : {}) };
  const load = useCallback(async () => { setLoading(true); setError(""); loadedSections.current.clear(); sectionRequest.current += 1; try { const result = await getSalesManagerAnalytics({ ...params, include: "overview,filters" }); setData(result); loadedSections.current.add("overview"); } catch (err) { setError(err instanceof Error ? err.message : "Unable to load sales manager analytics."); } finally { setLoading(false); } }, [params]);
  useEffect(() => { void getSystemConfig().then(config => setConfiguredSources(config.lists.sources || ["WALKIN"])).catch(() => setConfiguredSources(["WALKIN"])); }, []);
  useEffect(() => { const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, [load]);
  useEffect(() => {
    if (!data || loading || activeTab === "overview" || loadedSections.current.has(activeTab)) return;
    const request = ++sectionRequest.current;
    setSectionLoading(true);
    void getSalesManagerAnalytics({ ...params, include: activeTab }).then(result => {
      if (request !== sectionRequest.current) return;
      setData(current => current ? {
        ...current,
        ...(activeTab === "cre" ? { cre: result.cre } : {}),
        ...(activeTab === "ps" ? { ps: result.ps } : {}),
        ...(activeTab === "source" ? { source: result.source, models: result.models } : {}),
        ...(activeTab === "ops" ? { status: result.status, categories: result.categories, lost_reasons: result.lost_reasons, stale_leads: result.stale_leads } : {}),
      } : current);
      loadedSections.current.add(activeTab);
    }).catch(err => { if (request === sectionRequest.current) setError(err instanceof Error ? err.message : "Unable to load analytics section."); })
      .finally(() => { if (request === sectionRequest.current) setSectionLoading(false); });
  }, [activeTab, data, loading, params]);
  const sources = configuredSources;
  const models = data?.filters?.models || data?.models.map(row => row.model).filter(modelName => modelName !== "Model not set") || [];
  const creOptions = data?.filters?.cre || data?.cre || [];
  const psOptions = data?.filters?.ps || data?.ps || [];
  const exportSection = (section: string) => { setError(""); void exportSalesManagerAnalytics(section, params).catch(err => setError(err instanceof Error ? err.message : "Export failed.")); };
  const currentStateBuckets: { label: string; count: number; filter: Record<string, string> }[] = data ? [
    { label: "Callback", count: data.status.find(row => row.status === "CALLBACK")?.count || 0, filter: { status: "CALLBACK" } },
    { label: "Pending", count: data.status.find(row => row.status === "PENDING")?.count || 0, filter: { status: "PENDING" } },
    { label: "Qualified", count: data.status.find(row => row.status === "QUALIFIED")?.count || 0, filter: { status: "QUALIFIED" } },
    { label: "Lost / Unqualified", count: data.status.filter(row => ["LOST", "UNQUALIFIED"].includes(row.status)).reduce((total, row) => total + row.count, 0), filter: { status_group: "lost_or_unqualified" } },
  ] : [];

  return <section className="page manager-page">
    <div className="sales-hero manager-hero"><div><p className="eyebrow">SALES MANAGER</p><h1>Branch analytics <span>{data?.branch || ""}</span></h1><p className="subtext">Full branch visibility across lead intake, CRE handling, PS/SO conversion, follow-up load, and lost-lead risk.</p></div><div className="sales-hero-actions"><select className="filter" value={range} onChange={event => setRange(event.target.value)}><option value="mtd">MTD vs previous MTD</option><option value="today">Today</option><option value="custom">Date range</option><option value="all">All time</option></select>{range === "custom" && <><DateInput className="date-input-filter" value={dateFrom} max={historicalFromMax} onChange={setDateFrom} ariaLabel="Analytics start date, DD/MM/YYYY" /><DateInput className="date-input-filter" value={dateTo} min={dateFrom || undefined} max={today} onChange={setDateTo} ariaLabel="Analytics end date, DD/MM/YYYY" /></>}<button className="filter" onClick={() => void load()}>Refresh</button></div></div>
    {error && <div className="empty-state">{error}</div>}
    {loading && !data ? <div className="panel sales-analytics-loading">Loading branch analytics...</div> : data && <>
      <section className="manager-filter-bar panel"><label>Source<select value={source} onChange={event => setSource(event.target.value)}><option value="">All sources</option>{sources.map(item => <option value={item} key={item}>{sourceName(item)}</option>)}</select></label><label>Model<select value={model} onChange={event => setModel(event.target.value)}><option value="">All models</option>{models.map(item => <option value={item} key={item}>{item}</option>)}</select></label><label>CRE<select value={cre} onChange={event => setCre(event.target.value)}><option value="">All CRE</option>{creOptions.map(row => <option value={row.id} key={row.id}>{row.name}</option>)}</select></label><label>PS/SO<select value={ps} onChange={event => setPs(event.target.value)}><option value="">All PS/SO</option>{psOptions.map(row => <option value={row.id} key={row.id}>{row.name}</option>)}</select></label></section>
      <section className="sales-metrics manager-metrics">{[["Total leads", data.summary.total, "total"], ["Untouched", data.summary.untouched, "untouched"], ["Qualified", data.summary.qualified, "qualified"], ["Booked", data.summary.booked, "booked"], ["Retailed", data.summary.retailed, "retailed"], ["Lead to retail", `${data.summary.lead_to_retail_rate}%`, "conversion"]].map(([label, value, key]) => <Link prefetch={false} className="sales-metric manager-metric" key={key} href={leadHref(drilldownFilters, metricFilters[String(key)] || {})}><span>{label}</span><strong>{value}</strong><small>{key === "conversion" ? `${data.summary.qualified_to_booked_rate}% qualified to booked` : data.range === "mtd" ? `${metricDelta(data.summary.delta?.[String(key)] as number)} vs prev MTD` : "Selected period"}</small></Link>)}</section>
      <nav className="sales-tabs manager-tabs" aria-label="Analytics sections">{tabs.map(([key, label]) => <button key={key} className={activeTab === key ? "active" : ""} onClick={() => setActiveTab(key)}>{label}</button>)}</nav>
      {sectionLoading && activeTab !== "overview" && <div className="panel sales-analytics-loading">Loading section...</div>}
      {!sectionLoading && activeTab === "overview" && <section className="manager-overview-grid"><ProgressionChart funnel={data.funnel} /><MonthlyBarChart monthly={data.monthly} /><article className="panel manager-risk-card"><p className="eyebrow">OPS RISKS</p><h2>Needs attention</h2><div className="manager-risk-list"><Link prefetch={false} href={leadHref(drilldownFilters, { status: "FRESH", risk: "stale" })}><b>{data.summary.stale_untouched}</b><span>stale untouched leads</span></Link><Link prefetch={false} href={leadHref(drilldownFilters, { followup: "overdue" })}><b>{data.followups.overdue}</b><span>overdue follow-ups</span></Link><Link prefetch={false} href={leadHref(drilldownFilters, { flagged: "true" })}><b>{data.summary.flagged}</b><span>flagged to manager</span></Link><Link prefetch={false} href={leadHref(drilldownFilters, { status_group: "lost_or_unqualified" })}><b>{data.summary.lost}</b><span>lost or unqualified</span></Link></div></article></section>}
      {!sectionLoading && activeTab === "cre" && <RoleTable title="CRE performance" section="cre" rows={data.cre} filters={drilldownFilters} onExport={exportSection} />}
      {!sectionLoading && activeTab === "ps" && <RoleTable title="PS/SO performance" section="ps" rows={data.ps} filters={drilldownFilters} onExport={exportSection} />}
      {!sectionLoading && activeTab === "source" && <section className="manager-two-col"><PerformanceTable title="Source conversion" section="source" labelKey="source" rows={data.source} filters={drilldownFilters} onExport={exportSection} /><PerformanceTable title="Model conversion" section="models" labelKey="model" rows={data.models} filters={drilldownFilters} onExport={exportSection} /></section>}
      {!sectionLoading && activeTab === "ops" && <section className="manager-two-col"><article className="panel manager-table-card"><header className="manager-card-head"><div><p className="eyebrow">CURRENT PIPELINE</p><h2>Current lead states</h2></div></header><div className="manager-list">{currentStateBuckets.map(row => <Link prefetch={false} href={leadHref(drilldownFilters, row.filter)} key={row.label}><span>{row.label}</span><b>{row.count}</b></Link>)}</div></article><article className="panel manager-table-card"><header className="manager-card-head"><div><p className="eyebrow">STALE LEADS</p><h2>Oldest untouched</h2></div><button className="filter" onClick={() => exportSection("stale_leads")}>Export CSV</button></header><div className="manager-list">{data.stale_leads.length ? data.stale_leads.map(row => <Link prefetch={false} href={leadHref(drilldownFilters, { status: "FRESH", risk: "stale", q: row.phone })} key={row.id}><span>{row.name}<small>{sourceName(row.source)} - {row.model_interest || "Model not set"} - {formatDate(row.created_at)}</small></span><b>#{String(row.id).padStart(6, "0")}</b></Link>) : <p className="subtext">No stale untouched leads.</p>}</div></article></section>}
      <PSFollowupsSection filters={followupFilters} primaryPs={ps} setPrimaryPs={setPs} officers={psOptions} />
    </>}
  </section>;
}
