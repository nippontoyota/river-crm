"use client";

import { EtbrTiles } from "@/components/etbr-tiles";
import { useCrmRefresh } from "@/lib/use-crm-refresh";

import { useEffect, useState } from "react";
import { getReceptionistAnalytics, type ReceptionistAnalytics } from "@/lib/crm";

export default function ReceptionistDashboardPage() {
  const [analytics, setAnalytics] = useState<ReceptionistAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useCrmRefresh(() => getReceptionistAnalytics()
    .then(result => { setAnalytics(result); setError(""); })
    .catch(err => setError(err instanceof Error ? err.message : "Failed to load dashboard")));

  useEffect(() => {
    getReceptionistAnalytics()
      .then(setAnalytics)
      .catch(err => setError(err instanceof Error ? err.message : "Failed to load dashboard"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="page" style={{ padding: "2rem" }}>Loading dashboard...</div>;
  if (error) return <div className="page" style={{ padding: "2rem" }}>{error}</div>;
  if (!analytics) return null;

  return (
    <div className="page" style={{ padding: "2rem" }}>
      <div className="page-heading">
        <div>
          <h1>Receptionist Dashboard</h1>
          <p className="subtext">Your walk-in enquiries captured today.</p>
        </div>
      </div>
      
      <EtbrTiles data={analytics.summary} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1rem", marginBottom: "2rem" }}>
        <div className="panel" style={{ padding: "1.5rem" }}>
          <p className="eyebrow">TOTAL LEADS TODAY</p>
          <div style={{ fontSize: "2rem", fontWeight: "bold" }}>{analytics.summary.total}</div>
        </div>
        <div className="panel" style={{ padding: "1.5rem" }}>
          <p className="eyebrow">WALK-IN LEADS</p>
          <div style={{ fontSize: "2rem", fontWeight: "bold" }}>{analytics.summary.walkin}</div>
        </div>
      </div>

      <h2>SO Assignment Breakdown</h2>
      <p className="subtext">Your walk-in leads captured today and this calendar month, grouped by their current sales officer. Dates use India time.</p>
      <div className="panel" style={{ marginTop: "1rem" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border-color)", textAlign: "left" }}>
              <th style={{ padding: "1rem" }}>Sales Officer</th>
              <th style={{ padding: "1rem", textAlign: "right" }}>Leads Assigned Today</th>
              <th style={{ padding: "1rem", textAlign: "right" }}>Leads Assigned This Month</th>
            </tr>
          </thead>
          <tbody>
            {analytics.so_breakdown.length === 0 ? (
              <tr><td colSpan={3} style={{ padding: "1rem", textAlign: "center" }}>No leads captured this month.</td></tr>
            ) : (
              analytics.so_breakdown.map(so => (
                <tr key={so.so_id ?? "unassigned"} style={{ borderBottom: "1px solid var(--border-color)" }}>
                  <td style={{ padding: "1rem" }}>{so.name}</td>
                  <td style={{ padding: "1rem", textAlign: "right", fontWeight: "bold" }}>{so.count}</td>
                  <td style={{ padding: "1rem", textAlign: "right", fontWeight: "bold" }}>{so.month_count}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
