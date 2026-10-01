"use client";

import { useEffect, useState } from "react";
import { ceoGet, count, exportReport, text, type PageData, type ReportOptions } from "@/lib/ceo";
import { formatDate } from "@/lib/dates";
import { Badge, Drawer, Pagination, ReportTable, SearchField } from "./report-ui";
import { LeadDetailDrawer } from "./lead-detail";

export function AnalysisLeadsModal({ query, title, options, onClose }: { query: string; title: string; options: ReportOptions | null; onClose: () => void }) {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [result, setResult] = useState<{ query: string; data: PageData } | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [exporting, setExporting] = useState(false);
  const [detail, setDetail] = useState<{ id: number; entity: "leads" | "complaints" } | null>(null);
  const params = new URLSearchParams(query);
  params.set("page", String(page));
  if (search) params.set("q", search);
  const request = params.toString();
  const data = result?.query === request ? result.data : null;
  const loading = !data && !error;
  useEffect(() => {
    const controller = new AbortController();
    const next = new URLSearchParams(request);
    if (retry) next.set("refresh", String(retry));
    void ceoGet<PageData>("leads", next.toString(), controller.signal)
      .then(data => { setResult({ query: request, data }); setError(""); })
      .catch(error => { if (error.name !== "AbortError") setError(error.message); });
    return () => controller.abort();
  }, [request, retry]);
  const exportLeads = async () => {
    setExporting(true);
    try { await exportReport("leads", request); }
    catch (error) { setError(error instanceof Error ? error.message : "Export failed."); }
    finally { setExporting(false); }
  };
  return <>
    <Drawer centered wide title={`${title}${data ? ` · ${count(data.count)}` : ""}`} closeLabel="← Back to analysis" onClose={onClose}>
      <div className="ceo-detail-body ceo-analysis-results">
        <p className="ceo-context-line">Matching leads within your dashboard filters. Select a customer to see their details and full history.</p>
        <div className="ceo-table-tools">
          <SearchField value={search} onSearch={value => { setError(""); setSearch(value); setPage(1); }} />
          <button disabled={loading || exporting} onClick={() => void exportLeads()}>{exporting ? "Exporting…" : "Export CSV ↓"}</button>
        </div>
        {error && <p className="ceo-error" role="alert">{error} <button onClick={() => { setError(""); setRetry(value => value + 1); }}>Retry</button></p>}
        <ReportTable caption="Matching customers" loading={loading} rows={data?.results || []} onOpen={row => setDetail({ id: Number(row.id), entity: "leads" })} columns={[
          { key: "name", title: "Customer" },
          { key: "phone", title: "Mobile", render: row => <a href={`tel:${text(row.phone, "")}`}>{text(row.phone)}</a> },
          { key: "next_follow_up", title: "Next date", render: row => formatDate(text(row.next_follow_up, "")) || "Not scheduled" },
          { key: "analysis_status", title: "Latest outcome" },
          { key: "status", title: "Stage", render: row => <Badge value={row.status} /> },
          { key: "so", title: "Sales officer", optional: params.has("analysis_officer") },
        ]} />
        {data && <Pagination page={page} total={data.count} onChange={value => { setError(""); setPage(value); }} />}
      </div>
    </Drawer>
    {detail && <LeadDetailDrawer key={`${detail.entity}-${detail.id}`} {...detail} analysis options={options} onClose={() => setDetail(null)} onOpenLead={id => setDetail({ id, entity: "leads" })} onOpenComplaint={id => setDetail({ id, entity: "complaints" })} />}
  </>;
}
