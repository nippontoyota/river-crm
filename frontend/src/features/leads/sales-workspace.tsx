"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createLead, getCurrentUser, getLeadDetail, getMyDashboard, getOfficers, toOfficer, updateMyLead, type CurrentUser, type LeadDetail, type LeadInput, type LeadQualification, type Officer, type SalesDashboard, type SalesLead, getSystemConfig } from "@/lib/crm";
import { DateInput } from "@/components/date-input";
import { addDays, formatDate, formatDateTime, parseDate, todayInIST, toApiDate } from "@/lib/dates";

type Section = "all" | "fresh" | "followups" | "pending" | "qualified" | "walkin" | "won" | "lost" | "won_lost" | "active";
type WonLostFilter = "all" | "won" | "lost";
type PsOutcome = { label: string; tone: "qualified" | "lost"; status: string };
type Draft = {
  status: string; category: string; sales_outcome: string; call_outcome: string; call_status: string; remarks: string; follow_up_at: string;
  model_interest: string; city: string; profession: string; custom_location: string; ps_officer_id: string; lost_reason: string; pending_reason: string; trade_in_note: string;
  qualification: LeadQualification;
};
type LeadFields = { name: string; phone: string; email: string; source: string; source_label: string; campaign: string; model_interest: string; city: string; branch: string; enquiry_date: string | null };

const soConnectedOutcomes: PsOutcome[] = [
  { label: "Need Test Drive", tone: "qualified", status: "PENDING" },
  { label: "Showroom Visit", tone: "qualified", status: "PENDING" },
  { label: "Exchange Issue", tone: "qualified", status: "PENDING" },
  { label: "Booking Done", tone: "qualified", status: "WALKIN" },
  { label: "Retail Done", tone: "qualified", status: "WON" },
  { label: "Call Me Back", tone: "qualified", status: "CALLBACK" },
  { label: "Need time", tone: "qualified", status: "PENDING" },
  { label: "Need SO Call", tone: "qualified", status: "PENDING" },
  { label: "Need More Details", tone: "qualified", status: "PENDING" },
  { label: "Discount Issue", tone: "qualified", status: "PENDING" },
  { label: "Not Interested", tone: "lost", status: "LOST" },
  { label: "Already Booked", tone: "lost", status: "LOST" },
  { label: "Lost to Competition", tone: "lost", status: "LOST" },
  { label: "Finance Rejected", tone: "lost", status: "LOST" },
  { label: "Dropped", tone: "lost", status: "LOST" },
  { label: "Lost to co-dealer", tone: "lost", status: "LOST" }
];
const soNotConnectedOutcomes: PsOutcome[] = [
  { label: "RNR", tone: "qualified", status: "RNR" },
  { label: "Switch Off", tone: "qualified", status: "SWITCHED_OFF" },
  { label: "Call Forwarding", tone: "qualified", status: "PENDING" },
  { label: "Line Busy", tone: "qualified", status: "PENDING" },
  { label: "Invalid Number", tone: "qualified", status: "PENDING" },
  { label: "No Response", tone: "lost", status: "LOST" }
];
const soOutcomes = [...soConnectedOutcomes, ...soNotConnectedOutcomes];

const sections: { key: Section; label: string; count: keyof SalesDashboard["summary"]; icon: string }[] = [
  { key: "all", label: "All leads", count: "total", icon: "☰" },
  { key: "fresh", label: "Fresh leads", count: "fresh", icon: "✦" },
  { key: "followups", label: "Today's follow-ups", count: "followups", icon: "◷" },
  { key: "pending", label: "Pending leads", count: "pending", icon: "!" },
  { key: "qualified", label: "Qualified leads", count: "qualified", icon: "◎" },
  { key: "won_lost", label: "Won / lost", count: "won_lost", icon: "◇" },
];
const psSections: { key: Section; label: string; count: keyof SalesDashboard["summary"]; icon: string }[] = [
  { key: "all", label: "All leads", count: "total", icon: "☰" },
  { key: "fresh", label: "Fresh leads", count: "fresh", icon: "✦" },
  { key: "walkin", label: "Booked", count: "walkin", icon: "◷" },
  { key: "won", label: "Retailed", count: "won", icon: "✓" },
  { key: "lost", label: "Lost", count: "lost", icon: "×" },
];
const psFollowUpSections: { key: Section; label: string; count: keyof SalesDashboard["summary"]; icon: string }[] = [
  { key: "followups", label: "Today's follow-ups", count: "followups", icon: "◷" },
  { key: "walkin", label: "Booked", count: "walkin", icon: "◷" },
  { key: "won", label: "Retailed", count: "won", icon: "✓" },
  { key: "lost", label: "Lost", count: "lost", icon: "×" },
];
const statusLabels: Record<string, string> = { FRESH: "Fresh", RNR: "RNR", SWITCHED_OFF: "Switch off", CALLBACK: "Callback", PENDING: "Pending", QUALIFIED: "Qualified", UNQUALIFIED: "Unqualified", WALKIN: "Walk-in", WON: "Won", LOST: "Lost" };
const outcomeLabels: Record<string, string> = { QUALIFIED: "Qualified", LOST: "Lost", PENDING: "Pending" };
const psOutcomeLabels: Record<string, string> = { BOOKED: "Booked Follow-up", RETAILED: "Retailed", LOST: "Lost" };
const allOutcomeLabels: Record<string, string> = { ...outcomeLabels, ...psOutcomeLabels };
soOutcomes.forEach(o => { allOutcomeLabels[o.label] = o.label; });

const statusOptions: Record<string, string[]> = { QUALIFIED: ["QUALIFIED"], LOST: ["LOST"], PENDING: ["PENDING"], BOOKED: ["WALKIN"], RETAILED: ["WON"] };
soOutcomes.forEach(o => { statusOptions[o.label] = [o.status]; });
const autoNextDayFollowUpOutcomes = new Set(["RNR", "Switch Off", "Call Forwarding", "Line Busy"]);
const lostPsOutcomes = new Set(soOutcomes.filter(outcome => outcome.status === "LOST").map(outcome => outcome.label));
const sourceOptions = [{ value: "META", label: "Meta Ads" }, { value: "WEBSITE", label: "Website" }, { value: "CARWALE", label: "CarWale" }, { value: "WALKIN", label: "Walk-in" }, { value: "CAMPAIGN", label: "Campaign" }, { value: "OTHER", label: "Other" }, { value: "UNKNOWN", label: "Unknown" }];
const professionOptions = ["Salaried", "Business", "Self Employed", "Doctor", "Govt Employee"];
const buyingPlanOptions = ["Immediate", "1–2 Months", "2–3 Months", "Greater than 3 months"];
const financeOptions = ["Inhouse", "Outright"];
const testDriveOptions = ["No", "Home Test Drive", "Showroom visit"];
const tradeInOptions = ["Yes", "Additional", "Buying for first time"];
const lostReasons = ["Invalid Number", "Wrong Number", "Just enquired", "Service", "Insurance", "Internal", "Used car", "No Response", "Mock Call", "Plan Dropped", "DSA Enq", "BH Registration", "Existing Enq", "Duplicate Lead", "Not interested", "Did not enquire", "Lost to co-dealer", "Lost to competition", "Low Budget", "Out of Territory", "Not Eligible", "Job Enquiry"];
const pendingReasons = ["RNR", "DND", "Not Reachable", "Switched Off", "Busy", "Disconnecting the call", "Temporary out of Service", "Call me back", "Incoming call facility not available", "Out of Network", "Plan Postponed"];
const emptyQualification = (): LeadQualification => ({ variant: "", buying_timeline: "", finance_type: "", trade_in: null, test_drive: "", notes: "" });
const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const emptyLead = (): LeadInput => ({ name: "", phone: "", email: "", source: "OTHER", source_label: "", campaign: "", model_interest: "", city: "", branch: "", enquiry_date: formatDate(new Date()) });

