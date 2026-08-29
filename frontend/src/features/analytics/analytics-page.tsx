"use client";

import { useEffect, useState } from "react";
import { getAdminAnalytics, getMyAnalytics, type Analytics, type Metrics } from "@/lib/crm";

export function AnalyticsPage({ personal = false }: { personal?: boolean }) {
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [mine, setMine] = useState<Metrics | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { void (personal ? getMyAnalytics().then(setMine) : getAdminAnalytics().then(setAnalytics)).catch(requestError => setError(requestError instanceof Error ? requestError.message : "Unable to load analytics.")); }, [personal]);
  const rows = personal && mine ? [{ id: 0, name: "My performance", ...mine }] : [...(analytics?.cre || []), ...(analytics?.officers || [])];
  const followUps = rows.reduce((total, row) => total + Math.max(row.total_assigned - row.total_called, 0), 0);
  return <section className="page"><div className="page-heading"><div><p className="eyebrow">{personal ? "MY RESULTS" : "PIPELINE INTELLIGENCE"}</p><h1>{personal ? <>Your work, <span>in focus.</span></> : <>Turn every enquiry into a <span>clear next step.</span></>}</h1></div></div>{error && <div className="empty-state">{error}</div>}<section className="analytics-grid"><article className="panel table-panel"><header className="panel-heading"><div><p className="eyebrow">{personal ? "MY PERFORMANCE" : "TEAM PERFORMANCE"}</p><h2>{personal ? "Your conversion rate" : "Who is converting"}</h2></div></header><div className="table-scroll"><table><thead><tr><th>Officer</th><th>Assigned</th><th>Called</th><th>Qualified</th><th>Won</th><th>Rate</th></tr></thead><tbody>{rows.length ? rows.map(officer => <tr key={officer.id}><td><b>{officer.name}</b></td><td>{officer.total_assigned}</td><td>{officer.total_called}</td><td>{officer.qualified}</td><td>{officer.won}</td><td><span className="status qualified">{officer.conversion_rate}%</span></td></tr>) : <tr><td colSpan={6}>No analytics available yet.</td></tr>}</tbody></table></div></article><article className="panel"><p className="eyebrow">FOLLOW-UP LOAD</p><h2>Needs attention</h2><div className="follow-total"><b>{followUps}</b><span>leads not yet contacted</span></div><div className="follow-line"><span><i className="urgent" />Open pipeline</span><b>{personal ? mine?.total_assigned ?? 0 : analytics?.summary.total_assigned ?? 0} leads</b></div></article></section></section>;
}
