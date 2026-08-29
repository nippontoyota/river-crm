"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getAdminAnalytics, getLeads, sourceClass, sourceName, statusName, type Analytics, type Lead } from "@/lib/crm";

export function AdminDashboard() {
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { void Promise.all([getAdminAnalytics(), getLeads("?unassigned=true")]).then(([data, pool]) => { setAnalytics(data); setLeads(pool); }).catch(requestError => setError(requestError instanceof Error ? requestError.message : "Unable to load dashboard.")); }, []);
  const summary = analytics?.summary;
  const total = summary?.total_assigned || 0;
  const route = [["Enquiries", total], ["Contacted", summary?.total_called || 0], ["Qualified", summary?.qualified || 0], ["Walk-in", summary?.walkins || 0], ["Won", summary?.won || 0]];
  return <section className="page">
    <div className="page-heading"><div><p className="eyebrow">PIPELINE OVERVIEW</p><h1>Your showroom, <span>in motion.</span></h1><p className="subtext">Live lead flow and sales activity from the CRM.</p></div></div>
    {error && <div className="empty-state">{error}</div>}
    <section className="metric-grid"><Metric label="Total leads" value={total || "—"} dark /><Metric label="Qualified" value={summary?.qualified ?? "—"} suffix={total ? `/${total}` : undefined} detail={total ? `${((summary?.qualified || 0) / total * 100).toFixed(1)}% qualification rate` : "No leads yet"} /><Metric label="Walk-ins booked" value={summary?.walkins ?? "—"} detail="Across the active pipeline" /><Metric label="Retail conversions" value={summary?.won ?? "—"} detail={summary ? `${summary.conversion_rate}% conversion rate` : "No leads yet"} /></section>
    <section className="dashboard-grid"><article className="panel"><PanelHeading eyebrow="LEAD HEALTH" title="Conversion route" action="View report →" href="/analytics" /><div className="funnel">{route.map(([label, value]) => <div className="funnel-row" key={label}><span>{label}</span><div className="progress"><i className={label === "Won" ? "won" : ""} style={{ width: `${total ? Math.max((Number(value) / total) * 100, 4) : 0}%` }} /></div><b>{value}</b><small>{total ? `${((Number(value) / total) * 100).toFixed(1)}%` : "—"}</small></div>)}</div></article><article className="panel"><PanelHeading eyebrow="ACQUISITION" title="Where demand starts" /><div className="source-split"><div className="donut"><div><b>{total}</b><small>total leads</small></div></div><ul className="source-list">{analytics?.source.length ? analytics.source.map(source => <li key={source.source}><i className={sourceClass(source.source)} /><span>{sourceName(source.source)}</span><b>{source.total}</b><small>{total ? `${((source.total / total) * 100).toFixed(1)}%` : "—"}</small></li>) : <li><span>No lead sources yet.</span></li>}</ul></div></article></section>
    <section className="panel table-panel"><PanelHeading eyebrow="OPERATOR QUEUE" title="Leads waiting for a handoff" action="Assign leads →" href="/leads" /><div className="table-scroll"><table><thead><tr><th>Customer</th><th>Source</th><th>Model interest</th><th>Enquired</th><th>Signal</th><th /></tr></thead><tbody>{leads.length ? leads.slice(0, 5).map(lead => <tr key={lead.id}><td><b>{lead.name}</b><small>#{lead.id} · {lead.phone}</small></td><td><span className={`badge ${sourceClass(lead.source)}`}>{lead.source}</span></td><td>{lead.model}</td><td>{lead.enquiredAt}</td><td><span className={`status ${lead.status.toLowerCase()}`}>{statusName(lead.status)}</span></td><td><Link className="row-action" href="/leads">Open →</Link></td></tr>) : <tr><td colSpan={6}>No unassigned leads.</td></tr>}</tbody></table></div></section>
  </section>;
}

function Metric({ label, value, suffix, detail, dark }: { label: string; value: string | number; suffix?: string; detail?: string; dark?: boolean }) { return <article className={`metric ${dark ? "metric-dark" : ""}`}><p>{label}</p><strong>{value}{suffix && <small>{suffix}</small>}</strong><span>{detail || "Live CRM data"}</span><div className="metric-mark" /></article>; }
function PanelHeading({ eyebrow, title, action, href }: { eyebrow: string; title: string; action?: string; href?: string }) { return <header className="panel-heading"><div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2></div>{action && href && <Link href={href}>{action}</Link>}</header>; }
