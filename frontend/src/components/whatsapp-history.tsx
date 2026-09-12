"use client";

import { useState } from "react";
import { updateWhatsAppAgreement, type LeadDetail } from "@/lib/crm";
import { formatDateTime } from "@/lib/dates";

export const whatsappAgreementLabel = "Customer agrees to receive WhatsApp updates about their enquiry and assigned Sales Officer.";

export function WhatsAppHistory({ lead, onUpdated, disabled = false }: {
  lead: LeadDetail; onUpdated?: (lead: LeadDetail) => void; disabled?: boolean;
}) {
  const [checked, setChecked] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const whatsapp = lead.whatsapp;
  if (!whatsapp) return null;

  async function recordAgreement(agreed: boolean) {
    setSaving(true); setError("");
    try {
      const updated = await updateWhatsAppAgreement(lead.id, agreed);
      onUpdated?.(updated);
      setChecked(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save agreement.");
    } finally { setSaving(false); }
  }

  return <section className="sales-form-card whatsapp-history" aria-label="WhatsApp updates">
    <h3>WhatsApp updates</h3>
    <p className="subtext">{whatsapp.mode === "preview" ? "Preview only — messages are not being sent." : "WhatsApp automation is disabled."}</p>
    <p>{whatsapp.agreed ? `Customer agreement recorded for ${whatsapp.phone}.` : "Customer agreement not recorded for this phone number."}</p>
    {whatsapp.recorded_at && <small>Last updated {formatDateTime(whatsapp.recorded_at)}{whatsapp.recorded_by ? ` by ${whatsapp.recorded_by}` : " automatically"}</small>}
    {onUpdated && whatsapp.can_record_agreement && (whatsapp.enrolled_at || whatsapp.agreed) && <div className="whatsapp-consent-controls">
      {whatsapp.agreed ? <button type="button" className="filter" disabled={saving || disabled} onClick={() => void recordAgreement(false)}>{saving ? "Saving…" : "Record withdrawal"}</button> : <>
        <label className="whatsapp-agreement"><input type="checkbox" checked={checked} disabled={saving || disabled} onChange={event => setChecked(event.target.checked)} /><span>{whatsappAgreementLabel}</span></label>
        <button type="button" className="filter" disabled={!checked || saving || disabled} onClick={() => void recordAgreement(true)}>{saving ? "Saving…" : "Save agreement"}</button>
        <small>Saving agreement does not send or recreate earlier messages.</small>
      </>}
    </div>}
    {error && <p className="form-error" role="alert">{error}</p>}
    {whatsapp.messages.length ? <div className="whatsapp-message-list">{whatsapp.messages.map((message, index) => <details key={message.id} open={index === 0}>
      <summary><b>{message.kind === "INTRODUCTION" ? "SO introduction" : "SO changed"}</b><span>{message.status_label}</span></summary>
      <small>{formatDateTime(message.created_at)} · {message.recipient || "Invalid customer number"}</small>
      {message.reason && <p className="subtext">{message.reason}</p>}
      <p className="whatsapp-message-body">{message.body}</p>
    </details>)}</div> : <p className="subtext">No WhatsApp messages recorded. Introductions are prepared when a CE qualifies a lead with an assigned SO.</p>}
  </section>;
}
