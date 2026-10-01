"use client";

import { count, type AnalysisCount, type LeadAnalysisData } from "@/lib/ceo";

type Filters = Record<string, string | null>;
type Props = { data: LeadAnalysisData; loading: boolean; onOpen: (filters: Filters) => void };

export function LeadAnalysis({ data, loading, onOpen }: Props) {
  const link = (title: string, filters: Filters, description: string) => <button className="ceo-link" disabled={loading} onClick={() => onOpen(filters)} aria-label={description}>{title}</button>;
  const totals = (title: string, rows: AnalysisCount[], total: number, lost = false) => {
    const base: Filters = lost ? { analysis_status: "Lost Lead" } : {};
    return <section className={`ceo-table-card ceo-analysis${lost ? " ceo-analysis-lost" : ""}`} aria-busy={loading}>
      <header><h2>{title}</h2></header>
      <div className="ceo-table-scroll" tabIndex={0} role="region" aria-label={title}>
        <table>
          <caption className="ceo-sr-only">{title}</caption>
          <thead><tr><th scope="col">{lost ? "Lost lead reason" : "Lead status"}</th><th scope="col" className="number">Count</th></tr></thead>
          <tbody>{rows.map(row => {
            const filters = { ...base, [lost ? "loss_reason" : "analysis_status"]: row.key };
            return <tr key={row.key}><th scope="row">{link(row.label, filters, `View ${row.label} leads`)}</th><td className="number">{link(count(row.count), filters, `View ${count(row.count)} ${row.label} leads`)}</td></tr>;
          })}</tbody>
          <tfoot><tr><th scope="row">{link("Total", base, `View all ${lost ? "lost " : ""}matching leads`)}</th><td className="number">{link(count(total), base, `View all ${count(total)} ${lost ? "lost " : ""}matching leads`)}</td></tr></tfoot>
        </table>
        {!rows.length && <p className="ceo-empty">No {lost ? "lost " : ""}leads match these filters.</p>}
      </div>
    </section>;
  };
  return <div className="ceo-lead-analysis">
    <p className="ceo-context-line">Latest status now, for enquiries received in the selected dates. Select a name or count to view the matching leads and their history.</p>
    {totals("Lead Status Analysis", data.statuses, data.total)}
    {totals("Lost Lead Analysis", data.loss_reasons, data.lost_total, true)}
    <section className="ceo-table-card ceo-analysis ceo-analysis-officers" aria-busy={loading}>
      <header><div><h2>Sales Officer-wise Lead Status</h2><p>Grouped by current PS/SO assignment.</p></div></header>
      <div className="ceo-table-scroll" tabIndex={0} role="region" aria-label="Sales officer status matrix">
        <table>
          <caption className="ceo-sr-only">Sales Officer-wise Lead Status</caption>
          <thead><tr><th scope="col">Sales officer</th><th scope="col" className="number">{link("Total", {}, "View all matching leads")}</th>{data.statuses.map(status => <th key={status.key} scope="col" className="number">{link(status.label, { analysis_status: status.key }, `View all ${status.label} leads`)}</th>)}</tr></thead>
          <tbody>{data.officers.map(officer => <tr key={officer.key}>
            <th scope="row">{link(officer.name, { analysis_officer: officer.key }, `View leads assigned to ${officer.name}`)}{officer.key !== "__unassigned__" && <small className="ceo-cell-sub">{officer.branch || "No branch"} · #{officer.key}</small>}</th>
            <td className="number">{link(count(officer.total), { analysis_officer: officer.key }, `View all ${count(officer.total)} leads assigned to ${officer.name}`)}</td>
            {data.statuses.map(status => <td key={status.key} className="number">{link(count(officer.statuses[status.key] || 0), { analysis_officer: officer.key, analysis_status: status.key }, `View ${count(officer.statuses[status.key] || 0)} ${status.label} leads assigned to ${officer.name}`)}</td>)}
          </tr>)}</tbody>
          <tfoot><tr><th scope="row">{link("Total", {}, "View all matching leads")}</th><td className="number">{link(count(data.total), {}, `View all ${count(data.total)} matching leads`)}</td>{data.statuses.map(status => <td key={status.key} className="number">{link(count(status.count), { analysis_status: status.key }, `View all ${count(status.count)} ${status.label} leads`)}</td>)}</tr></tfoot>
        </table>
        {!data.officers.length && <p className="ceo-empty">No leads match these filters.</p>}
      </div>
    </section>
  </div>;
}
