"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ceoGet, exportReport, type ReportOptions } from "@/lib/ceo";
import { formatDateTime } from "@/lib/dates";
import { useCrmRefresh } from "@/lib/use-crm-refresh";
import styles from "./ce-analytics.module.css";

type Counts = { assigned: number; untouched: number; awaiting_ps: number; due_today: number; overdue: number; calls: number; called: number; qualified: number; not_interested: number; handoffs: number };
type CERow = Counts & { id: number; name: string; email: string; branch: string; lifecycle: string; last_call: string | null; qualification_rate: number | null };
type CEReport = { results: CERow[]; summary: Counts; generated_at: string };
const workload = [
  ["assigned", "Assigned", "All leads currently assigned to this CE."],
  ["untouched", "Untouched by CE", "No call or customer action by the current CE since their latest allocation."],
  ["awaiting_ps", "Awaiting PS", "Open leads owned by this CE with no PS allocated yet."],
  ["due_today", "Due today", "Distinct leads with an outstanding CE follow-up scheduled today, including missed times."],
  ["overdue", "Overdue", "Distinct leads with an outstanding CE follow-up whose scheduled time has passed."],
] as const;
const activity = [
  ["calls", "Calls logged", "Call records logged by this CE in the selected period."],
  ["called", "Leads called", "Distinct leads called by this CE in the selected period."],
  ["qualified", "Qualified", "Distinct leads marked qualified in this CE’s call records in the selected period."],
  ["handoffs", "PS handoffs", "Distinct leads allocated to a PS by this CE in the selected period."],
  ["not_interested", "Closed by CE", "Distinct leads marked lost or not interested in this CE’s call records in the selected period."],
] as const;

export function CEAnalyticsPage() {
  const [range, setRange] = useState("mtd");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [branch, setBranch] = useState("");
  const [employee, setEmployee] = useState("");
  const [tab, setTab] = useState<"workload" | "activity">("workload");
  const [options, setOptions] = useState<ReportOptions | null>(null);
  const [data, setData] = useState<CEReport | null>(null);
  const [error, setError] = useState("");
  const [optionsError, setOptionsError] = useState("");
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
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
  const columns = tab === "workload" ? workload : activity;
  return <section className={styles.page}>
    <header className={styles.heading}><div><p className={styles.eyebrow}>CUSTOMER EXECUTIVES</p><h1>CE performance</h1><p>Lead contact, qualification and handoff to the sales team.</p></div><div className={styles.actions}><button disabled={loading || !valid} onClick={() => void load()}>{loading ? "Refreshing…" : "Refresh"}</button><button disabled={!data || exporting || loading} onClick={() => void exportCSV()}>{exporting ? "Exporting…" : "Export CSV"}</button></div></header>
    <div className={styles.filters}>
      <label>Activity period<select value={range} onChange={e => setRange(e.target.value)}><option value="today">Today</option><option value="mtd">Month to date</option><option value="previous_month">Previous month</option><option value="all">All time</option><option value="custom">Custom dates</option></select></label>
      {range === "custom" && <><label>From<input type="date" value={from} max={to || undefined} onChange={e => setFrom(e.target.value)} /></label><label>To<input type="date" value={to} min={from || undefined} onChange={e => setTo(e.target.value)} /></label></>}
      <label>Lead branch<select value={branch} disabled={!options} onChange={e => { setBranch(e.target.value); setEmployee(""); }}><option value="">All branches</option>{options?.branches.map(b => <option key={b.value} value={b.value}>{b.label}</option>)}</select></label>
      <label>CE<select value={employee} disabled={!options} onChange={e => setEmployee(e.target.value)}><option value="">All CEs</option>{options?.employees.filter(e => e.role === "CRE").map(e => <option key={e.id} value={e.id}>{e.name}{e.lifecycle !== "ACTIVE" ? ` · ${e.lifecycle.toLowerCase()}` : ""}</option>)}</select></label>
    </div>
    {(error || optionsError) && <p className={styles.error} role="alert">{error || optionsError}</p>}
    {!valid && <p>Choose both dates to load the report.</p>}
    <div className={styles.metrics}>{([
      ["assigned", "Assigned now", "Current CE ownership"], ["untouched", "Untouched by CE", "Since latest CE allocation"],
      ["overdue", "Overdue leads", "Outstanding CE follow-ups"], ["calls", "Calls in period", "Logged by the CE"],
    ] as const).map(([key, title, detail]) => <article key={key}><span>{title}</span><strong>{data?.summary[key] ?? "—"}</strong><small>{detail}</small></article>)}</div>
    <section className={styles.panel} aria-label="CE performance table" aria-busy={loading}>
      <header className={styles.tableHeading}><h2>CE team</h2><div className={styles.tabs} role="group" aria-label="CE report view"><button aria-pressed={tab === "workload"} onClick={() => setTab("workload")}>Current workload</button><button aria-pressed={tab === "activity"} onClick={() => setTab("activity")}>Calls & qualification</button></div></header>
      <p className={styles.note}>{tab === "workload" ? "Current assignments across all enquiry dates. Due today includes overdue follow-ups from earlier today; each lead counts once per column." : "Activity recorded by each CE in the selected period, including leads later reassigned. Qualification % = qualified leads ÷ distinct leads called. Later PS updates do not change this credit."}</p>
      <div className={styles.scroll}><table><thead><tr><th scope="col">CE</th>{columns.map(([key, title, detail]) => <th scope="col" title={detail} key={key}>{title}</th>)}{tab === "activity" && <><th scope="col" title="Qualified leads divided by distinct leads called by this CE in the period.">Qualification %</th><th scope="col">Last call in period</th></>}</tr></thead><tbody>{data?.results.map(row => <tr key={row.id}><td><b>{row.name}</b><small>{row.email}</small><small>{row.branch || "No branch"}{row.lifecycle !== "ACTIVE" ? ` · ${row.lifecycle.toLowerCase()}` : ""}</small></td>{columns.map(([key]) => <td key={key} className={key === "overdue" && row[key] > 0 ? styles.overdue : undefined}>{row[key]}</td>)}{tab === "activity" && <><td>{row.qualification_rate === null ? "—" : `${row.qualification_rate}%`}</td><td>{row.last_call ? formatDateTime(row.last_call) : "No calls logged"}</td></>}</tr>)}</tbody></table>{!data?.results.length && <p className={styles.empty}>{loading ? "Loading CE performance…" : !valid ? "Choose an activity period." : error ? "Report unavailable. Use Refresh to retry." : "No CEs match these filters."}</p>}</div>
    </section>
    <p className={styles.updated}>Refreshes every 30 seconds while open{data ? ` · Updated ${formatDateTime(data.generated_at)}` : ""}</p>
  </section>;
}