const optionsWithCurrent = (options: string[], current = "") => {
  const value = current.trim();
  return value && !options.includes(value) ? [value, ...options] : options;
};

function formatFollowUp(value: string | null) {
  if (!value) return "Not scheduled";
  return formatDateTime(value) || "Invalid date";
}

const minimumFollowUpDay = todayInIST;
const tomorrowFollowUpDay = () => addDays(todayInIST(), 1);
const maximumFollowUpDay = () => addDays(todayInIST(), 3);

const followUpIso = (value: string) => {
  const date = toApiDate(value);
  return date && /^\d{4}-\d{2}-\d{2}$/.test(date) ? new Date(`${date}T23:59:00+05:30`).toISOString() : null;
};

const creNoteText = (notes = "") => notes
  .split(/\r?\n/)
  .map(line => line.trim())
  .filter(line => line && line !== "Qualified lead" && !/^(Profession|Preferred branch|Trade in):/i.test(line))
  .join("\n");

const pendingOutcomeFor = (reason: string) => {
  if (reason === "Call me back") return { call_outcome: "Call Me Back", status: "PENDING" };
  if (reason === "RNR") return { call_outcome: "RNR", status: "PENDING" };
  if (reason === "Switched Off") return { call_outcome: "Switch Off", status: "PENDING" };
  return { call_outcome: "PENDING", status: "PENDING" };
};

function progressState(callCount: number, index: number) {
  const currentStep = Math.min(callCount, 4);
  return index < currentStep ? "done" : index === currentStep ? "current" : "locked";
}

function draftFor(lead: LeadDetail): Draft {
  const { updated_at: _updatedAt, ...qualification } = lead.qualification || emptyQualification();
  qualification.notes = creNoteText(qualification.notes);
  const latestOutcome = lead.callHistory[0]?.outcome;
  const call_outcome = ["PENDING", "QUALIFIED", "LOST"].includes(latestOutcome || "") ? latestOutcome : lead.statusCode === "PENDING" ? "PENDING" : lead.statusCode === "QUALIFIED" ? "QUALIFIED" : lead.statusCode === "LOST" ? "LOST" : "";
  return { status: lead.statusCode, category: lead.category || "WARM", sales_outcome: lead.salesOutcome || "PENDING", call_outcome, call_status: "", remarks: "", follow_up_at: "", model_interest: lead.model === "—" ? "" : lead.model, city: lead.city, profession: "", custom_location: "", ps_officer_id: lead.assignedPsId ? String(lead.assignedPsId) : "", lost_reason: "", pending_reason: "", trade_in_note: "", qualification };
}

function leadFieldsFor(lead: LeadDetail): LeadFields {
  return { name: lead.name, phone: lead.phone, email: lead.email, source: lead.sourceCode, source_label: lead.sourceLabel, campaign: lead.campaign, model_interest: lead.model === "—" ? "" : lead.model, city: lead.city, branch: lead.branch, enquiry_date: formatDate(lead.enquiryDate) };
}

function ChoiceRow({ options, value, onChange }: { options: string[]; value: string; onChange: (value: string) => void }) {
  return <div className="sales-choice-row">{options.map(option => <button type="button" className={value === option ? "chosen" : ""} onClick={() => onChange(option)} key={option}>{option}</button>)}</div>;
}

function LeadEditPanel({ fields, modelOptions, onChange, onClose, onSave, saving }: { fields: LeadFields; modelOptions: string[]; onChange: (fields: LeadFields) => void; onClose: () => void; onSave: () => void; saving: boolean }) {
  const update = (field: keyof LeadFields, value: string | null) => onChange({ ...fields, [field]: value });
  return <div className="modal-layer sales-edit-layer" role="presentation"><section className="modal sales-detail-modal sales-edit-modal" role="dialog" aria-modal="true" aria-labelledby="sales-edit-title"><header className="sales-detail-header"><div><p className="eyebrow">CUSTOMER INFORMATION</p><h2 id="sales-edit-title">Edit lead details</h2><p className="subtext">Update the customer record saved in the CRM.</p></div><button className="modal-close" onClick={onClose} aria-label="Close">×</button></header><div className="sales-detail-scroll"><section className="sales-form-card"><div className="sales-form-grid"><label>Full name<input required value={fields.name} onChange={event => update("name", event.target.value)} /></label><label>Phone number<input required type="tel" inputMode="numeric" pattern="[0-9]{10}" maxLength={10} value={fields.phone} onChange={event => update("phone", event.target.value.replace(/\D/g, "").slice(0, 10))} /></label><label>Email<input type="email" value={fields.email} onChange={event => update("email", event.target.value)} /></label><label>Lead source<select value={fields.source} onChange={event => update("source", event.target.value)}>{sourceOptions.map(option => <option value={option.value} key={option.value}>{option.label}</option>)}</select></label><label>Source detail<input value={fields.source_label} onChange={event => update("source_label", event.target.value)} /></label><label>Campaign<input value={fields.campaign} onChange={event => update("campaign", event.target.value)} /></label><label>Vehicle / model<select value={fields.model_interest} onChange={event => update("model_interest", event.target.value)} disabled={!modelOptions.length && !fields.model_interest}><option value="">{modelOptions.length ? "Select model" : "Add models in Lists first"}</option>{optionsWithCurrent(modelOptions, fields.model_interest).map(model => <option value={model} key={model}>{model}</option>)}</select></label><label>City<input value={fields.city} onChange={event => update("city", event.target.value)} /></label><label>Branch<input value={fields.branch} onChange={event => update("branch", event.target.value)} /></label><label>Enquiry date<DateInput value={fields.enquiry_date || ""} max={formatDate(new Date())} onChange={value => update("enquiry_date", value || null)} ariaLabel="Enquiry date, DD/MM/YYYY" /></label></div></section></div><footer className="sales-detail-footer"><button className="filter" onClick={onClose}>Cancel</button><button className="button primary" disabled={saving || !fields.name.trim() || fields.phone.length !== 10} onClick={onSave}>{saving ? "Saving…" : "Save details"}</button></footer></section></div>;
}

