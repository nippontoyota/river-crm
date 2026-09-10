"use client";

import { ActivityFields } from "@/components/activity-fields";

import { useEffect, useState, type FormEvent } from "react";
import { DateInput } from "@/components/date-input";
import { createSoLead, getSystemConfig, type CurrentUser, type SystemConfig } from "@/lib/crm";
import { formatDate, parseDate } from "@/lib/dates";

export function SOLeadForm({ user, onClose, onCreated }: { user: CurrentUser; onClose: () => void; onCreated: (name: string) => void }) {
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ name: "", phone: "", email: "", profession: "", city: "", rto: "", source: "", source_label: "", activity: "", sub_activity: "", model_interest: "", variant: "", buying_timeline: "", enquiry_date: formatDate(new Date()) });
  const change = (field: keyof typeof form, value: string) => setForm(current => ({ ...current, [field]: value }));
  const models = config?.lists.models || [];
  const colors = config?.lists.colorVariants || [];
  const sources = config?.so_lead_sources || [];
  const rtos = config?.rto_options || [];

  useEffect(() => {
    void getSystemConfig().then(setConfig).catch(() => setError("Unable to load form options. Close the form and try again."));
  }, []);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (saving) return;
    const enquiryDate = parseDate(form.enquiry_date);
    if (!enquiryDate) { setError("Enter the enquiry date as DD/MM/YYYY."); return; }
    if (enquiryDate > (parseDate(formatDate(new Date())) || "")) { setError("Enquiry date cannot be in the future."); return; }
    setSaving(true); setError("");
    try {
      const { variant, buying_timeline, ...lead } = form;
      const created = await createSoLead({ ...lead, enquiry_date: enquiryDate, qualification_input: { variant, buying_timeline, finance_type: "", trade_in: null, test_drive: "", notes: "" } });
      onCreated(created.name);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to add your lead.");
    } finally { setSaving(false); }
  };

  return <div className="modal-layer" role="presentation">
    <section className="modal sales-detail-modal so-lead-modal" role="dialog" aria-modal="true" aria-labelledby="so-add-lead-title">
      <header className="sales-detail-header"><div><p className="eyebrow">SO LEAD INTAKE</p><h2 id="so-add-lead-title">Add my lead</h2><p className="subtext">Capture a customer enquiry from your own contacts or outreach.</p></div><button className="modal-close" onClick={onClose} disabled={saving} aria-label="Close">×</button></header>
      <form onSubmit={submit}>
        <div className="sales-detail-scroll">
          <section className="sales-form-card">
            <div className="sales-form-grid">
              <label>Full name *<input name="name" required maxLength={160} value={form.name} onChange={event => change("name", event.target.value)} placeholder="Customer name" /></label>
              <label>Phone number *<input name="phone" required type="tel" inputMode="numeric" pattern="[0-9]{10}" maxLength={10} value={form.phone} onChange={event => change("phone", event.target.value.replace(/\D/g, ""))} placeholder="10-digit mobile number" /></label>
              <label>Email<input name="email" type="email" value={form.email} onChange={event => change("email", event.target.value)} placeholder="name@example.com" /></label>
              <label>Profession<input name="profession" maxLength={100} value={form.profession} onChange={event => change("profession", event.target.value)} placeholder="Customer profession (optional)" /></label>
              <label>City<input name="city" maxLength={100} value={form.city} onChange={event => change("city", event.target.value)} placeholder="Customer city" /></label>
              <label>RTO (optional)<select name="rto" value={form.rto} onChange={event => change("rto", event.target.value)} disabled={!rtos.length}><option value="">Select Kerala RTO</option>{rtos.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
              <label>Lead source *<select name="source" required value={form.source} onChange={event => change("source", event.target.value)} disabled={!sources.length}><option value="">Select how you found this customer</option>{sources.map(source => <option key={source} value={source}>{source}</option>)}</select></label>
              <ActivityFields activity={form.activity} subActivity={form.sub_activity} onChange={fields => setForm(current => ({ ...current, ...fields }))} />
              <label>Enquiry date *<DateInput required value={form.enquiry_date} max={formatDate(new Date())} onChange={value => change("enquiry_date", value)} ariaLabel="Enquiry date, DD/MM/YYYY" /></label>
              <label>Vehicle interest *<select name="model_interest" required value={form.model_interest} onChange={event => change("model_interest", event.target.value)} disabled={!models.length}><option value="">{models.length ? "Select model" : "Add models in Lists first"}</option>{models.map(model => <option key={model} value={model}>{model}</option>)}</select></label>
              <label>Color interested *<select name="variant" required value={form.variant} onChange={event => change("variant", event.target.value)} disabled={!colors.length}><option value="">{colors.length ? "Select color" : "Add color variants in Lists first"}</option>{colors.map(color => <option key={color} value={color}>{color}</option>)}</select></label>
              <label>Purchase timeline<select name="buying_timeline" value={form.buying_timeline} onChange={event => change("buying_timeline", event.target.value)}><option value="">Select timeline (optional)</option><option>Immediate</option><option>1–2 Months</option><option>2–3 Months</option><option>Greater than 3 months</option></select></label>
              <label>Branch<input value={user.location || "Branch not set"} readOnly /></label>
            </div>
            <label className="sales-full-label">{form.source === "Other" ? "Source detail *" : "Source detail (optional)"}<input name="source_label" maxLength={100} required={form.source === "Other"} value={form.source_label} onChange={event => change("source_label", event.target.value)} placeholder={form.source === "Referral" ? "Referrer name or referral details" : "How did you meet or hear from this customer?"} /></label>
          </section>
          <p className="subtext">Assigned to you: {[user.first_name, user.last_name].filter(Boolean).join(" ") || user.email}. This lead will appear in your Fresh leads.</p>
          {!user.location?.trim() && <p className="form-error" role="alert">Ask your admin to set your branch before adding a lead.</p>}
          {error && <p className="form-error" role="alert">{error}</p>}
        </div>
        <footer className="sales-detail-footer"><button type="button" className="filter" onClick={onClose} disabled={saving}>Cancel</button><button className="button primary" disabled={saving || !sources.length || !models.length || !colors.length || !user.location?.trim()}>{saving ? "Adding…" : "Add my lead"}</button></footer>
      </form>
    </section>
  </div>;
}
