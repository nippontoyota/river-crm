"use client";

import { useState } from "react";
import { completeTestDrive, type LeadDetail } from "@/lib/crm";
import { formatDateTime } from "@/lib/dates";

export function TestDriveCompletion({ lead, canComplete, onCompleted, disabled = false, onSavingChange }: { lead: LeadDetail; canComplete: boolean; onCompleted: (lead: LeadDetail) => void; disabled?: boolean; onSavingChange?: (saving: boolean) => void }) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const complete = async () => {
    if (saving || disabled) return;
    setSaving(true); onSavingChange?.(true); setError("");
    try { onCompleted(await completeTestDrive(lead.id)); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Unable to record test drive completion."); }
    finally { setSaving(false); onSavingChange?.(false); }
  };
  return <section className="sales-info-card">
    <h3>Test drive</h3>
    {lead.test_drive_completed_at ? <p role="status">Completed · {formatDateTime(lead.test_drive_completed_at)}</p> : <>
      <p className="subtext">Completion has not been recorded.</p>
      {canComplete && lead.outcomePolicy.can_complete_test_drive && <button type="button" className="button primary" disabled={saving || disabled} onClick={() => void complete()}>{saving ? "Saving…" : "Mark test drive completed"}</button>}
    </>}
    {error && <p className="form-error" role="alert">{error}</p>}
  </section>;
}