export function SalesWorkspace({ followUpsOnly = false }: { followUpsOnly?: boolean }) {
  const [section, setSection] = useState<Section>(followUpsOnly ? "followups" : "fresh");
  const [wonLostFilter, setWonLostFilter] = useState<WonLostFilter>("all");
  const [range, setRange] = useState("all");
  const [category, setCategory] = useState("");
  const [source, setSource] = useState("");
  const [query, setQuery] = useState("");
  const [dashboard, setDashboard] = useState<SalesDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState<LeadDetail | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const [editingLead, setEditingLead] = useState(false);
  const [leadFields, setLeadFields] = useState<LeadFields | null>(null);
  const [addingLead, setAddingLead] = useState(false);
  const [creatingLead, setCreatingLead] = useState(false);
  const [newLead, setNewLead] = useState<LeadInput>(emptyLead());
  const [addLeadError, setAddLeadError] = useState("");
  const [submittedLead, setSubmittedLead] = useState<string | null>(null);
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [psOptions, setPsOptions] = useState<Officer[]>([]);
  const [psLoading, setPsLoading] = useState(false);
  const [branches, setBranches] = useState<string[]>([]);
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [colorVariantOptions, setColorVariantOptions] = useState<string[]>([]);
  const [addLeadPsOptions, setAddLeadPsOptions] = useState<Officer[]>([]);
  const dashboardRequest = useRef(0);
  const isPs = user?.role === "SO";
  const activeOutcomeLabels = isPs ? psOutcomeLabels : outcomeLabels;
  const branchOptions = branches;
  const selectedLocation = draft ? draft.city.trim() : "";

  useEffect(() => {
    void getCurrentUser().then(result => {
      setUser(result.user);
      if (result.user.role === "SO" && !followUpsOnly) setSection("all");
    }).catch(() => setUser(null)).finally(() => setAuthChecked(true));
    void getSystemConfig()
      .then(config => {
        setBranches(config.lists?.branches || []);
        setModelOptions(config.lists?.models || []);
        setColorVariantOptions(config.lists?.colorVariants || []);
      })
      .catch(error => {
        console.warn("Failed to fetch system config", error);
        setBranches([]);
        setModelOptions([]);
        setColorVariantOptions([]);
      });
  }, [followUpsOnly]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (!newLead.branch) {
        if (!cancelled) setAddLeadPsOptions([]);
        return;
      }
      const records = await getOfficers(newLead.branch);
      if (!cancelled) setAddLeadPsOptions(records.map(r => toOfficer(r)));
    })();
    return () => { cancelled = true; };
  }, [newLead.branch]);

  const loadDashboard = useCallback(async () => {
    if (!user) return;
    const request = ++dashboardRequest.current;
    setLoading(true); setError("");
    try { const result = await getMyDashboard({ section, range, ...(category ? { category } : {}), ...(source ? { source } : {}), ...(query ? { q: query } : {}) }); if (request === dashboardRequest.current) setDashboard(result); }
    catch (requestError) { if (request === dashboardRequest.current) setError(requestError instanceof Error ? requestError.message : "Unable to load your leads."); }
    finally { if (request === dashboardRequest.current) setLoading(false); }
  }, [category, query, range, section, source, user]);

  useEffect(() => { if (!authChecked || !user) return; const timer = window.setTimeout(() => void loadDashboard(), query ? 250 : 0); return () => window.clearTimeout(timer); }, [authChecked, loadDashboard, query, user]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (isPs || draft?.call_outcome !== "QUALIFIED" || !selectedLocation) {
        if (!cancelled) setPsOptions([]);
        return;
      }
      setPsOptions([]);
      setPsLoading(true);
      try {
        const records = await getOfficers(selectedLocation);
        if (!cancelled) setPsOptions(records.map(record => toOfficer(record)));
      } catch {
        if (!cancelled) setPsOptions([]);
      } finally {
        if (!cancelled) setPsLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [draft?.call_outcome, isPs, selectedLocation]);

  const openLead = async (lead: { id: number }) => {
    setDetailLoading(true); setError("");
    try {
      const fullLead = await getLeadDetail(lead.id);
      const nextDraft = draftFor(fullLead);
      if (isPs) nextDraft.call_outcome = fullLead.statusCode === "WALKIN" ? "BOOKED" : fullLead.statusCode === "WON" ? "RETAILED" : fullLead.statusCode === "LOST" ? "LOST" : "";
      else if (fullLead.statusCode === "QUALIFIED") nextDraft.call_outcome = "";
      setDetail(fullLead); setDraft(nextDraft); setLeadFields(leadFieldsFor(fullLead)); setEditingLead(false);
    }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Unable to open this lead."); }
    finally { setDetailLoading(false); }
  };

  const save = async () => {
    if (!detail || !draft || saving) return;
    
    let followUpAt: string | null = null;
    let remarks = "";
    
    if (isPs) {
      if (!draft.call_status) return setNotice("Choose Connected or Not Connected.");
      if (!draft.call_outcome) return setNotice("Choose a call outcome.");
      if (!draft.remarks.trim()) return setNotice("Remarks are required.");
      const nextStatus = statusOptions[draft.call_outcome]?.[0] || "";
      if (autoNextDayFollowUpOutcomes.has(draft.call_outcome)) {
        followUpAt = followUpIso(draft.follow_up_at || tomorrowFollowUpDay());
        if (!followUpAt) return setNotice("Choose a valid follow-up date.");
      } else if (["PENDING", "WALKIN", "CALLBACK"].includes(nextStatus)) {
        if (!draft.follow_up_at) return setNotice("Choose a follow-up date for this outcome.");
        followUpAt = followUpIso(draft.follow_up_at);
        if (!followUpAt) return setNotice("Choose a valid follow-up date.");
        const minDay = minimumFollowUpDay();
        const maxDay = maximumFollowUpDay();
        const chosenDay = toApiDate(draft.follow_up_at);
        if (chosenDay && chosenDay < minDay) return setNotice("Choose a future follow-up date.");
        if (maxDay && chosenDay && chosenDay > maxDay) return setNotice("Choose a follow-up date within the next 3 days.");
        if (new Date(followUpAt).getTime() <= Date.now()) return setNotice("Choose a future follow-up date.");
      }
      remarks = draft.remarks;
    } else {
      if (!draft.call_outcome) return setNotice("Choose Qualified, Lost, or Pending.");
      if (draft.call_outcome === "QUALIFIED" && (!draft.model_interest || !selectedLocation || !draft.ps_officer_id || !draft.qualification.variant || !draft.qualification.buying_timeline || !draft.qualification.finance_type || !draft.qualification.notes.trim())) return setNotice("Complete model, branch, PS/SO, buying plan, finance, color variant, and qualification notes.");
      if (draft.call_outcome === "LOST" && (!draft.lost_reason || !draft.remarks.trim())) return setNotice("Choose a lost reason and add remarks.");
      if (draft.call_outcome === "PENDING" && (!draft.pending_reason || !draft.remarks.trim() || !draft.follow_up_at)) return setNotice("Choose a pending reason, add remarks, and set follow-up date.");
      if (draft.call_outcome === "BOOKED" && (!draft.remarks.trim() || !draft.follow_up_at)) return setNotice("Add remarks and set the booked follow-up date.");
      followUpAt = ["PENDING", "BOOKED"].includes(draft.call_outcome) ? followUpIso(draft.follow_up_at) : null;
      if (["PENDING", "BOOKED"].includes(draft.call_outcome) && !followUpAt) return setNotice("Choose a valid follow-up date.");
      const chosenDay = toApiDate(draft.follow_up_at);
      if (["PENDING", "BOOKED"].includes(draft.call_outcome) && chosenDay && chosenDay > maximumFollowUpDay()) return setNotice("Choose a follow-up date within the next 3 days.");
      if (["PENDING", "BOOKED"].includes(draft.call_outcome) && followUpAt && new Date(followUpAt).getTime() <= Date.now()) return setNotice("Choose a future follow-up date.");
      remarks = draft.call_outcome === "LOST" ? `Lost reason: ${draft.lost_reason}\n${draft.remarks}` : draft.call_outcome === "PENDING" ? `Pending reason: ${draft.pending_reason}\n${draft.remarks}` : draft.qualification.notes;
    }

    setSaving(true); setError("");
    try {
      const notes = draft.qualification.notes.trim();
      const pendingOutcome = !isPs && draft.call_outcome === "PENDING" ? pendingOutcomeFor(draft.pending_reason) : null;
      await updateMyLead(detail.id, {
        call_outcome: pendingOutcome?.call_outcome || draft.call_outcome,
        status: pendingOutcome?.status || statusOptions[draft.call_outcome]?.[0] || detail.statusCode,
        category: draft.category,
        sales_outcome: draft.call_outcome === "Retail Done" ? "RETAILED" : draft.call_outcome === "Booking Done" ? "BOOKED" : lostPsOutcomes.has(draft.call_outcome) ? "LOST" : isPs ? "PENDING" : draft.call_outcome === "LOST" ? "LOST" : draft.call_outcome === "BOOKED" ? "BOOKED" : draft.call_outcome === "RETAILED" ? "RETAILED" : "PENDING",
        remarks,
        follow_up_at: followUpAt,
        model_interest: !isPs && draft.call_outcome === "QUALIFIED" ? draft.model_interest : undefined,
        city: !isPs && draft.call_outcome === "QUALIFIED" ? selectedLocation : undefined,
        branch: !isPs && draft.call_outcome === "QUALIFIED" ? selectedLocation : undefined,
        ps_officer_id: !isPs && draft.call_outcome === "QUALIFIED" ? Number(draft.ps_officer_id) : undefined,
        qualification: !isPs && draft.call_outcome === "QUALIFIED" ? { ...draft.qualification, trade_in: draft.trade_in_note === "Yes" ? true : draft.trade_in_note ? false : null, notes } : undefined,
      });
      setDetail(null);
      setDraft(null);
      setNotice("Lead updated and follow-up history saved."); await loadDashboard();
    } catch (requestError) { const message = requestError instanceof Error ? requestError.message : "Lead update could not be saved."; setError(message); setNotice(message); }
    finally { setSaving(false); }
  };

  const saveLeadFields = async () => {
    if (!detail || !leadFields || saving) return;
    const enquiryDate = leadFields.enquiry_date ? parseDate(leadFields.enquiry_date) : null;
    if (leadFields.enquiry_date && !enquiryDate) return setNotice("Enter the enquiry date as DD/MM/YYYY.");
    const today = parseDate(formatDate(new Date()));
    if (enquiryDate && today && enquiryDate > today) return setNotice("Enquiry date cannot be in the future.");
    setSaving(true); setError("");
    try {
      const updated = await updateMyLead(detail.id, { ...leadFields, enquiry_date: enquiryDate });
      setDetail(updated); setLeadFields(leadFieldsFor(updated)); setEditingLead(false); setNotice("Customer details updated."); await loadDashboard();
    } catch (requestError) { const message = requestError instanceof Error ? requestError.message : "Customer details could not be saved."; setError(message); setNotice(message); }
    finally { setSaving(false); }
  };

  const saveLead = async () => {
    if (creatingLead) return;
    if (!newLead.model_interest) { setAddLeadError("Select a vehicle model from Admin Lists."); return; }
    const enquiryDate = parseDate(newLead.enquiry_date || "");
    if (!enquiryDate) { setAddLeadError("Enter the enquiry date as DD/MM/YYYY."); return; }
    const today = parseDate(formatDate(new Date()));
    if (today && enquiryDate > today) { setAddLeadError("Enquiry date cannot be in the future."); return; }
    setCreatingLead(true); setAddLeadError("");
    try {
      const payload: LeadInput = { ...newLead, enquiry_date: enquiryDate };
      if (newLead.ps_officer_id) {
         payload.status = "QUALIFIED";
      }
      const created = await createLead(payload);
      setSubmittedLead(created.name);
      setAddingLead(false);
      setNewLead(emptyLead());
      void loadDashboard();
    } catch (requestError) {
      setAddLeadError(requestError instanceof Error ? requestError.message : "Failed to add lead.");
    } finally {
      setCreatingLead(false);
    }
  };

  const summary = dashboard?.summary;
  const selectCallOutcome = (call_outcome: string) => setDraft(current => current ? { ...current, call_outcome, status: statusOptions[call_outcome]?.[0] || "", follow_up_at: autoNextDayFollowUpOutcomes.has(call_outcome) ? formatDate(tomorrowFollowUpDay()) : "" } : current);
  const choose = <K extends keyof Draft>(field: K, value: Draft[K]) => setDraft(current => current ? { ...current, [field]: value } : current);
  const chooseQualification = (field: keyof LeadQualification, value: string | boolean | null) => setDraft(current => current ? { ...current, qualification: { ...current.qualification, [field]: value } } : current);
  const submitLabel = draft?.call_outcome === "QUALIFIED" ? "Qualify Lead" : draft?.call_outcome === "LOST" ? "Mark as Lost" : draft?.call_outcome === "PENDING" ? "Mark as Pending" : draft?.call_outcome === "BOOKED" ? "Book Follow-up" : draft?.call_outcome === "RETAILED" ? "Mark Retailed" : "Save follow-up";
  const visibleSections = isPs ? sections.filter(item => !["all", "fresh", "pending"].includes(item.key)) : sections;
  const psVisibleSections = followUpsOnly ? psFollowUpSections : psSections;
  const metrics = isPs
    ? [{label: followUpsOnly ? "TODAY'S FOLLOW-UPS" : "FRESH LEADS", value: followUpsOnly ? summary?.followups ?? 0 : summary?.fresh ?? 0, tone:"blue"}, {label:"BOOKED", value:summary?.walkin ?? 0, tone:"green"}, {label:"RETAILED", value:summary?.won ?? 0, tone:"green"}, {label:"LOST", value:summary?.lost ?? 0, tone:"red"}]
    : [{label:"Fresh leads", value:summary?.fresh ?? 0, tone:"blue"}, {label:"Today's follow-ups", value:summary?.followups ?? 0, tone:"yellow"}, {label:"Pending leads", value:summary?.pending ?? 0, tone:"orange"}, {label:"Qualified leads", value:summary?.qualified ?? 0, tone:"green"}, {label:"Won leads", value:summary?.won ?? 0, tone:"mint"}, {label:"Lost leads", value:summary?.lost ?? 0, tone:"red"}];
  const displayStatus = (lead: SalesLead) => !isPs && ["RNR", "SWITCHED_OFF", "CALLBACK"].includes(lead.statusCode) ? "Pending" : lead.status;
  const displayStatusClass = (lead: SalesLead) => !isPs && ["RNR", "SWITCHED_OFF", "CALLBACK"].includes(lead.statusCode) ? "pending" : lead.statusCode.toLowerCase();
  const psVisibleOutcomes = draft ? (draft.call_status === "Connected" ? soConnectedOutcomes : soNotConnectedOutcomes) : [];
  const saveTone = draft?.call_outcome && lostPsOutcomes.has(draft.call_outcome) ? "lost" : draft?.call_outcome ? "qualified" : "";

  return <section className="page sales-workspace">
    <div className="sales-hero"><div><p className="eyebrow">{isPs ? "PS/SO WORKSPACE" : "CRE WORKSPACE"}</p><h1>My queue</h1><p className="subtext">Today, {formatDate(new Date())}</p></div><div className="sales-hero-actions"><button className="filter" onClick={() => void loadDashboard()}>↻ Refresh</button><a className="button primary" href="/my-analytics">View analytics →</a>{!isPs && <button className="button primary" onClick={() => { setAddLeadError(""); setAddingLead(true); }}>＋ Add lead</button>}</div></div>
    <section className="sales-metrics">{metrics.map(metric => <article className={`sales-metric ${metric.tone}`} key={metric.label}><span>{metric.label}</span><strong>{metric.value}</strong><small>Assigned to you</small></article>)}</section>
    
    {isPs ? (
      <section className="panel sales-table-panel" style={{ background: "transparent", border: "none", boxShadow: "none", padding: 0 }}>
        <nav className="sales-tabs" aria-label="Lead status views">{psVisibleSections.map(item => <button key={item.key} className={section === item.key ? "active" : ""} onClick={() => setSection(item.key)}><i>{item.icon}</i><span>{item.label}</span><b>{summary?.[item.count] ?? 0}</b></button>)}</nav>
        <div className="sales-filters" style={{ marginBottom: "1rem" }}>
          <label className="sales-search" style={{ width: "100%", background: "#fff" }}>⌕<input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search by name or mobile..." /></label>
        </div>
        <div className="so-card-list" style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          {loading ? <div className="sales-empty">Loading…</div> : dashboard?.results.length ? dashboard.results.map(lead => (
            <div key={lead.id} onClick={() => void openLead(lead)} style={{ background: "#fff", padding: "1.25rem", borderRadius: "12px", border: "1px solid var(--border)", cursor: "pointer", display: "flex", flexDirection: "column", gap: "0.75rem", boxShadow: "0 1px 3px rgba(0,0,0,0.05)" }}>
               <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                 <div style={{ display: "flex", flexDirection: "column" }}>
                   <b style={{ fontSize: "1.1rem", marginBottom: "0.25rem" }}>{lead.name}</b>
                   <span style={{ color: "var(--text-light)", fontSize: "0.9rem" }}>{lead.phone} · {lead.sourceCode}</span>
                   <span style={{ color: "var(--text-light)", fontSize: "0.85rem" }}>{lead.source} · {lead.status}</span>
                 </div>
                 <span className={`sales-status ${displayStatusClass(lead)}`}>{displayStatus(lead)}</span>
               </div>
            </div>
          )) : <div className="sales-empty"><strong>No leads in this view.</strong><span>New assignments and follow-ups will appear here automatically.</span></div>}
        </div>
      </section>
    ) : (
      <>
        <nav className="sales-tabs" aria-label="Lead status views">{visibleSections.map(item => <button key={item.key} className={section === item.key ? "active" : ""} onClick={() => setSection(item.key)}><i>{item.icon}</i><span>{item.label}</span><b>{summary?.[item.count] ?? 0}</b></button>)}</nav>
        <section className="panel sales-table-panel"><header className="sales-table-heading"><div><p className="eyebrow">{sections.find(item => item.key === section)?.label.toUpperCase()}</p><h2>{loading ? "Loading your pipeline…" : `${dashboard?.results.length ?? 0} leads in this view`}</h2></div><div className="sales-filters"><select aria-label="Date range" value={range} onChange={event => setRange(event.target.value)}><option value="all">All time</option><option value="today">Today</option><option value="mtd">Month to date</option></select>{section !== "pending" && <select aria-label="Lead category" value={category} onChange={event => setCategory(event.target.value)}><option value="">All categories</option><option value="HOT">Hot</option><option value="WARM">Warm</option><option value="COLD">Cold</option></select>}<select aria-label="Lead source" value={source} onChange={event => setSource(event.target.value)}><option value="">All sources</option><option value="META">Meta Ads</option><option value="WEBSITE">Website</option><option value="CARWALE">CarWale</option><option value="CAMPAIGN">Campaign</option><option value="OTHER">Other</option></select><label className="sales-search">⌕<input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search name, phone, model" /></label></div></header>{!isPs && section === "won_lost" ? <div className="sales-subfilters"><span>Status</span><button className={wonLostFilter === "all" ? "selected" : ""} onClick={() => setWonLostFilter("all")}>◇ All <b>{summary?.won_lost ?? 0}</b></button><button className={wonLostFilter === "won" ? "selected" : ""} onClick={() => setWonLostFilter("won")}>✓ Won <b>{summary?.won ?? 0}</b></button><button className={wonLostFilter === "lost" ? "selected" : ""} onClick={() => setWonLostFilter("lost")}>× Lost <b>{summary?.lost ?? 0}</b></button></div> : !isPs && section === "pending" ? <div className="sales-subfilters"><span>Lead category</span><button className={!category ? "selected" : ""} onClick={() => setCategory("")}>All</button><button className={category === "HOT" ? "selected hot" : "hot"} onClick={() => setCategory("HOT")}>Hot</button><button className={category === "WARM" ? "selected warm" : "warm"} onClick={() => setCategory("WARM")}>Warm</button><button className={category === "COLD" ? "selected cold" : "cold"} onClick={() => setCategory("COLD")}>Cold</button></div> : null}<div className="sales-table-scroll"><table className="sales-table"><thead><tr><th>Action</th><th>Status</th><th>Customer name</th><th>Mobile no.</th><th>Source</th></tr></thead><tbody>{loading ? <tr><td colSpan={5} className="sales-empty">Loading…</td></tr> : (() => { const filtered = section === "won_lost" && wonLostFilter !== "all" ? (dashboard?.results ?? []).filter(l => wonLostFilter === "won" ? l.statusCode === "WON" : l.statusCode === "LOST") : dashboard?.results ?? []; return filtered.length ? filtered.map(lead => <tr key={lead.id} onClick={() => void openLead(lead)}><td><button className="sales-row-action" onClick={event => { event.stopPropagation(); void openLead(lead); }}>↗ Open</button></td><td><span className={`sales-status ${displayStatusClass(lead)}`}>{displayStatus(lead)}</span></td><td><b>{lead.name}</b><small>#{String(lead.id).padStart(6, "0")}</small></td><td>{lead.phone}</td><td>{lead.source}</td></tr>) : <tr><td colSpan={5} className="sales-empty"><strong>No leads in this view.</strong><span>New assignments and follow-ups will appear here automatically.</span></td></tr>; })()}</tbody></table></div></section>
      </>
    )}

    {editingLead && leadFields && <LeadEditPanel fields={leadFields} modelOptions={modelOptions} onChange={setLeadFields} onClose={() => setEditingLead(false)} onSave={() => void saveLeadFields()} saving={saving} />}
    {notice && <div className="toast" role="status">{notice}<button aria-label="Dismiss" onClick={() => setNotice("")}>×</button></div>}
    {detailLoading && <div className="modal-layer"><section className="modal sales-loading-modal"><span className="sales-spinner" /><p>Opening lead history…</p></section></div>}
    {detail && draft && <div className="modal-layer" role="presentation"><section className="modal sales-detail-modal" role="dialog" aria-modal="true" aria-labelledby="sales-detail-title">
      <header className="sales-detail-header"><div><p className="eyebrow">LEAD DETAIL · #{String(detail.id).padStart(6, "0")}</p><h2 id="sales-detail-title">Update {detail.name}</h2><p className="subtext">Customer information and call history.</p></div><button className="modal-close" onClick={() => setDetail(null)} aria-label="Close">×</button></header>
      <div className="sales-detail-scroll">
        {error && <p className="form-error" role="alert">{error}</p>}

        <section className="sales-info-card"><h3>Customer information <button type="button" className="row-action" onClick={() => { setLeadFields(leadFieldsFor(detail)); setEditingLead(true); }}>Edit fields</button></h3><div className="sales-info-grid"><span><small>Name</small><b>{detail.name}</b></span><span><small>Phone</small><b>{detail.phone}</b></span><span><small>Email</small><b>{detail.email || "—"}</b></span><span><small>Source</small><b>{detail.source}</b></span><span><small>Source detail</small><b>{detail.sourceLabel || "—"}</b></span><span><small>Model</small><b>{detail.model}</b></span><span><small>City</small><b>{detail.city || "—"}</b></span><span><small>Enquiry date</small><b>{detail.enquiredAt}</b></span><span><small>Campaign</small><b>{detail.campaign || "—"}</b></span><span><small>Branch</small><b>{detail.branch || "—"}</b></span></div><div className="sales-detail-meta"><span>Category <b className={`category-pill ${draft.category.toLowerCase()}`}>{draft.category}</b></span><span>Calls <b>{detail.callCount}</b></span></div></section>
        {detail.qualification && <section className="sales-info-card"><h3>CRE qualification</h3><div className="sales-info-grid"><span><small>Color variant</small><b>{detail.qualification.variant || "—"}</b></span><span><small>Buying plan</small><b>{detail.qualification.buying_timeline || "—"}</b></span><span><small>Finance</small><b>{detail.qualification.finance_type || "—"}</b></span><span><small>Test drive</small><b>{detail.qualification.test_drive || "—"}</b></span><span><small>Trade-in</small><b>{detail.qualification.trade_in === true ? "Yes" : detail.qualification.trade_in === false ? "No" : "—"}</b></span><span><small>Notes</small><b style={{ whiteSpace: "pre-line" }}>{creNoteText(detail.qualification.notes) || "—"}</b></span></div></section>}
        <section className="sales-form-card sales-outcome-card"><h3>Lead Status Update</h3><div className="sales-stepper">{["F1", "F2", "F3", "F4", "F5"].map((step, index) => <span className={progressState(detail.callCount, index)} key={step}>{index < Math.min(detail.callCount, 4) ? "✓" : index === Math.min(detail.callCount, 4) ? "○" : "▣"} {step}</span>)}</div>
          {isPs ? (
             <div style={{ marginTop: "1rem" }}>
               <h4 style={{ fontSize: "0.85rem", color: "var(--text-light)", marginBottom: "0.5rem" }}>Call status *</h4>
               <div className="sales-choice-row sales-status-update">
                 <button type="button" className={draft.call_status === "Connected" ? "chosen qualified" : ""} onClick={() => { choose("call_status", "Connected"); choose("call_outcome", ""); }}>Connected</button>
                 <button type="button" className={draft.call_status === "Not Connected" ? "chosen pending" : ""} onClick={() => { choose("call_status", "Not Connected"); choose("call_outcome", ""); }}>Not Connected</button>
               </div>
               
               {draft.call_status && (
                 <div style={{ marginTop: "1.5rem" }}>
                   <h4 style={{ fontSize: "0.85rem", color: "var(--text-light)", marginBottom: "0.5rem" }}>Outcome *</h4>
                   <div className="sales-choice-row sales-status-update" style={{ flexWrap: "wrap", justifyContent: "flex-start", gap: "0.5rem" }}>
                     {psVisibleOutcomes.map(o => (
                       <button type="button" key={o.label} className={`${draft.call_outcome === o.label ? "chosen " + o.tone : ""}`} onClick={() => choose("call_outcome", o.label)} style={{ padding: "0.4rem 1rem", borderRadius: "20px", fontSize: "0.85rem", flex: "none", whiteSpace: "nowrap" }}>{o.label}</button>
                     ))}
                   </div>
                 </div>
               )}
               


               {draft.call_outcome && ["PENDING", "WALKIN", "CALLBACK"].includes(statusOptions[draft.call_outcome]?.[0] || "") && (
                 <div style={{ marginTop: "1.5rem" }}>
                   <h4 style={{ fontSize: "0.85rem", color: "var(--text-light)", marginBottom: "0.5rem" }}>Follow Up Date *</h4>
                   <DateInput min={minimumFollowUpDay()} max={maximumFollowUpDay()} value={draft.follow_up_at} onChange={value => choose("follow_up_at", value)} style={{ width: "100%" }} ariaLabel="Follow-up date, DD/MM/YYYY" />
                 </div>
               )}

               <div style={{ marginTop: "1.5rem" }}>
                 <h4 style={{ fontSize: "0.85rem", color: "var(--text-light)", marginBottom: "0.5rem" }}>Remarks *</h4>
                 <textarea value={draft.remarks} onChange={e => choose("remarks", e.target.value)} style={{ width: "100%", padding: "0.75rem", borderRadius: "8px", border: "1px solid var(--border)", minHeight: "100px", resize: "vertical", background: "var(--field-bg)", fontSize: "1rem" }} />
               </div>
             </div>
          ) : (
             <div className="sales-choice-row sales-status-update">{Object.entries(activeOutcomeLabels).map(([value, label]) => <button type="button" className={draft.call_outcome === value ? `chosen ${value.toLowerCase()}` : value.toLowerCase()} onClick={() => selectCallOutcome(value)} key={value}>{value === "QUALIFIED" || value === "RETAILED" ? "✓" : value === "LOST" ? "×" : "◷"} {label}</button>)}</div>
          )}
        </section>

        {!isPs && draft.call_outcome === "QUALIFIED" && <section className="sales-outcome-grid">
          <article className="sales-branch-card"><h3>Model Interested</h3><label>Vehicle model *<select value={draft.model_interest} onChange={event => choose("model_interest", event.target.value)} disabled={!modelOptions.length && !draft.model_interest}><option value="">{modelOptions.length ? "Select model" : "Add models in Lists first"}</option>{optionsWithCurrent(modelOptions, draft.model_interest).map(model => <option value={model} key={model}>{model}</option>)}</select></label></article>
          <article className="sales-branch-card"><h3>Color variant</h3><label>Color variant *<select value={draft.qualification.variant} onChange={event => chooseQualification("variant", event.target.value)} disabled={!colorVariantOptions.length && !draft.qualification.variant}><option value="">{colorVariantOptions.length ? "Select color variant" : "Add color variants in Lists first"}</option>{optionsWithCurrent(colorVariantOptions, draft.qualification.variant).map(option => <option value={option} key={option}>{option}</option>)}</select></label></article>
          <article className="sales-branch-card"><h3>Customer Details</h3><label>Profession</label><ChoiceRow options={professionOptions} value={draft.profession} onChange={value => choose("profession", value)} /><label>Preferred branch *<select value={draft.city} onChange={event => setDraft(current => current ? { ...current, city: event.target.value, custom_location: "", ps_officer_id: "" } : current)}><option value="">Select branch</option>{branchOptions.map(option => <option value={option} key={option}>{option}</option>)}</select></label></article>
          <article className="sales-branch-card"><h3>Assign PS/SO</h3><label>PS/SO for {selectedLocation || "selected branch"} *<select value={draft.ps_officer_id} disabled={!selectedLocation || psLoading} onChange={event => choose("ps_officer_id", event.target.value)}><option value="">{psLoading ? "Loading PS/SO..." : selectedLocation ? "Select PS/SO" : "Select branch first"}</option>{psOptions.map(officer => <option value={officer.id} key={officer.id}>{officer.name} - {officer.location}</option>)}</select></label>{selectedLocation && !psLoading && !psOptions.length && <small>No active PS/SO found for this branch.</small>}</article>
          <article className="sales-branch-card"><h3>Purchase Planning</h3><label>Buying Plan *</label><ChoiceRow options={buyingPlanOptions} value={draft.qualification.buying_timeline} onChange={value => chooseQualification("buying_timeline", value)} /></article>
          <article className="sales-branch-card"><h3>Finance Options</h3><label>Finance Option *</label><ChoiceRow options={financeOptions} value={draft.qualification.finance_type} onChange={value => chooseQualification("finance_type", value)} /></article>
          <article className="sales-branch-card"><h3>Test Drive</h3><label>Test Drive Type</label><ChoiceRow options={testDriveOptions} value={draft.qualification.test_drive} onChange={value => chooseQualification("test_drive", value)} /></article>
          <article className="sales-branch-card"><h3>Trade In</h3><label>Trade In</label><ChoiceRow options={tradeInOptions} value={draft.trade_in_note} onChange={value => choose("trade_in_note", value)} /></article>
          <article className="sales-branch-card"><h3>Qualification Notes</h3><label>Remarks *<textarea value={draft.qualification.notes} onChange={event => chooseQualification("notes", event.target.value)} placeholder="Add qualification notes" /></label></article>
          <article className="sales-branch-card"><h3>Lead Category</h3><label>Lead Category</label><ChoiceRow options={["HOT", "WARM", "COLD"]} value={draft.category} onChange={value => choose("category", value)} /></article>
        </section>}

        {!isPs && draft.call_outcome === "LOST" && <section className="sales-branch-card sales-single-branch lost"><h3>Lead Lost Reason</h3><label>Reason for Loss</label><ChoiceRow options={lostReasons} value={draft.lost_reason} onChange={value => choose("lost_reason", value)} /><label>Remarks *<textarea value={draft.remarks} onChange={event => choose("remarks", event.target.value)} placeholder="Add reason/remark for loss" /></label><p className="sales-warning">△ Lead will be marked as lost and moved to won/lost leads section after update.</p></section>}

        {!isPs && draft.call_outcome === "PENDING" && <section className="sales-outcome-grid">
          <article className="sales-branch-card sales-single-branch"><h3>Pending Reason</h3><label>Pending Status</label><ChoiceRow options={pendingReasons} value={draft.pending_reason} onChange={value => choose("pending_reason", value)} /><label>Remark for Pending Reason *<textarea value={draft.remarks} onChange={event => choose("remarks", event.target.value)} placeholder="Enter detailed remark for this pending reason..." /></label></article>
          <article className="sales-branch-card sales-single-branch"><h3>Follow Up Details</h3><label>Follow Up Date *<DateInput min={minimumFollowUpDay()} max={maximumFollowUpDay()} value={draft.follow_up_at} onChange={value => choose("follow_up_at", value)} ariaLabel="Follow-up date, DD/MM/YYYY" /></label><small>Lead will be moved to the correct follow-up section after update.</small></article>
        </section>}

        {!isPs && draft.call_outcome === "BOOKED" && <section className="sales-outcome-grid">
          <article className="sales-branch-card sales-single-branch"><h3>Booked Follow-up</h3><label>Follow Up Date *<DateInput min={minimumFollowUpDay()} max={maximumFollowUpDay()} value={draft.follow_up_at} onChange={value => choose("follow_up_at", value)} ariaLabel="Follow-up date, DD/MM/YYYY" /></label><label>Remarks *<textarea value={draft.remarks} onChange={event => choose("remarks", event.target.value)} placeholder="Add PS/SO follow-up notes" /></label></article>
        </section>}

        {!isPs && draft.call_outcome === "RETAILED" && <section className="sales-branch-card sales-single-branch"><h3>Retail Details</h3><label>Remarks<textarea value={draft.remarks} onChange={event => choose("remarks", event.target.value)} placeholder="Add sale confirmation notes" /></label><p className="sales-warning">Lead will be marked as won and retailed after update.</p></section>}

        <section className="sales-history"><h3>History</h3>{detail.callHistory.length ? detail.callHistory.map(call => <div className="sales-history-row" key={`call-${call.id}`}><span className="history-dot" /><div><b>{allOutcomeLabels[call.outcome] || statusLabels[call.status] || call.status}</b><small>{call.remarks || "No remarks"} · {call.so_name || "You"}</small></div><time>{formatFollowUp(call.created_at)}</time></div>) : <p className="subtext">No calls recorded yet.</p>}{detail.followUpHistory.length ? detail.followUpHistory.map(followUp => <div className="sales-history-row" key={`follow-${followUp.id}`}><span className="history-dot follow" /><div><b>Follow-up {followUp.resolved_at ? "completed" : "scheduled"}</b><small>{formatFollowUp(followUp.scheduled_for)}</small></div><time>{followUp.resolved_at ? "Resolved" : "Open"}</time></div>) : null}</section>
      </div>
      <footer className="sales-detail-footer"><button className="filter" onClick={() => setDetail(null)}>Close</button><button className={`button primary ${saveTone}`} disabled={saving} onClick={() => void save()}>{saving ? "Saving…" : submitLabel}</button></footer>
    </section></div>}
    {addingLead && <div className="modal-layer" role="presentation"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="add-lead-title"><button className="modal-close" onClick={() => setAddingLead(false)} aria-label="Close">×</button><p className="eyebrow">LEAD INTAKE</p><h2 id="add-lead-title">Add a lead</h2><form className="lead-form" onSubmit={event => { event.preventDefault(); void saveLead(); }}><div className="form-grid"><label>Full name<input required maxLength={160} value={newLead.name} onChange={event => setNewLead(current => ({ ...current, name: event.target.value }))} placeholder="Customer name" /></label><label>Phone number<input required inputMode="numeric" pattern="[0-9]{10}" maxLength={10} value={newLead.phone} onChange={event => setNewLead(current => ({ ...current, phone: event.target.value.replace(/\D/g, "") }))} placeholder="10-digit mobile number" /></label><label>Email<input type="email" inputMode="email" pattern={emailPattern.source} title="Use a complete email such as name@example.com" value={newLead.email} onChange={event => setNewLead(current => ({ ...current, email: event.target.value }))} placeholder="name@example.com" /></label><label>City<input maxLength={100} value={newLead.city} onChange={event => setNewLead(current => ({ ...current, city: event.target.value }))} placeholder="City" /></label><label>Lead source<select value={newLead.source} onChange={event => setNewLead(current => ({ ...current, source: event.target.value }))}>{sourceOptions.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label><label>Enquiry date<DateInput required value={newLead.enquiry_date || ""} max={formatDate(new Date())} onChange={value => setNewLead(current => ({ ...current, enquiry_date: value }))} ariaLabel="Enquiry date, DD/MM/YYYY" /></label><label>Vehicle interest<select required value={newLead.model_interest || ""} onChange={event => setNewLead(current => ({ ...current, model_interest: event.target.value }))} disabled={!modelOptions.length}><option value="">{modelOptions.length ? "Select model" : "Add models in Lists first"}</option>{modelOptions.map(model => <option key={model} value={model}>{model}</option>)}</select></label><label>Campaign<input maxLength={160} value={newLead.campaign} onChange={event => setNewLead(current => ({ ...current, campaign: event.target.value }))} placeholder="Campaign name" /></label><label>Branch *<select required value={newLead.branch || ""} onChange={event => setNewLead(current => ({ ...current, branch: event.target.value, ps_officer_id: undefined }))}><option value="">Select branch</option>{branchOptions.map(branch => <option key={branch} value={branch}>{branch}</option>)}</select></label><label>PS Name *<select required value={newLead.ps_officer_id || ""} onChange={event => setNewLead(current => ({ ...current, ps_officer_id: Number(event.target.value) }))}><option value="">{addLeadPsOptions.length ? "Select PS" : newLead.branch ? "No PS in this branch" : "Select branch first"}</option>{addLeadPsOptions.map(ps => <option key={ps.id} value={ps.id}>{ps.name}</option>)}</select></label></div><label style={{ marginTop: "13px", display: "block" }}>Source detail<input maxLength={100} value={newLead.source_label} onChange={event => setNewLead(current => ({ ...current, source_label: event.target.value }))} placeholder="Ad set, partner, referral, or other detail" /></label>{addLeadError && <p className="form-error" role="alert">{addLeadError}</p>}<p className="subtext">The new lead will be automatically assigned to the selected PS as a Qualified lead.</p><footer><button type="button" className="filter" onClick={() => setAddingLead(false)}>Cancel</button><button className="button primary" disabled={creatingLead || !newLead.ps_officer_id}>{creatingLead ? "Adding…" : "Add lead"}</button></footer></form></section></div>}
    {submittedLead && <div className="modal-layer" role="presentation"><section className="modal success-modal" role="dialog" aria-modal="true" aria-labelledby="submitted-title"><button className="modal-close" onClick={() => setSubmittedLead(null)} aria-label="Close">×</button><div className="success-mark" aria-hidden="true">✓</div><p className="eyebrow">LEAD SUBMITTED</p><h2 id="submitted-title">Thank you, lead submitted.</h2><p className="subtext">{submittedLead} has been directly assigned as Qualified.</p><button className="button primary" onClick={() => setSubmittedLead(null)}>Done</button></section></div>}
  </section>;
}
