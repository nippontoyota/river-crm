"use client";
import { useState } from "react";
import { count, label, numeric, type Overview } from "@/lib/ceo";
import { formatDate } from "@/lib/dates";

export function Trends({ overview, onAge }: { overview: Overview; onAge: (age: string) => void }) {
  const [kind, setKind] = useState("E");
  const rows = overview.trend || [];
  const maximum = Math.max(Math.ceil(Math.max(...rows.map(row => numeric(row[kind])), 0) / 2) * 2, 2);
  const points = rows.map((row, i) => ({ x: 30 + i * 600 / Math.max(rows.length - 1, 1), y: 138 - numeric(row[kind]) / maximum * 108, row }));
  return <div className="ceo-trend-grid">
    <section className="ceo-panel">
      <header><h2>ETBR trend</h2><select aria-label="Trend milestone" value={kind} onChange={event => setKind(event.target.value)}>{["E", "T", "B", "R"].map(value => <option key={value} value={value}>{label(value)}</option>)}</select></header>
      {points.length ? <svg className="ceo-trend-chart" viewBox="0 0 660 178" role="img" aria-label={`${label(kind)} by ${overview.trend_interval || "day"}, ${rows.length} reporting dates`}>
        {[0, 0.5, 1].map(fraction => <g key={fraction}><line x1="30" x2="630" y1={138 - fraction * 108} y2={138 - fraction * 108} stroke="#e7edf3" /><text x="22" y={142 - fraction * 108} textAnchor="end">{Math.round(maximum * fraction)}</text></g>)}
        <polyline points={points.map(point => `${point.x},${point.y}`).join(" ")} fill="none" stroke="#087f78" strokeWidth="2.5" />
        {points.map(point => <circle key={String(point.row.date)} cx={point.x} cy={point.y} r="4" fill="#087f78"><title>{formatDate(String(point.row.date))}: {count(point.row[kind])} {label(kind).toLowerCase()}</title></circle>)}
        <text x="30" y="166">{formatDate(String(rows[0].date))}</text><text x="630" y="166" textAnchor="end">{formatDate(String(rows[rows.length - 1].date))}</text>
      </svg> : <p className="ceo-empty">No verified milestones in this selection.</p>}
      <details className="ceo-trend-data"><summary>View trend data</summary><div className="ceo-table-scroll"><table><thead><tr><th>Date</th><th>{label(kind)}</th></tr></thead><tbody>{rows.map(row => <tr key={String(row.date)}><td>{formatDate(String(row.date))}</td><td>{count(row[kind])}</td></tr>)}</tbody></table></div></details>
    </section>
    <section className="ceo-panel"><header><h2>Open lead age</h2><span>Days since enquiry · current</span></header><div className="ceo-age-list">{[["0_3", "0–3 days"], ["4_7", "4–7 days"], ["8_14", "8–14 days"], ["15_30", "15–30 days"], ["31_plus", "31+ days"]].map(([key, title]) => <button key={key} onClick={() => onAge(key)}><span>{title}</span><i><b style={{ width: `${numeric(overview.ageing?.[key]) / Math.max(...Object.values(overview.ageing || {}), 1) * 100}%` }} /></i><strong>{count(overview.ageing?.[key])} ↗</strong></button>)}</div></section>
  </div>;
}
