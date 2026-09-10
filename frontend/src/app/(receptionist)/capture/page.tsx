"use client";

import { ActivityFields } from "@/components/activity-fields";

import { useEffect, useState, FormEvent } from "react";
import { createLead, getSystemConfig, getOfficers, toOfficer, type Officer, type SystemConfig } from "@/lib/crm";

export default function CaptureLeadPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [officers, setOfficers] = useState<Officer[]>([]);

  const [formData, setFormData] = useState({
    activity: "", sub_activity: "",
    name: "",
    phone: "",
    email: "",
    profession: "",
    rto: "",
    model_interest: "",
    assigned_ps_id: "",
  });

  useEffect(() => {
    getSystemConfig().then(setConfig).catch(() => setError("Unable to load enquiry options. Refresh the page to retry."));
    getOfficers().then(apiOfficers => setOfficers(apiOfficers.map(o => toOfficer(o)))).catch(console.error);
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleClear = () => {
    setFormData({
      activity: "", sub_activity: "",
      name: "", phone: "", email: "", profession: "", rto: "",
      model_interest: "", assigned_ps_id: ""
    });
    setError("");
    setSuccess(false);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setSuccess(false);

    try {
      if (!formData.model_interest) throw new Error("Select a vehicle model from Admin Lists.");
      const payload = {
        name: formData.name,
        phone: formData.phone,
        email: formData.email || undefined,
        profession: formData.profession,
        rto: formData.rto,
        source: "WALKIN",
        activity: formData.activity, sub_activity: formData.sub_activity,
        status: "QUALIFIED",
        model_interest: formData.model_interest,
        ps_officer_id: formData.assigned_ps_id ? parseInt(formData.assigned_ps_id) : undefined,
      };
      
      await createLead(payload);
      setSuccess(true);
      setTimeout(() => {
        handleClear();
      }, 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to capture lead.");
    } finally {
      setLoading(false);
    }
  };

  const modelOptions = config?.lists?.models || [];
  const rtoOptions = config?.rto_options || [];

  return (
    <div className="page capture-page">
      <div className="page-heading compact capture-heading">
        <div>
          <p className="eyebrow">FRONT DESK INTAKE</p>
          <h1>Capture <span>lead</span></h1>
          <p className="subtext">Register a new customer enquiry and assign it to a sales executive.</p>
        </div>
      </div>

      <form className="panel capture-form" onSubmit={submit}>
        {error && <div className="form-error capture-alert">{error}</div>}
        {success && <div className="form-success capture-alert">Lead successfully captured.</div>}

        <div className="capture-form-grid">
            <label>
              Customer Full Name *
              <input type="text" name="name" value={formData.name} onChange={handleChange} required placeholder="Enter customer name" />
            </label>
            <label>
              Mobile Number *
              <input type="tel" name="phone" value={formData.phone} onChange={handleChange} onInput={(e) => { e.currentTarget.value = e.currentTarget.value.replace(/\D/g, '').slice(0, 10); handleChange(e as any); }} required pattern="\d{10}" minLength={10} maxLength={10} placeholder="10-digit mobile number" />
            </label>
        </div>

        <div className="capture-form-grid">
            <label>
              Email Address (optional)
              <input type="email" name="email" value={formData.email} onChange={handleChange} placeholder="customer@example.com" />
            </label>
            <label>
              Profession
              <input type="text" name="profession" value={formData.profession} onChange={handleChange} placeholder="Enter profession (optional)" />
            </label>
        </div>


        <div className="capture-form-grid">
            <label>
              RTO (optional)
              <select name="rto" value={formData.rto} onChange={handleChange} disabled={!rtoOptions.length}>
                <option value="">{rtoOptions.length ? "Select Kerala RTO" : "RTO list unavailable"}</option>
                {rtoOptions.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
        </div>

        <fieldset className="capture-fieldset">
            <legend>Source *</legend>
            <div className="capture-choice-row">
              <label className="selected">
                <input type="radio" name="sourceType" checked readOnly />
                Walk-in
              </label>
            </div>
        </fieldset>

        <div className="capture-form-grid">
            <ActivityFields activity={formData.activity} subActivity={formData.sub_activity} onChange={fields => setFormData(current => ({ ...current, ...fields }))} />
            <label>
              Model Interested *
              <select name="model_interest" value={formData.model_interest} onChange={handleChange} required disabled={!modelOptions.length}>
                <option value="">{modelOptions.length ? "Select model" : "Add models in Lists first"}</option>
                {modelOptions.map(m => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </label>
            <label>
              Assign to Sales Executive (PS) *
              <select name="assigned_ps_id" value={formData.assigned_ps_id} onChange={handleChange} required>
                <option value="">Select Executive</option>
                {officers.map(o => (
                  <option key={o.id} value={o.id}>{o.name} ({o.location})</option>
                ))}
              </select>
            </label>
        </div>

        <footer className="capture-form-actions">
            <button className="button secondary" type="button" onClick={handleClear} disabled={loading}>
              Clear Form
            </button>
            <button className="button primary" type="submit" disabled={loading}>
              {loading ? "Submitting..." : "Submit Lead"}
            </button>
        </footer>
      </form>
    </div>
  );
}
