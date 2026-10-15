"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ceoGet, exportReport, type ReportOptions } from "@/lib/ceo";
import { formatDateTime } from "@/lib/dates";
import { useCrmRefresh } from "@/lib/use-crm-refresh";
import { AnalysisLeadsModal } from "@/features/ceo/analysis-leads-modal";
import styles from "./ce-analytics.module.css";

type Counts = { assigned: number; untouched: number; qualified: number; lost: number; in_progress: number; followups: number; awaiting_ps: number; due_today: number; overdue: number; calls: number; called: number; handoffs: number };
type CERow = Counts & { id: number; name: string; email: string; branch: string; lifecycle: string; last_call: string | null; qualification_rate: number | null };
type CEReport = { results: CERow[]; summary: Counts; generated_at: string };
const columns = [
  ["assigned", "Assigned", "Leads currently assigned to this CE within the selected enquiry dates."],
  ["untouched", "Untouched by CE", "No call or customer action by the current CE since their latest allocation."],
  ["qualified", "Qualified by CE", "Latest recorded CE outcome is qualified. Later PS updates do not change this result."],
  ["lost", "Lost by CE", "Latest recorded CE outcome is lost or not interested."],
  ["in_progress", "In progress", "Touched by the CE without a current qualified or lost CE outcome, including pending and RNR."],
  ["followups", "Follow-ups", "Distinct leads with an outstanding actionable follow-up for their current CE."],
  ["due_today", "Due today", "Distinct leads with an outstanding CE follow-up scheduled today, including missed times."],
  ["overdue", "Overdue", "Distinct leads with an outstanding CE follow-up whose scheduled time has passed."],
  ["calls", "Calls logged", "Calls by this CE on these leads since their latest allocation. Repeat calls count separately."],
] as const;

