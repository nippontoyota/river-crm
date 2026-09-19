"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { commitUpload, getUpload, getUploadSummary, uploadLeads, type UploadBatch, type UploadSummary } from "@/lib/crm";
import { formatDateTime } from "@/lib/dates";
import { downloadLeadSample } from "@/lib/lead-sample";
import { UploadReview } from "@/features/intake/upload-review";

const statusLabels = { PARSING: "Checking file", READY: "Awaiting import", COMMITTED: "Imported", FAILED: "File needs correction" };

export function BulkUploadPage() {
  const [batch, setBatch] = useState<UploadBatch | null>(null);
  const [summary, setSummary] = useState<UploadSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [refreshing, setRefreshing] = useState(true);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const [summaryError, setSummaryError] = useState("");
  const [notice, setNotice] = useState("");
  const reviewRef = useRef<HTMLElement>(null);
  const parsingId = batch?.status === "PARSING" ? batch.id : null;
  const locked = busy || reviewing || !!parsingId;

  const refreshSummary = useCallback(() => getUploadSummary()
    .then(result => { setSummary(result); setSummaryError(""); })
    .catch(error => setSummaryError(error instanceof Error ? error.message : "Unable to load upload totals. Refresh to try again."))
    .finally(() => setRefreshing(false)), []);

  useEffect(() => {
    void refreshSummary();
    window.addEventListener("focus", refreshSummary);
    return () => window.removeEventListener("focus", refreshSummary);
  }, [refreshSummary, batch?.id, batch?.status]);

  useEffect(() => {
    if (!parsingId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await getUpload(parsingId);
        if (!cancelled) {
          setBatch(next);
          if (next.status === "PARSING") timer = setTimeout(poll, 1500);
        }
      } catch (error) {
        if (!cancelled) setError(error instanceof Error ? error.message : "Unable to check upload. Use Check import to retry.");
      }
    };
    void poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [parsingId]);

  const selectFile = async (file?: File) => {
    if (!file || locked) return;
    setError(""); setNotice("");
    if (!/\.(csv|xlsx)$/i.test(file.name) || file.size > 10 * 1024 * 1024) {
      setError("Choose a CSV or XLSX file up to 10 MB."); return;
    }
    setBusy(true); setBatch(null);
    try { setBatch(await uploadLeads(file)); }
    catch (error) { setError(error instanceof Error ? error.message : "Upload failed."); }
    finally { setBusy(false); }
  };

  const check = async (id = batch?.id) => {
    if (!id || busy || reviewing) return;
    setBusy(true); setError("");
    try {
      setBatch(await getUpload(id));
      requestAnimationFrame(() => reviewRef.current?.scrollIntoView({ block: "start" }));
    } catch (error) { setError(error instanceof Error ? error.message : "Unable to check upload."); }
    finally { setBusy(false); }
  };

  const importLeads = async () => {
    if (!batch || busy || reviewing || batch.status !== "READY" || batch.pending_duplicates || batch.validation_errors_found || !batch.total_rows) return;
    setBusy(true); setError("");
    try {
      const result = await commitUpload(batch.id);
      setBatch(null);
      setNotice(`${result.created} leads imported. ${result.overwritten} existing leads updated. ${result.skipped} rows skipped. New leads are now in the admin assignment pool.`);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Import failed.");
      setBatch(await getUpload(batch.id).catch(() => batch));
    } finally { setBusy(false); }
  };

  const totals = summary?.totals;
  const tiles = [
    { label: "Leads imported", value: totals?.imported_leads, note: "New leads added to CRM", icon: "↗", className: "imported" },
    { label: "Existing leads updated", value: totals?.updated_leads, note: "Approved duplicate updates", icon: "↻", className: "updated" },
    { label: "Awaiting import", value: totals?.awaiting_import, note: "Files to check and import", icon: "◷", className: "pending" },
    { label: "Files uploaded", value: totals?.total_uploads, note: totals?.failed_uploads ? `${totals.failed_uploads} ${totals.failed_uploads === 1 ? "file needs" : "files need"} correction` : "All your spreadsheet uploads", icon: "▤", className: "files" },
  ];

  return <section className="page intake-page uploader-page">
    <header className="uploader-heading"><div><p className="eyebrow">META UPLOADER · YOUR UPLOADS</p><h1>Bring your leads <span>into CRM.</span></h1><p className="subtext">Upload, review, and send company enquiries to the admin assignment pool.</p></div><button className="filter" disabled={refreshing || locked} onClick={() => { setRefreshing(true); void refreshSummary(); }}>{refreshing ? "Refreshing…" : "↻ Refresh totals"}</button></header>
    {summaryError && <p className="intake-error" role="alert">{summaryError}</p>}
    <section className="uploader-metrics" aria-label="Your upload analytics, all time" aria-busy={refreshing}>
      {tiles.map(tile => <article className={`uploader-metric ${tile.className}`} key={tile.label}><div><p>{tile.label}</p><span aria-hidden="true">{tile.icon}</span></div><strong>{tile.value === undefined ? "—" : tile.value.toLocaleString("en-IN")}</strong><small>{tile.note}</small></article>)}
    </section>
    <div className="uploader-workspace">
      <section className="panel uploader-file-panel">
        <header><div><p className="eyebrow">NEW UPLOAD</p><h2>Upload your spreadsheet</h2></div><span className="uploader-file-types">CSV / XLSX</span></header>
        <p className="subtext">Use the sample format. We’ll check every row before you import.</p>
        <label className={`uploader-dropzone ${dragging ? "dragging" : ""} ${locked ? "disabled" : ""}`} onDragOver={event => { event.preventDefault(); if (!locked) setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={event => {
          event.preventDefault(); setDragging(false);
          if (event.dataTransfer.files.length !== 1) { setError("Choose one spreadsheet at a time."); return; }
          void selectFile(event.dataTransfer.files[0]);
        }}>
          <input aria-label="Upload bulk leads" type="file" accept=".csv,.xlsx" disabled={locked} onChange={event => { const file = event.target.files?.[0]; event.target.value = ""; void selectFile(file); }} />
          <span className="uploader-upload-icon" aria-hidden="true">↑</span>
          <strong>{busy ? "Working on your upload…" : parsingId ? "Checking your spreadsheet…" : "Drop your spreadsheet here"}</strong>
          <span>{locked ? "Please wait before choosing another file" : "or click to browse your files"}</span>
          <span className="uploader-choose" aria-hidden="true">Choose file</span>
          <small>One CSV or XLSX file · Up to 10 MB · 1,000 leads</small>
        </label>
        <footer><span>Start with the right columns.</span><button className="filter" onClick={() => downloadLeadSample("META")}>↓ Download sample format</button></footer>
      </section>
      <aside className="panel uploader-guide">
        <p className="eyebrow">BEFORE YOU UPLOAD</p><h2>One format. Every lead.</h2>
        <p className="subtext">Keep these seven column headings exactly as shown in the sample.</p>
        <div className="uploader-columns">{["name", "phone", "email", "source", "enquiry date", "city", "pincode"].map(field => <code key={field}>{field}</code>)}</div>
        <dl><div><dt>City</dt><dd>Up to 100 characters. Leave blank if unknown.</dd></div><div><dt>Pincode</dt><dd>Six digits, starting with 1–9. Leave blank if unknown.</dd></div><div><dt>Phone</dt><dd>Used to find repeated and existing leads.</dd></div><div><dt>Source</dt><dd>Use a configured source, such as META.</dd></div><div><dt>Enquiry date</dt><dd>DD/MM/YYYY, for example 17/09/2026.</dd></div></dl>
        <div className="uploader-handoff"><span aria-hidden="true">✓</span><p><b>Connected to your CRM</b>After you select Import leads, new leads appear in the admin pool. Existing assignment and reporting rules apply.</p></div>
      </aside>
    </div>
    {error && <p className="intake-error uploader-message" role="alert">{error}</p>}
    {notice && <p className="uploader-success" role="status"><span aria-hidden="true">✓</span>{notice}</p>}
    {batch && <section ref={reviewRef} className="panel bulk-import-review uploader-review">
      <header><div><p className="eyebrow">{statusLabels[batch.status]}</p><h2>{batch.status === "PARSING" ? "Checking your file…" : batch.status === "FAILED" ? "Correct your spreadsheet" : batch.status === "COMMITTED" ? "Import complete" : "Review before importing"}</h2><p className="subtext">{batch.filename}</p></div><button className="filter" disabled={busy || reviewing} onClick={() => void check()}>Check import</button></header>
      {batch.status === "READY" && <><p className="uploader-review-counts">{batch.total_rows} rows · {batch.parsed_ok} ready · {batch.pending_duplicates} duplicates need review · {batch.skipped} skipped · {batch.validation_errors_found} invalid</p><p className="subtext">Correct errors in your spreadsheet and upload it again. Approve or reject duplicates below.</p></>}
      {batch.status === "COMMITTED" && <p className="uploader-success">This file has already been imported into CRM.</p>}
      {batch.error_message && <p className="intake-error" role="alert">{batch.error_message}</p>}
      <UploadReview key={batch.id} batch={batch} onChange={setBatch} disabled={busy} onBusyChange={setReviewing} />
      {batch.status === "READY" && <footer><p>New leads will be available to Admin for assignment.</p><button className="button primary" disabled={busy || reviewing || !!batch.pending_duplicates || !!batch.validation_errors_found || !batch.total_rows} onClick={() => void importLeads()}>{busy ? "Importing…" : "Import leads"}</button></footer>}
    </section>}
    <section className="panel uploader-history">
      <header><div><p className="eyebrow">UPLOAD HISTORY</p><h2>Recent uploads</h2></div><span>Latest 10 files · Your account</span></header>
      {!summary ? <p className="uploader-empty">{summaryError ? "Upload history is unavailable. Refresh totals to try again." : "Loading your upload history…"}</p> : !summary.recent.length ? <div className="uploader-empty"><span aria-hidden="true">▤</span><h3>Your first upload starts here</h3><p>Choose a spreadsheet above. Its status and import results will appear here.</p></div> : <div className="intake-table-wrap"><table><thead><tr><th>File / uploaded</th><th>Status</th><th>Rows</th><th>New leads</th><th>Updated</th><th>Skipped</th><th>Action</th></tr></thead><tbody>{summary.recent.map(item => <tr key={item.id}><td><b>{item.filename}</b><small>{formatDateTime(item.created_at)}</small></td><td><span className={`uploader-status ${item.status.toLowerCase()}`}>{statusLabels[item.status]}</span></td><td>{item.total_rows}</td><td>{item.status === "COMMITTED" ? item.imported_leads : "—"}</td><td>{item.status === "COMMITTED" ? item.updated_leads : "—"}</td><td>{item.status === "COMMITTED" ? item.skipped : "—"}</td><td><button className="filter" disabled={locked} aria-label={`View upload ${item.filename}`} onClick={() => void check(item.id)}>{item.status === "READY" ? "Review →" : "View →"}</button></td></tr>)}</tbody></table></div>}
    </section>
  </section>;
}
