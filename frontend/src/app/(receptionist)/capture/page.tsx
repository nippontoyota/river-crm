"use client";

import { useEffect, useState, FormEvent } from "react";
import { createLead, getSystemConfig, getOfficers, toOfficer, sourceName, type Officer, type SystemConfig } from "@/lib/crm";

export default function CaptureLeadPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [officers, setOfficers] = useState<Officer[]>([]);

  const [sourceType, setSourceType] = useState<"Walk-in" | "Digital">("Walk-in");
  const [digitalSource, setDigitalSource] = useState("WEBSITE");

  const [formData, setFormData] = useState({
    name: "",
    phone: "",
    email: "",
    profession: "",
    model_interest: "",
    variant: "",
    buying_timeline: "",
    assigned_ps_id: "",
  });

  useEffect(() => {
    getSystemConfig().then(setConfig).catch(console.error);
    getOfficers().then(apiOfficers => setOfficers(apiOfficers.map(o => toOfficer(o)))).catch(console.error);
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleClear = () => {
    setFormData({
      name: "", phone: "", email: "", profession: "",
      model_interest: "", variant: "", buying_timeline: "", assigned_ps_id: ""
    });
    setSourceType("Walk-in");
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
      if (!formData.variant) throw new Error("Select a color variant from Admin Lists.");
      const payload = {
        name: formData.name,
        phone: formData.phone,
        email: formData.email || undefined,
        profession: formData.profession,
        source: sourceType === "Walk-in" ? "WALKIN" : digitalSource,
        model_interest: formData.model_interest,
        ps_officer_id: formData.assigned_ps_id ? parseInt(formData.assigned_ps_id) : undefined,
        qualification_input: {
          variant: formData.variant,
          buying_timeline: formData.buying_timeline,
          finance_type: "",
          test_drive: "",
          notes: ""
        }
      };
      
      const finalPayload = {
        ...payload,
        status: sourceType === "Walk-in" ? "QUALIFIED" : "FRESH"
      };

      await createLead(finalPayload as any);
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
  const colorVariantOptions = config?.lists?.colorVariants || [];

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


        <fieldset className="capture-fieldset">
            <legend>Source *</legend>
            <div className="capture-choice-row">
              <label className={sourceType === "Walk-in" ? "selected" : ""}>
                <input type="radio" name="sourceType" checked={sourceType === "Walk-in"} onChange={() => setSourceType("Walk-in")} />
                Walk-in
              </label>
              <label className={sourceType === "Digital" ? "selected" : ""}>
                <input type="radio" name="sourceType" checked={sourceType === "Digital"} onChange={() => setSourceType("Digital")} />
                Digital
              </label>
            </div>
            {sourceType === "Digital" && (
              <label className="capture-digital-source">
                Digital source
                <select value={digitalSource} onChange={e => setDigitalSource(e.target.value)} required>
                  {(config?.lists?.sources?.length ? config.lists.sources.filter(s => s !== "WALKIN") : ["META", "WEBSITE", "CARWALE", "CAMPAIGN", "OTHER"]).map(s => (
                    <option key={s} value={s}>{sourceName(s)}</option>
                  ))}
                </select>
              </label>
            )}
        </fieldset>

        <div className="capture-form-grid">
            <label>
              River Model Interested *
              <select name="model_interest" value={formData.model_interest} onChange={handleChange} required disabled={!modelOptions.length}>
                <option value="">{modelOptions.length ? "Select model" : "Add models in Lists first"}</option>
                {modelOptions.map(m => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </label>
            <label>
              Color variant *
              <select name="variant" value={formData.variant} onChange={handleChange} required disabled={!colorVariantOptions.length}>
                <option value="">{colorVariantOptions.length ? "Select color variant" : "Add color variants in Lists first"}</option>
                {colorVariantOptions.map(v => (
                  <option key={v} value={v}>{v}</option>
                ))}
              </select>
            </label>
        </div>

        <div className="capture-form-grid">
            <label>
              Purchase Timeline *
              <select name="buying_timeline" value={formData.buying_timeline} onChange={handleChange} required>
                <option value="">Select timeline</option>
                <option value="Immediate">Immediate (0-15 days)</option>
                <option value="Short Term">Short Term (1-2 months)</option>
                <option value="Long Term">Long Term (2+ months)</option>
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