export function CEAnalyticsPage() {
  const [range, setRange] = useState("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [branch, setBranch] = useState("");
  const [employee, setEmployee] = useState("");
  const [options, setOptions] = useState<ReportOptions | null>(null);
  const [data, setData] = useState<CEReport | null>(null);
  const [error, setError] = useState("");
  const [optionsError, setOptionsError] = useState("");
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [selected, setSelected] = useState<{ query: string; title: string } | null>(null);
  const requestId = useRef(0);
  const params = new URLSearchParams({ range, role: "CRE" });
  if (branch) params.set("branch", branch);
  if (employee) params.set("employee", employee);
  if (range === "custom") { params.set("date_from", from); params.set("date_to", to); }
  const query = params.toString();
  const valid = range !== "custom" || Boolean(from && to);
  const load = useCallback(async () => {
    if (!valid) return;
    const id = ++requestId.current;
    setLoading(true);
    try {
      const result = await ceoGet<CEReport>("ce-performance", `${query}&refresh=1`);
      if (id === requestId.current) { setData(result); setError(""); }
    } catch (e) { if (id === requestId.current) setError(e instanceof Error ? e.message : "Unable to load CE performance."); }
    finally { if (id === requestId.current) setLoading(false); }
  }, [query, valid]);
  useEffect(() => {
    const controller = new AbortController();
    void ceoGet<ReportOptions>("options", "", controller.signal).then(setOptions).catch(e => { if (e.name !== "AbortError") setOptionsError("Unable to load CE and branch filters. Reload the page to retry."); });
    return () => controller.abort();
  }, []);
  useEffect(() => { setData(null); setError(""); setLoading(false); void load(); return () => { requestId.current++; }; }, [load]);
  useCrmRefresh(load, valid);
  const exportCSV = async () => {
    setExporting(true);
    try { await exportReport("ce-performance", query); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to export CE performance."); }
    finally { setExporting(false); }
  };
  const openLeads = (metric: string, title: string, row?: CERow) => {
    const filters = new URLSearchParams(query);
    filters.set("ce_metric", metric);
    filters.set("refresh", "1");
    if (row) filters.set("employee", String(row.id));
    setSelected({ query: filters.toString(), title: `${row?.name || options?.employees.find(item => String(item.id) === employee)?.name || "All CEs"} · ${title}` });
  };
  return <section className={styles.page}>
    <header className={styles.heading}><div><p className={styles.eyebrow}>CUSTOMER EXECUTIVES</p><h1>CE performance</h1><p>Lead contact, qualification and handoff to the sales team.</p></div><div className={styles.actions}><button disabled={loading || !valid} onClick={() => void load()}>{loading ? "Refreshing…" : "Refresh"}</button><button disabled={!data || exporting || loading} onClick={() => void exportCSV()}>{exporting ? "Exporting…" : "Export CSV"}</button></div></header>
    <div className={styles.filters}>
      <label>Enquiry period<select value={range} onChange={e => setRange(e.target.value)}><option value="today">Today</option><option value="mtd">Month to date</option><option value="previous_month">Previous month</option><option value="all">All time</option><option value="custom">Custom dates</option></select></label>
      {range === "custom" && <><label>From<input type="date" value={from} max={to || undefined} onChange={e => setFrom(e.target.value)} /></label><label>To<input type="date" value={to} min={from || undefined} onChange={e => setTo(e.target.value)} /></label></>}
      <label>Lead branch<select value={branch} disabled={!options} onChange={e => { setBranch(e.target.value); setEmployee(""); }}><option value="">All branches</option>{options?.branches.map(b => <option key={b.value} value={b.value}>{b.label}</option>)}</select></label>
      <label>CE<select value={employee} disabled={!options} onChange={e => setEmployee(e.target.value)}><option value="">All CEs</option>{options?.employees.filter(e => e.role === "CRE").map(e => <option key={e.id} value={e.id}>{e.name}{e.lifecycle !== "ACTIVE" ? ` · ${e.lifecycle.toLowerCase()}` : ""}</option>)}</select></label>
    </div>
    {(error || optionsError) && <p className={styles.error} role="alert">{error || optionsError}</p>}
    {!valid && <p>Choose both dates to load the report.</p>}
    <div className={styles.metrics}>{([
      ["assigned", "Assigned", "Within selected enquiry dates"], ["untouched", "Untouched by CE", "No CE action since allocation"],
      ["qualified", "Qualified by CE", "Latest CE outcome"], ["lost", "Lost by CE", "Lost or not interested"],
      ["in_progress", "In progress", "Touched, not qualified or lost"],
    ] as const).map(([key, title, detail]) => <button className={styles.metric} disabled={!data} onClick={() => openLeads(key, title)} key={key} aria-label={`View ${title.toLowerCase()} leads`}><span>{title}</span><strong>{data?.summary[key] ?? "—"}</strong><small>{detail}</small></button>)}</div>
    <section className={styles.panel} aria-label="CE performance table" aria-busy={loading}>
      <header className={styles.tableHeading}><h2>CE team</h2></header>
      <p className={styles.note}>Select a tile, CE name or count to see matching leads, then select a customer to open their history.</p>
      <p className={styles.note}><b>Assigned = Untouched + Qualified by CE + Lost by CE + In progress.</b> Each assigned lead appears in exactly one of these four categories, based on the current CE’s actions since allocation. Later PS updates do not change the CE result.</p>
      <p className={styles.note}>Follow-ups count leads with outstanding CE follow-ups and overlap the categories above. Due today and overdue can overlap when a follow-up was missed earlier today. Calls logged includes repeat calls.</p>
      <div className={styles.scroll}><table>
        <thead><tr><th scope="col">CE</th>{columns.map(([key, title, detail]) => <th scope="col" title={detail} key={key}>{title}</th>)}<th scope="col" title="Qualified by CE divided by assigned leads. Select to view qualified leads.">Qualification %</th></tr></thead>
        <tbody>{data?.results.map(row => <tr key={row.id}>
          <td><button className={styles.countLink} onClick={() => openLeads("assigned", "Assigned", row)}><b>{row.name}</b></button><small>{row.email}</small><small>{row.branch || "No branch"}{row.lifecycle !== "ACTIVE" ? ` · ${row.lifecycle.toLowerCase()}` : ""}</small></td>
          {columns.map(([key, title]) => <td key={key} className={key === "overdue" && row[key] > 0 ? styles.overdue : undefined}><button className={styles.countLink} aria-label={`${row.name}: ${title}, ${row[key]}. View matching leads`} onClick={() => openLeads(key, title, row)}>{row[key]}</button></td>)}
          <td>{row.qualification_rate === null ? "—" : <button className={styles.countLink} aria-label={`${row.name}: view qualified leads`} onClick={() => openLeads("qualified", "Qualified by CE", row)}>{row.qualification_rate}%</button>}</td>
        </tr>)}</tbody>
        {data && <tfoot><tr><th scope="row">Total</th>{columns.map(([key, title]) => <td key={key}><button className={styles.countLink} aria-label={`Total ${title}: ${data.summary[key]}. View matching leads`} onClick={() => openLeads(key, title)}>{data.summary[key]}</button></td>)}<td>{data.summary.assigned ? <button className={styles.countLink} aria-label="View all qualified leads" onClick={() => openLeads("qualified", "Qualified by CE")}>{Math.round(data.summary.qualified / data.summary.assigned * 1000) / 10}%</button> : "—"}</td></tr></tfoot>}
      </table>{!data?.results.length && <p className={styles.empty}>{loading ? "Loading CE performance…" : !valid ? "Choose an enquiry period." : error ? "Report unavailable. Use Refresh to retry." : "No CEs match these filters."}</p>}</div>
    </section>
    <p className={styles.updated}>Refreshes every 30 seconds while open{data ? ` · Updated ${formatDateTime(data.generated_at)}` : ""}</p>
    {selected && <AnalysisLeadsModal key={selected.query} {...selected} options={options} onClose={() => setSelected(null)} />}
  </section>;
}
