"use client";

import { useEffect, useState } from "react";
import { getReceptionistAnalytics, type ReceptionistAnalytics } from "@/lib/crm";

export default function ReceptionistDashboardPage() {
  const [analytics, setAnalytics] = useState<ReceptionistAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

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
          <p className="subtext">Overview of leads captured today.</p>
        </div>
      </div>
      
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1rem", marginBottom: "2rem" }}>
        <div className="panel" style={{ padding: "1.5rem" }}>
          <p className="eyebrow">TOTAL LEADS TODAY</p>
          <div style={{ fontSize: "2rem", fontWeight: "bold" }}>{analytics.summary.total}</div>
        </div>
        <div className="panel" style={{ padding: "1.5rem" }}>
          <p className="eyebrow">WALK-IN LEADS</p>
          <div style={{ fontSize: "2rem", fontWeight: "bold" }}>{analytics.summary.walkin}</div>
        </div>
        <div className="panel" style={{ padding: "1.5rem" }}>
          <p className="eyebrow">DIGITAL LEADS</p>
          <div style={{ fontSize: "2rem", fontWeight: "bold" }}>{analytics.summary.digital}</div>
        </div>
      </div>

      <h2>SO Assignment Breakdown</h2>
      <div className="panel" style={{ marginTop: "1rem" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border-color)", textAlign: "left" }}>
              <th style={{ padding: "1rem" }}>Sales Officer</th>
              <th style={{ padding: "1rem", textAlign: "right" }}>Leads Assigned Today</th>
            </tr>
          </thead>
          <tbody>
            {analytics.so_breakdown.length === 0 ? (
              <tr><td colSpan={2} style={{ padding: "1rem", textAlign: "center" }}>No leads assigned today.</td></tr>
            ) : (
              analytics.so_breakdown.map((so, index) => (
                <tr key={index} style={{ borderBottom: "1px solid var(--border-color)" }}>
                  <td style={{ padding: "1rem" }}>{so.name}</td>
                  <td style={{ padding: "1rem", textAlign: "right", fontWeight: "bold" }}>{so.count}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
