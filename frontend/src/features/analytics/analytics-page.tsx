"use client";
import { useCrmRefresh } from "@/lib/use-crm-refresh";

import { EtbrTiles } from "@/components/etbr-tiles";

import { useCallback, useEffect, useRef, useState } from "react";
import { formatDateTime } from "@/lib/dates";
import { getAdminAnalytics, getMyAnalytics, getUserLifecycleHistory, type Analytics, type AnalyticsOfficer, type Metrics } from "@/lib/crm";

export function AnalyticsPage({ personal = false }: { personal?: boolean }) {
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [mine, setMine] = useState<Metrics | null>(null);
  const [selected, setSelected] = useState<AnalyticsOfficer | null>(null);
  const [historyLoading, setHistoryLoading] = useState<number | null>(null);
  const [error, setError] = useState("");
  const requestId = useRef(0);
  const load = useCallback(async () => {
    const request = ++requestId.current;
    try {
      if (personal) {
        const result = await getMyAnalytics();
        if (request === requestId.current) setMine(result);
      } else {
        const result = await getAdminAnalytics();
        if (request === requestId.current) setAnalytics(result);
      }
      if (request === requestId.current) setError("");
    } catch (requestError) {
      if (request === requestId.current) setError(requestError instanceof Error ? requestError.message : "Unable to load analytics.");
    }
  }, [personal]);
  useCrmRefresh(load);
  useEffect(() => { void load(); return () => { requestId.current++; }; }, [load]);
  const rows: AnalyticsOfficer[] = personal && mine ? [{ id: 0, name: "My performance", ...mine }] : (analytics?.officers || []);
  const followUps = [...rows, ...(!personal ? analytics?.cre || [] : [])].reduce((total, row) => total + (row.followup_untouched || 0), 0);
  const openHistory = async (officer: AnalyticsOfficer) => {
    setHistoryLoading(officer.id); setError("");
    try { setSelected({ ...officer, ...await getUserLifecycleHistory(officer.id) }); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Account history could not be loaded."); }
    finally { setHistoryLoading(null); }
  };

  return <section className="page">
    <div className="page-heading"><div><p className="eyebrow">{personal ? "MY RESULTS" : "PIPELINE INTELLIGENCE"}</p><h1>{personal ? <>Your work, <span>in focus.</span></> : <>Turn every enquiry into a <span>clear next step.</span></>}</h1></div></div>
    {error && <div className="empty-state">{error}</div>}
    {!personal && <EtbrTiles data={analytics?.summary} />}<section className="analytics-grid">
      <article className="panel table-panel"><header className="panel-heading"><div><p className="eyebrow">{personal ? "MY PERFORMANCE" : "PS/SO PERFORMANCE"}</p><h2>{personal ? "Your conversion rate" : "PS/SO performance"}</h2></div></header><div className="table-scroll"><table><thead><tr><th>Officer</th><th>Assigned</th><th>Called</th><th>Untouched by owner</th><th>Qualified</th><th>Booked</th><th>Won</th><th>Rate</th></tr></thead><tbody>{rows.length ? rows.map(officer => <tr key={officer.id}><td>{personal ? <b>{officer.name}</b> : <button className="analytics-officer-link" disabled={historyLoading === officer.id} onClick={() => void openHistory(officer)}><b>{historyLoading === officer.id ? "Loading history…" : officer.name}</b>{officer.lifecycle_status && officer.lifecycle_status !== "ACTIVE" && <small className={`account-state ${officer.lifecycle_status.toLowerCase()}`}>{officer.lifecycle_status === "DELETED" ? "Deleted" : "Disabled"}</small>}</button>}</td><td>{officer.total_assigned}</td><td>{officer.total_called}</td><td>{officer.untouched ?? 0}</td><td>{officer.qualified}</td><td>{officer.booked}</td><td>{officer.won}</td><td><span className="status qualified">{officer.conversion_rate}%</span></td></tr>) : <tr><td colSpan={8}>No analytics available yet.</td></tr>}</tbody></table></div></article>
      <article className="panel"><p className="eyebrow">FOLLOW-UP LOAD</p><h2>Needs attention</h2><div className="follow-total"><b>{followUps}</b><span>active untouched assignments</span></div>{!personal && <><div className="follow-line"><span>Untouched by CE</span><b>{analytics?.cre.reduce((sum, row) => sum + (row.followup_untouched || 0), 0) ?? 0}</b></div><div className="follow-line"><span>Untouched by PS</span><b>{analytics?.officers.reduce((sum, row) => sum + (row.followup_untouched || 0), 0) ?? 0}</b></div></>}<div className="follow-line"><span><i className="urgent" />Open pipeline</span><b>{personal ? mine?.active_pipeline ?? 0 : analytics?.summary.active_pipeline ?? 0} leads</b></div></article>
    </section>
    {selected && <div className="modal-layer" role="presentation"><section className="modal lifecycle-report-modal" role="dialog" aria-modal="true" aria-labelledby="account-history-title"><button className="modal-close" onClick={() => setSelected(null)} aria-label="Close">×</button><p className="eyebrow">HISTORICAL ACCOUNT RECORD</p><h2 id="account-history-title">{selected.name}</h2><span className={`account-state ${(selected.lifecycle_status || "ACTIVE").toLowerCase()}`}>{selected.lifecycle_status === "DELETED" ? "Deleted" : selected.lifecycle_status === "DISABLED" ? "Disabled" : "Active"}</span><div className="lifecycle-event-list">{selected.account_history?.length ? selected.account_history.map((event, index) => <article key={`${event.action}-${event.created_at}-${index}`}><header><b>{event.action === "DELETED" ? "Permanently deleted" : event.action.charAt(0) + event.action.slice(1).toLowerCase()}</b><time>{formatDateTime(event.created_at)}</time></header><small>By {event.actor}</small>{event.reason && <p>{event.reason}</p>}<dl><div><dt>Active leads handled</dt><dd>{String(event.summary.actionable_leads ?? "—")}</dd></div><div><dt>Moved to pool</dt><dd>{String(event.summary.pooled_leads ?? "—")}</dd></div><div><dt>Follow-ups held</dt><dd>{String(event.summary.followups_held ?? "—")}</dd></div><div><dt>Closed history retained</dt><dd>{String(event.summary.closed_leads_retained ?? "—")}</dd></div></dl></article>) : <div className="empty-state">No account lifecycle actions have been recorded.</div>}</div><footer><button className="filter" onClick={() => setSelected(null)}>Close</button></footer></section></div>}
    <style>{`
      .analytics-officer-link { border: 0; background: none; padding: 0; text-align: left; cursor: pointer; }
      .account-state { display: inline-block; width: max-content; margin-top: 4px; border-radius: 4px; padding: 3px 6px; background: #e8f6ef; color: #257453; font: 9px ui-monospace, SFMono-Regular, Menlo, monospace; text-transform: uppercase; }
      .account-state.disabled { background: #fff4dd; color: #906415; }
      .account-state.deleted { background: #f8eeee; color: #a43f3f; }
      .lifecycle-report-modal { width: min(620px, 100%); max-height: 85vh; overflow: auto; }
      .lifecycle-report-modal h2 { margin-bottom: 6px; }
      .lifecycle-event-list { display: grid; gap: 10px; margin-top: 18px; }
      .lifecycle-event-list article { border: 1px solid #e4e6e3; border-left: 4px solid #d49a2f; border-radius: 8px; padding: 13px; }
      .lifecycle-event-list header { display: flex; justify-content: space-between; gap: 12px; }
      .lifecycle-event-list time, .lifecycle-event-list small { color: #8a9095; font: 9px ui-monospace, SFMono-Regular, Menlo, monospace; }
      .lifecycle-event-list p { margin: 10px 0 0; color: #555d60; font-size: 11px; }
      .lifecycle-event-list dl { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin: 12px 0 0; }
      .lifecycle-event-list dl div { border-radius: 6px; background: #f5f6f4; padding: 8px; }
      .lifecycle-event-list dt { color: #89908d; font-size: 8px; }
      .lifecycle-event-list dd { margin: 4px 0 0; color: #27302d; font-weight: 700; }
      @media (max-width: 560px) { .lifecycle-event-list dl { grid-template-columns: 1fr 1fr; } }
    `}</style>
  </section>;
}
