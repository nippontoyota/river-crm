"use client";

import { useState } from "react";
import { completeTestDrive, type LeadDetail } from "@/lib/crm";
import { formatDateTime } from "@/lib/dates";

export function TestDriveCompletion({ lead, canComplete, onCompleted }: { lead: LeadDetail; canComplete: boolean; onCompleted: (lead: LeadDetail) => void }) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const complete = async () => {
    setSaving(true); setError("");
    try { onCompleted(await completeTestDrive(lead.id)); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Unable to record test drive completion."); }
    finally { setSaving(false); }
  };
  return <section className="sales-info-card">
    <h3>Test drive</h3>
    {lead.test_drive_completed_at ? <p role="status">Completed · {formatDateTime(lead.test_drive_completed_at)}</p> : <>
      <p className="subtext">Completion has not been recorded.</p>
      {canComplete && <button type="button" className="button primary" disabled={saving} onClick={() => void complete()}>{saving ? "Saving…" : "Mark test drive completed"}</button>}
    </>}
    {error && <p className="form-error" role="alert">{error}</p>}
  </section>;
}
