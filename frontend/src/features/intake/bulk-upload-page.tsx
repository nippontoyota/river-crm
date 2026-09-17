"use client";

import { useEffect, useState } from "react";
import { commitUpload, getUpload, uploadLeads, type UploadBatch } from "@/lib/crm";
import { downloadLeadSample } from "@/lib/lead-sample";
import { UploadReview } from "@/features/intake/upload-review";

export function BulkUploadPage() {
  const [batch, setBatch] = useState<UploadBatch | null>(null);
  const [busy, setBusy] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const parsingId = batch?.status === "PARSING" ? batch.id : null;

  useEffect(() => {
    if (!parsingId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await getUpload(parsingId, true);
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
    if (!file || busy || reviewing) return;
    setBusy(true); setError(""); setNotice(""); setBatch(null);
    try { setBatch(await uploadLeads(file)); }
    catch (error) { setError(error instanceof Error ? error.message : "Upload failed."); }
    finally { setBusy(false); }
  };

  const check = async () => {
    if (!batch || busy || reviewing) return;
    setBusy(true); setError("");
    try { setBatch(await getUpload(batch.id, true)); }
    catch (error) { setError(error instanceof Error ? error.message : "Unable to check upload."); }
    finally { setBusy(false); }
  };

  const importLeads = async () => {
    if (!batch || busy || reviewing || batch.status !== "READY" || batch.pending_duplicates || batch.validation_errors_found || !batch.parsed_ok) return;
    setBusy(true); setError("");
    try {
      const result = await commitUpload(batch.id);
      setBatch(null);
      setNotice(`${result.created} leads imported. ${result.overwritten} existing leads updated. ${result.skipped} rows skipped. New leads are ready for admin assignment.`);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Import failed.");
      setBatch(await getUpload(batch.id, true).catch(() => batch));
    } finally { setBusy(false); }
  };

  return <section className="page intake-page">
    <header className="page-heading"><div><p className="eyebrow">META UPLOADER</p><h1>Bulk lead upload</h1><p className="subtext">Upload company leads using the existing sample format.</p></div></header>
    <section className="panel">
      <h2>Upload your spreadsheet</h2>
      <p>Use these headings: <code>name, phone, email, source, enquiry date</code>.</p>
      <p className="subtext">CSV or XLSX, up to 10 MB. Use a configured lead source, such as META, and dates in DD/MM/YYYY format. Correct any errors in your spreadsheet and upload it again.</p>
      <div className="intake-actions">
        <button className="filter" onClick={() => downloadLeadSample("META")}>Download sample format</button>
        <label>{busy ? "Working…" : "Bulk Upload"}<input aria-label="Upload bulk leads" type="file" accept=".csv,.xlsx" disabled={busy || reviewing || !!parsingId} onChange={event => { const file = event.target.files?.[0]; event.target.value = ""; void selectFile(file); }} /></label>
      </div>
    </section>
    {error && <p className="intake-error" role="alert">{error}</p>}
    {notice && <p className="panel" role="status">{notice}</p>}
    {batch && <section className="panel bulk-import-review" style={{ marginTop: "1rem" }}>
      <h2>{batch.status === "PARSING" ? "Checking your file…" : batch.status === "FAILED" ? "File could not be imported" : "Review import"}</h2>
      <p className="subtext">{batch.filename}</p>
      {batch.status === "READY" && <p>{batch.total_rows} rows · {batch.parsed_ok} ready · {batch.pending_duplicates} duplicates need review · {batch.skipped} skipped · {batch.validation_errors_found} invalid</p>}
      <div className="intake-actions">
        <button className="filter" disabled={busy || reviewing} onClick={() => void check()}>Check import</button>
        {batch.status === "READY" && <button className="button primary" disabled={busy || reviewing || !!batch.pending_duplicates || !!batch.validation_errors_found || !batch.parsed_ok} onClick={() => void importLeads()}>{busy ? "Working…" : "Import leads"}</button>}
      </div>
      {batch.error_message && <p className="intake-error" role="alert">{batch.error_message}</p>}
      <UploadReview key={batch.id} batch={batch} onChange={setBatch} disabled={busy} onBusyChange={setReviewing} />
    </section>}
  </section>;
}
