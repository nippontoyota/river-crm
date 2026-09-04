"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { assignLead, autoAssignLeads, commitUpload, createLead, deleteLead, distributeFilteredLeads, getAdminAnalytics, getCres, getLeadDetail, getLeadsPage, getOfficers, getSystemConfig, getUpload, logCall, reassignLeads, resolveUploadDuplicates, reviewFollowUp, sourceClass, sourceName, toLead, toOfficer, updateMyLead, type Lead, type LeadDetail, type LeadFilters, type LeadInput, type Officer, type UploadBatch, uploadLeads } from "@/lib/crm";
import { DateInput } from "@/components/date-input";
import { addDays, formatDate, formatDateTime, parseDate, parseDateTime, todayInIST, toDateInputValue } from "@/lib/dates";

function formatCallDate(value: string) {
  return formatDateTime(value) || value;
}

function localDateTimeValue(value: string | null) {
  return formatDateTime(value);
}

function dateTimeInputValue(value: string) {
  const formatted = formatDateTime(value);
  const match = formatted.match(/^(\d{2})\/(\d{2})\/(\d{4}) (\d{2}):(\d{2})$/);
  return match ? `${match[3]}-${match[2]}-${match[1]}T${match[4]}:${match[5]}` : "";
}

const dateTimeInputToIso = (value: string) => value ? new Date(`${value}:00+05:30`).toISOString() : "";

function followUpOptions() {
  const now = new Date();
  const slot = (label: string, offsetMs: number) => {
    const date = new Date(now.getTime() + offsetMs);
    return { label: `${label} · ${formatDateTime(date)}`, value: date.toISOString() };
  };
  const atHour = (label: string, daysAhead: number, hour: number) => {
    const day = addDays(todayInIST(), daysAhead);
    const date = new Date(`${day}T${String(hour).padStart(2, "0")}:00:00+05:30`);
    if (date <= now) return null;
    return { label: `${label} · ${formatDateTime(date)}`, value: date.toISOString() };
  };
  return [
    slot("In 30 minutes", 30 * 60_000),
    slot("In 1 hour", 60 * 60_000),
    slot("In 2 hours", 2 * 60 * 60_000),
    slot("In 4 hours", 4 * 60 * 60_000),
    atHour("Tomorrow 10:00 AM", 1, 10),
    atHour("Tomorrow 2:00 PM", 1, 14),
    atHour("Day after 10:00 AM", 2, 10),
  ].filter(Boolean) as { label: string; value: string }[];
}

const nextOutcomes: Record<string, { label: string; value: string }[]> = {
  Fresh: [{ label: "No response", value: "RNR" }, { label: "Schedule callback", value: "CALLBACK" }, { label: "Interested / Qualified", value: "QUALIFIED" }, { label: "Not interested", value: "UNQUALIFIED" }],
  RNR: [{ label: "Schedule callback", value: "CALLBACK" }, { label: "Interested / Qualified", value: "QUALIFIED" }, { label: "Not interested", value: "UNQUALIFIED" }],
  Callback: [{ label: "No response", value: "RNR" }, { label: "Interested / Qualified", value: "QUALIFIED" }, { label: "Book walk-in", value: "WALKIN" }, { label: "Not interested", value: "UNQUALIFIED" }],
  Qualified: [{ label: "Book walk-in", value: "WALKIN" }, { label: "Won (Sold)", value: "WON" }, { label: "Lost", value: "LOST" }],
  "Walk-in": [{ label: "Won (Sold)", value: "WON" }, { label: "Lost", value: "LOST" }],
};

const leadStatuses = [["FRESH", "Fresh"], ["RNR", "RNR"], ["SWITCHED_OFF", "Switch off"], ["CALLBACK", "Callback"], ["PENDING", "Pending"], ["QUALIFIED", "Qualified"], ["WALKIN", "Walk-in"], ["WON", "Won"], ["LOST", "Lost"], ["UNQUALIFIED", "Unqualified"]];
const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const emptyLead = (): LeadInput => ({ name: "", phone: "", email: "", source: "", source_label: "", model_interest: "", city: "", enquiry_date: formatDate(new Date()) });
const optionsWithCurrent = (options: string[], current = "") => {
  const value = current.trim();
  return value && !options.includes(value) ? [value, ...options] : options;
};
const downloadLeadSample = (source: string) => {
  const leadSampleRows = [
    ["name", "phone", "email", "source", "campaign", "model", "city", "enquiry date"],
    ["Aarav Sharma", "9876543210", "aarav@example.com", source, "Campaign name", "Admin model name", "Kochi", "22/08/2026"],
    ["Ananya Reddy", "9876543211", "ananya@example.com", source, "Campaign name", "Admin model name", "Thrissur", "22/08/2026"],
  ];
  const csv = leadSampleRows.map(row => row.map(value => `"${value.replaceAll('"', '""')}"`).join(",")).join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "incheon-bulk-leads-sample.csv";
  link.click();
  URL.revokeObjectURL(url);
};
const leadQuery = (officerMode: boolean, followUpsOnly: boolean, filters: LeadFilters, page: number, search: string, assignmentView = "fresh", reassignmentRole: "CRE" | "SO" = "CRE") => {
  const params = new URLSearchParams();
  if (officerMode) { if (followUpsOnly) params.set("status", "CALLBACK"); }
  else { 
    if (assignmentView === "fresh") params.set("unassigned", "true");
    else if (assignmentView === "qualified") params.set("ps_unassigned", "true");
    else if (assignmentView === "reassignment") params.set("needs_reassignment", reassignmentRole);
    params.set("page", String(page)); 
    Object.entries(filters).forEach(([key, value]) => { if (value && (!key.startsWith("date_") || toDateInputValue(value))) params.set(key, key.startsWith("date_") ? toDateInputValue(value) : value); });
  }
  if (search) params.set("q", search);
  return `?${params.toString()}`;
};

function LeadPagination({ page, total, loading, onPageChange }: { page: number; total: number; loading: boolean; onPageChange: (page: number) => void }) {
  const pageSize = 50;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const first = total ? (page - 1) * pageSize + 1 : 0;
  const last = Math.min(page * pageSize, total);
  return <nav className="lead-pagination" aria-label="Lead pages"><span>Showing {first}–{last} of {total} leads</span><div><button className="filter" disabled={loading || page <= 1} onClick={() => onPageChange(page - 1)} aria-label="Previous page">‹</button><b>Page {page} of {totalPages}</b><button className="filter" disabled={loading || page >= totalPages} onClick={() => onPageChange(page + 1)} aria-label="Next page">›</button></div></nav>;
}

type AdminMode = "assignment" | "all";
type AllLeadStatusFilter = "all" | "fresh" | "qualified" | "reassignment";
const allLeadStatusFilters: { value: AllLeadStatusFilter; label: string; status?: string }[] = [{ value: "all", label: "All leads" }, { value: "fresh", label: "Fresh", status: "FRESH" }, { value: "qualified", label: "Qualified", status: "QUALIFIED" }, { value: "reassignment", label: "Needs reassignment" }];

export function LeadDesk({ officerMode = false, followUpsOnly = false, adminMode = "assignment" }: { officerMode?: boolean; followUpsOnly?: boolean; adminMode?: AdminMode }) {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [creUsers, setCreUsers] = useState<Officer[]>([]);
  const [psUsers, setPsUsers] = useState<Officer[]>([]);
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [analytics, setAnalytics] = useState<any>(null);
  const [allLeadStatus, setAllLeadStatus] = useState<AllLeadStatusFilter>("fresh");
  const [activeLead, setActiveLead] = useState<Lead | null>(null);
  const [leadDetail, setLeadDetail] = useState<LeadDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [deletingLead, setDeletingLead] = useState(false);
  const [outcome, setOutcome] = useState("");
  const [remarks, setRemarks] = useState("");
  const [followUpAt, setFollowUpAt] = useState("");
  const [editingCustomer, setEditingCustomer] = useState(false);
  const [editDetails, setEditDetails] = useState({ name: "", phone: "", model: "", variant: "", trade_in: null as boolean | null, category: "" });
  const [savingDetails, setSavingDetails] = useState(false);
  const [savingCall, setSavingCall] = useState(false);
  const [addingLead, setAddingLead] = useState(false);
  const [creatingLead, setCreatingLead] = useState(false);
  const [newLead, setNewLead] = useState<LeadInput>(emptyLead);
  const [newLeadColor, setNewLeadColor] = useState("");
  const [draggedOfficerId, setDraggedOfficerId] = useState<number | null>(null);
  const [dropTargetId, setDropTargetId] = useState<number | null>(null);
  const [upload, setUpload] = useState<UploadBatch | null>(null);
  const [uploading, setUploading] = useState(false);
  const [checkingUpload, setCheckingUpload] = useState(false);
  const [importingUpload, setImportingUpload] = useState(false);
  const [submittedLead, setSubmittedLead] = useState<string | null>(null);
  const [filters, setFilters] = useState<LeadFilters>({});
  const today = todayInIST();
  const selectedTo = toDateInputValue(filters.date_to);
  const historicalFromMax = selectedTo && selectedTo < today ? filters.date_to : today;
  const [models, setModels] = useState<string[]>([]);
  const [branches, setBranches] = useState<string[]>([]);
  const [colorVariantOptions, setColorVariantOptions] = useState<string[]>([]);
  const [sourceOptions, setSourceOptions] = useState<string[]>(["WALKIN"]);
  const [activeFilters, setActiveFilters] = useState<LeadFilters>({});
  const [manualAssigning, setManualAssigning] = useState(false);
  const [bucketOfficerIds, setBucketOfficerIds] = useState<number[]>([]);
  const [bucketAssigning, setBucketAssigning] = useState(false);
  const [page, setPage] = useState(1);
  const [searchFilter, setSearchFilter] = useState("");
  const [totalLeads, setTotalLeads] = useState(0);
  const [reassignmentRole, setReassignmentRole] = useState<"CRE" | "SO">("CRE");
  const [selectedReassignmentLeads, setSelectedReassignmentLeads] = useState<number[]>([]);
  const [selectedReassignmentUsers, setSelectedReassignmentUsers] = useState<number[]>([]);
  const [reassigning, setReassigning] = useState(false);
  const [reviewingFollowup, setReviewingFollowup] = useState<number | null>(null);
  const [followupDrafts, setFollowupDrafts] = useState<Record<number, string>>({});
  const supportLoaded = useRef(false);
  const listRequest = useRef(0);
  const isAdminAllLeads = !officerMode && adminMode === "all";
  const isAssignmentDesk = !officerMode && adminMode === "assignment";
  const leadView = isAdminAllLeads ? allLeadStatus === "reassignment" ? "reassignment" : "all" : "fresh";
  const assignmentUsers = creUsers;
  const effectiveActiveFilters = useMemo<LeadFilters>(() => {
    const status = allLeadStatusFilters.find(item => item.value === allLeadStatus)?.status;
    return isAdminAllLeads && status ? { ...activeFilters, status } : activeFilters;
  }, [activeFilters, allLeadStatus, isAdminAllLeads]);
  const assignmentFilters = useMemo<LeadFilters>(() => ({ ...activeFilters, ...(searchFilter ? { q: searchFilter } : {}) }), [activeFilters, searchFilter]);

  const refresh = useCallback(async () => {
    const request = ++listRequest.current;
    setLoading(true); setError("");
    try {
      const queryString = leadQuery(officerMode, followUpsOnly, effectiveActiveFilters, page, searchFilter, leadView, reassignmentRole);
      if (officerMode) { const result = await getLeadsPage(queryString); if (request !== listRequest.current) return; setLeads(result.results); setTotalLeads(result.count); }
      else {
        if (!supportLoaded.current) {
          const [pool, creRecords, psRecords, analyticsResult] = await Promise.all([getLeadsPage(queryString), getCres(), getOfficers(), getAdminAnalytics()]);
          if (request !== listRequest.current) return;
          setLeads(pool.results); setTotalLeads(pool.count);
          setCreUsers(creRecords.map(officer => toOfficer(officer, analyticsResult.cre.find(item => item.id === officer.id))));
          setPsUsers(psRecords.map(officer => toOfficer(officer, analyticsResult.officers.find(item => item.id === officer.id))));
          setAnalytics(analyticsResult);
          supportLoaded.current = true;
        } else {
          const pool = await getLeadsPage(queryString);
          if (request !== listRequest.current) return;
          setLeads(pool.results); setTotalLeads(pool.count);
        }
      }
    } catch (requestError) { if (request === listRequest.current) setError(requestError instanceof Error ? requestError.message : "Unable to load CRM data."); }
    finally { if (request === listRequest.current) setLoading(false); }
  }, [effectiveActiveFilters, followUpsOnly, leadView, officerMode, page, reassignmentRole, searchFilter]);

  useEffect(() => { const timer = window.setTimeout(() => void refresh(), 0); return () => window.clearTimeout(timer); }, [refresh]);
  useEffect(() => {
    void getSystemConfig().then(config => {
      setModels(config.lists?.models || []);
      setBranches(config.lists?.branches || []);
      setColorVariantOptions(config.lists?.colorVariants || []);
      setSourceOptions(config.lists?.sources || ["WALKIN"]);
    }).catch(() => {
      setModels([]);
      setBranches([]);
      setColorVariantOptions([]);
      setSourceOptions(["WALKIN"]);
    });
  }, []);
  useEffect(() => { const timer = window.setTimeout(() => { setPage(1); setSearchFilter(query.trim()); }, 250); return () => window.clearTimeout(timer); }, [query]);
  useEffect(() => { const timer = window.setTimeout(() => { setPage(1); setActiveFilters(current => JSON.stringify(current) === JSON.stringify(filters) ? current : { ...filters }); }, 250); return () => window.clearTimeout(timer); }, [filters]);
  useEffect(() => {
    const open = () => setAddingLead(true);
    window.addEventListener("incheon:add-lead", open);
    if (!officerMode && new URLSearchParams(window.location.search).get("addLead") === "1") { open(); window.history.replaceState({}, "", "/leads"); }
    return () => window.removeEventListener("incheon:add-lead", open);
  }, [officerMode]);

  const visible = useMemo(() => leads.filter(lead => `${lead.name} ${lead.phone}`.toLowerCase().includes(query.toLowerCase())), [leads, query]);
  const needsAppointment = ["CALLBACK", "WALKIN", "PENDING"].includes(outcome);
  const selectedBucketOfficers = useMemo(() => bucketOfficerIds.map(id => creUsers.find(officer => officer.id === id)).filter(Boolean) as Officer[], [bucketOfficerIds, creUsers]);
  const reassignmentUsers = reassignmentRole === "CRE" ? creUsers : psUsers;
  const bucketName = useMemo(() => {
    const parts = [activeFilters.source && sourceName(activeFilters.source), activeFilters.model, searchFilter && `Search: ${searchFilter}`].filter(Boolean);
    return parts.length ? parts.join(" · ") : "All fresh leads";
  }, [activeFilters, searchFilter]);
  const bucketSplit = useMemo(() => {
    if (!selectedBucketOfficers.length) return [];
    const base = Math.floor(totalLeads / selectedBucketOfficers.length);
    const extra = totalLeads % selectedBucketOfficers.length;
    return selectedBucketOfficers.map((officer, index) => ({ officer, count: base + (index < extra ? 1 : 0) }));
  }, [selectedBucketOfficers, totalLeads]);

  const toggleBucketOfficer = (officerId: number) => {
    setBucketOfficerIds(current => current.includes(officerId) ? current.filter(id => id !== officerId) : [...current, officerId]);
  };

  const toggleReassignmentLead = (leadId: number) => setSelectedReassignmentLeads(current => current.includes(leadId) ? current.filter(id => id !== leadId) : [...current, leadId]);
  const toggleReassignmentUser = (userId: number) => setSelectedReassignmentUsers(current => current.includes(userId) ? current.filter(id => id !== userId) : [...current, userId]);

  const assignReassignmentQueue = async () => {
    if (!selectedReassignmentLeads.length || !selectedReassignmentUsers.length || reassigning) return;
    setReassigning(true); setError("");
    try {
      const result = await reassignLeads(reassignmentRole, selectedReassignmentLeads, selectedReassignmentUsers);
      setNotice(`${result.assigned} lead${result.assigned === 1 ? "" : "s"} reassigned${result.skipped ? `; ${result.skipped} stayed in the pool because no selected PS/SO matched the branch` : ""}.`);
      setSelectedReassignmentLeads([]); setSelectedReassignmentUsers([]);
      await refresh();
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Reassignment failed."); }
    finally { setReassigning(false); }
  };

  const assign = async (lead: Lead, officerId: number) => {
    const previousLeads = leads;
    const previousUsers = assignmentUsers;
    const setUsers = setCreUsers;
    setLeads(current => current.filter(item => item.id !== lead.id));
    setUsers(current => current.map(officer => officer.id === officerId ? { ...officer, assigned: officer.assigned + 1 } : officer));
    try { await assignLead(lead.id, officerId); setNotice(`${lead.name} assigned to CRE.`); }
    catch (requestError) { setLeads(previousLeads); setUsers(previousUsers); setError(requestError instanceof Error ? requestError.message : "Assignment failed."); }
    finally { setDropTargetId(null); }
  };

  const autoAssign = async () => {
    try { const result = await autoAssignLeads(); setNotice(`${result.assigned} leads assigned.`); await refresh(); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Auto-assignment failed."); }
  };

  const assignBucket = async () => {
    if (!bucketOfficerIds.length || !totalLeads || bucketAssigning) return;
    if (!window.confirm(`Assign ${totalLeads} matching fresh leads across ${bucketOfficerIds.length} CREs?`)) return;
    setBucketAssigning(true); setError("");
    try {
      const result = await distributeFilteredLeads(bucketOfficerIds, assignmentFilters);
      const assignedByOfficer = new Map(result.distribution.map(item => [item.sales_officer_id, item.assigned]));
      setCreUsers(current => current.map(officer => ({ ...officer, assigned: officer.assigned + (assignedByOfficer.get(officer.id) || 0) })));
      setNotice(`${result.assigned} leads assigned across ${bucketOfficerIds.length} CREs.`);
      setBucketOfficerIds([]);
      await refresh();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Bucket assignment failed.");
    } finally {
      setBucketAssigning(false);
    }
  };

  const manualAssignCre = async (officerId: number) => {
    if (!activeLead || !isAdminAllLeads || activeLead.assignedSoId || manualAssigning) return;
    const officer = creUsers.find(item => item.id === officerId);
    if (!officer) return;
    setManualAssigning(true); setError("");
    try {
      await assignLead(activeLead.id, officer.id);
      setActiveLead(current => current ? { ...current, assignedSoId: officer.id, assignedSoName: officer.name } : current);
      setLeads(current => current.map(lead => lead.id === activeLead.id ? { ...lead, assignedSoId: officer.id, assignedSoName: officer.name } : lead));
      setCreUsers(current => current.map(item => item.id === officer.id ? { ...item, assigned: item.assigned + 1 } : item));
      setNotice(`${activeLead.name} assigned to ${officer.name}.`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Manual assignment failed.");
    } finally {
      setManualAssigning(false);
    }
  };

  const saveCall = async () => {
    if (!officerMode || !activeLead || !outcome || savingCall) return;
    if (needsAppointment && !followUpAt) { setError("Select a follow-up time."); return; }
    const parsedFollowUpAt = followUpAt ? parseDateTime(followUpAt) || (Number.isNaN(new Date(followUpAt).getTime()) ? "" : new Date(followUpAt).toISOString()) : "";
    if (needsAppointment && !parsedFollowUpAt) { setError("Enter follow-up time as DD/MM/YYYY HH:mm."); return; }
    setError("");
    setSavingCall(true);
    try {
      await logCall(activeLead.id, { status: outcome, remarks, ...(parsedFollowUpAt ? { follow_up_at: parsedFollowUpAt } : {}) });
      setNotice(`Call log saved for ${activeLead.name}.`); setActiveLead(null); setLeadDetail(null); setRemarks(""); setFollowUpAt(""); await refresh();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Follow-up could not be updated.");
    } finally { setSavingCall(false); }
  };

  const startEditing = () => {
    setEditDetails({
      name: activeLead?.name || "",
      phone: activeLead?.phone || "",
      model: activeLead?.model || "",
      variant: leadDetail?.qualification?.variant || "",
      trade_in: leadDetail?.qualification?.trade_in ?? null,
      category: activeLead?.category || "WARM"
    });
    setEditingCustomer(true);
  };

  const saveCustomerDetails = async () => {
    if (!activeLead) return;
    if (!editDetails.model) { setError("Select a vehicle model from Admin Lists."); return; }
    setSavingDetails(true);
    try {
      await updateMyLead(activeLead.id, {
        name: editDetails.name,
        phone: editDetails.phone,
        model_interest: editDetails.model,
        category: editDetails.category,
        qualification: {
          variant: editDetails.variant,
          buying_timeline: leadDetail?.qualification?.buying_timeline || "",
          finance_type: leadDetail?.qualification?.finance_type || "",
          trade_in: editDetails.trade_in,
          test_drive: leadDetail?.qualification?.test_drive || "",
          notes: leadDetail?.qualification?.notes || ""
        }
      });
      setNotice(`Customer details updated for ${editDetails.name}.`);
      setActiveLead({ ...activeLead, name: editDetails.name, phone: editDetails.phone, model: editDetails.model, category: editDetails.category });
      if (leadDetail) {
        setLeadDetail({
          ...leadDetail,
          qualification: { ...leadDetail.qualification, variant: editDetails.variant, buying_timeline: leadDetail.qualification?.buying_timeline || "", finance_type: leadDetail.qualification?.finance_type || "", trade_in: editDetails.trade_in, test_drive: leadDetail.qualification?.test_drive || "", notes: leadDetail.qualification?.notes || "" }
        });
      }
      setEditingCustomer(false);
      const newPool = await getLeadsPage(leadQuery(officerMode, followUpsOnly, activeFilters, page, searchFilter, leadView, reassignmentRole));
      setLeads(newPool.results);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Details could not be saved.");
    } finally { setSavingDetails(false); }
  };

  const openLead = async (lead: Lead) => {
    const initialOutcome = officerMode ? nextOutcomes[lead.status]?.[0]?.value || "" : "";
    setActiveLead(lead); setOutcome(initialOutcome); setRemarks(""); setFollowUpAt(officerMode ? localDateTimeValue(lead.nextFollowUp) : ""); setEditingCustomer(false); setSavingCall(false); setError("");
    if (!officerMode) {
      setDetailLoading(true);
      try {
        const detail = await getLeadDetail(lead.id);
        setLeadDetail(detail);
        setFollowupDrafts(Object.fromEntries(detail.followUpHistory.filter(item => item.reminder_held && !item.resolved_at).map(item => [item.id, dateTimeInputValue(item.scheduled_for)])));
      }
      catch { /* detail fetch failed, modal still works with basic data */ }
      finally { setDetailLoading(false); }
    }
  };

  const removeActiveLead = async () => {
    if (!activeLead || deletingLead || !window.confirm(`Delete ${activeLead.name}? This lead will be removed from CRM views.`)) return;
    setDeletingLead(true); setError("");
    try {
      const deletedName = activeLead.name;
      await deleteLead(activeLead.id);
      setActiveLead(null); setLeadDetail(null); setEditingCustomer(false);
      setLeads(current => current.filter(lead => lead.id !== activeLead.id));
      setTotalLeads(current => Math.max(0, current - 1));
      setNotice(`${deletedName} was deleted.`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Lead could not be deleted.");
    } finally { setDeletingLead(false); }
  };

  const reviewHeldFollowup = async (id: number, action: "APPROVE" | "RESOLVE", original: string) => {
    if (!activeLead || reviewingFollowup) return;
    const draft = followupDrafts[id] || "";
    const changedSchedule = draft && draft !== dateTimeInputValue(original) ? dateTimeInputToIso(draft) : undefined;
    setReviewingFollowup(id); setError("");
    try {
      await reviewFollowUp(id, action, action === "APPROVE" ? changedSchedule : undefined);
      const detail = await getLeadDetail(activeLead.id);
      setLeadDetail(detail);
      setNotice(action === "APPROVE" ? "Reminder released to the current owner." : "Follow-up resolved.");
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Follow-up review failed."); }
    finally { setReviewingFollowup(null); }
  };

  const saveLead = async () => {
    if (creatingLead) return;
    const email = newLead.email?.trim() || "";
    if (email && !emailPattern.test(email)) { setError("Enter a valid email address, such as name@example.com."); return; }
    if (!newLead.source) { setError("Select a lead source from Admin Lists."); return; }
    if (!newLead.model_interest) { setError("Select a vehicle model from Admin Lists."); return; }
    if (!newLeadColor) { setError("Select a color from Admin Lists."); return; }
    const enquiryDate = parseDate(newLead.enquiry_date || "");
    if (!enquiryDate) { setError("Enter the enquiry date as DD/MM/YYYY."); return; }
    const today = parseDate(formatDate(new Date()));
    if (today && enquiryDate > today) { setError("Enquiry date cannot be in the future."); return; }
    setCreatingLead(true); setError("");
    try {
      const lead = await createLead({ ...newLead, email, enquiry_date: enquiryDate, qualification_input: { variant: newLeadColor, buying_timeline: "", finance_type: "", trade_in: null, test_drive: "", notes: "" } });
      setLeads(current => [toLead(lead), ...current]);
      setAddingLead(false); setNewLead(emptyLead()); setNewLeadColor(""); setSubmittedLead(lead.name);
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Lead could not be added."); }
    finally { setCreatingLead(false); }
  };

  const selectFile = async (file?: File) => {
    if (!file) return;
    setUploading(true); setError("");
    try { const batch = await uploadLeads(file); setUpload(batch); setNotice("File received. Check import when parsing finishes."); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Upload failed."); }
    finally { setUploading(false); }
  };
  const checkUpload = async () => {
    if (!upload || checkingUpload) return;
    setCheckingUpload(true);
    try {
      const summary = await getUpload(upload.id);
      const nextUpload = summary.status === "READY" && (summary.removed_duplicates > 0 || summary.pending_duplicates > 0) ? await getUpload(upload.id, true) : summary;
      setUpload(nextUpload);
      if (nextUpload.status === "READY" && nextUpload.removed_duplicates > 0) {
        setNotice(`${nextUpload.removed_duplicates} duplicate ${nextUpload.removed_duplicates === 1 ? "row was" : "rows were"} removed: ${nextUpload.crm_duplicates_found} already in CRM, ${nextUpload.file_duplicates_found} repeated in this file.`);
      }
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Unable to check import."); }
    finally { setCheckingUpload(false); }
  };
  const removeDuplicates = async (rowIds: number[]) => {
    if (!upload || !rowIds.length) return;
    try {
      await resolveUploadDuplicates(upload.id, rowIds.map(id => ({ id, resolution: "SKIP" })));
      setUpload(await getUpload(upload.id, true));
      setNotice(`${rowIds.length} duplicate ${rowIds.length === 1 ? "row removed" : "rows removed"} from this import.`);
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Duplicate rows could not be removed."); }
  };
  const importUpload = async () => {
    if (!upload || importingUpload) return;
    setImportingUpload(true); setError("");
    try {
      const result = await commitUpload(upload.id);
      const duplicateNote = upload.removed_duplicates ? ` ${upload.removed_duplicates} duplicate ${upload.removed_duplicates === 1 ? "row was" : "rows were"} skipped.` : "";
      setUpload(null); setNotice(`${result.created} leads imported.${duplicateNote} Assign them from the pool.`);
      setLoading(true);
      const pageResult = await getLeadsPage(leadQuery(false, false, effectiveActiveFilters, page, searchFilter, leadView, reassignmentRole));
      setLeads(pageResult.results); setTotalLeads(pageResult.count);
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Import failed."); }
    finally { setImportingUpload(false); setLoading(false); }
  };
  const duplicateRows = upload?.rows?.filter(row => row.duplicate_type && row.resolution === "PENDING") || [];
  const removedDuplicateRows = upload?.rows?.filter(row => row.duplicate_type && row.resolution === "SKIP") || [];
  const importableRows = upload?.rows ? upload.rows.filter(row => !row.validation_error && row.resolution !== "SKIP").length : upload?.parsed_ok;
  const targetLabel = "CRE";
  const poolLabel = isAdminAllLeads ? allLeadStatus === "fresh" ? "Fresh leads" : allLeadStatus === "qualified" ? "Qualified leads" : allLeadStatus === "reassignment" ? "Needs reassignment" : "All leads" : "Fresh lead pool";
  const heading = followUpsOnly ? "Follow-ups" : officerMode ? "My queue" : isAdminAllLeads ? "All leads" : "Assignment desk";
  const adminTitle = isAdminAllLeads ? <>All <span>leads.</span></> : <>Lead <span>assignment.</span></>;
  const adminSubtext = isAdminAllLeads ? "Filter and review every lead in the CRM." : "Assign fresh unassigned leads to CREs.";
  const adminMetrics = !officerMode && analytics?.summary ? (
    <section className="admin-leads-metrics">
      <article className="sales-metric blue">
        <span>ALL LEADS</span>
        <strong>{analytics.summary.total_assigned || 0}</strong>
        <small>Total managed leads</small>
      </article>
      <article className="sales-metric mint">
        <span>BOOKED</span>
        <strong>{analytics.summary.walkins || 0}</strong>
        <small>Appointments scheduled</small>
      </article>
      <article className="sales-metric green">
        <span>RETAILED</span>
        <strong>{analytics.summary.won || 0}</strong>
        <small>Successfully closed</small>
      </article>
      <article className="sales-metric red">
        <span>LOST</span>
        <strong>{analytics.summary.lost || 0}</strong>
        <small>Dropped leads</small>
      </article>
    </section>
  ) : null;
  const adminFilterBand = !officerMode ? (
    <section className="panel admin-filter-band">
      <section className="lead-toolbar admin-filter-toolbar">
        <label className="search"><span>⌕</span><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search by name or mobile..." /></label>
        <label className="button filter bulk-upload-button">{uploading ? "Uploading…" : "Bulk Upload"}<input hidden type="file" accept=".xlsx,.csv" onChange={event => void selectFile(event.target.files?.[0])} /></label>
        <button className="filter sample-download" onClick={() => downloadLeadSample(sourceOptions.find(item => item !== "WALKIN") || "WALKIN")}>Download sample format</button>
        <button className="button primary" onClick={() => { setError(""); setAddingLead(true); }}>＋ Add lead</button>
      </section>
      <section className="lead-filters admin-lead-filters">
        <div className="lead-filters-grid">
          <label>Source<select value={filters.source || ""} onChange={event => setFilters(current => ({ ...current, source: event.target.value || undefined }))}><option value="">All sources</option>{sourceOptions.map(item => <option key={item} value={item}>{sourceName(item)}</option>)}</select></label>
          <label>Model<select value={filters.model || ""} onChange={event => setFilters(current => ({ ...current, model: event.target.value || undefined }))} disabled={!models.length}><option value="">{models.length ? "Any model" : "Add models in Lists first"}</option>{models.map(model => <option key={model} value={model}>{model}</option>)}</select></label>
          {allLeadStatus === "reassignment" && <label>Status<select value={filters.status || ""} onChange={event => setFilters(current => ({ ...current, status: event.target.value || undefined }))}><option value="">All statuses</option>{leadStatuses.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>}
          {allLeadStatus === "reassignment" && <label>Branch<select value={filters.branch || ""} onChange={event => setFilters(current => ({ ...current, branch: event.target.value || undefined }))}><option value="">All branches</option>{branches.map(branch => <option key={branch} value={branch}>{branch}</option>)}</select></label>}
          <label>From<DateInput value={filters.date_from || ""} max={historicalFromMax} onChange={next => setFilters(current => { const value = next || undefined; const valueIso = toDateInputValue(value); const toIso = toDateInputValue(current.date_to); return { ...current, date_from: value, date_to: valueIso && toIso && toIso < valueIso ? value : current.date_to }; })} ariaLabel="From date, DD/MM/YYYY" /></label>
          <label>To<DateInput value={filters.date_to || ""} min={filters.date_from || undefined} max={today} onChange={next => setFilters(current => { const value = next || undefined; const valueIso = toDateInputValue(value); const fromIso = toDateInputValue(current.date_from); return { ...current, date_to: value, date_from: valueIso && fromIso && fromIso > valueIso ? value : current.date_from }; })} ariaLabel="To date, DD/MM/YYYY" /></label>
        </div>
        <footer className="lead-filters-actions">
          <span>{Object.values(activeFilters).filter(Boolean).length || searchFilter ? `Filtered ${poolLabel.toLowerCase()}` : `All ${poolLabel.toLowerCase()}`}</span>
          <div>
            <button className="filter" onClick={() => { setFilters({}); setActiveFilters({}); setQuery(""); }}>Clear</button>
            <button className="filter" onClick={() => setActiveFilters({ ...filters })}>Apply filters</button>
            {isAssignmentDesk && <section className="bucket-assignment"><p className="eyebrow">BUCKET</p><b>{bucketName}</b><span>{totalLeads} matching fresh lead{totalLeads === 1 ? "" : "s"}</span>{bucketSplit.length ? <div>{bucketSplit.map(item => <small key={item.officer.id}>{item.officer.name}: <b>{item.count}</b></small>)}</div> : <small>Select CRE cards above to split this bucket.</small>}<button className="button primary" onClick={() => void assignBucket()} disabled={!bucketOfficerIds.length || !totalLeads || bucketAssigning}>{bucketAssigning ? "Assigning…" : "Assign bucket"}</button></section>}
          </div>
        </footer>
      </section>
    </section>
  ) : null;

  return <section className="page">
    {officerMode ? <div className="page-heading compact"><div><p className="eyebrow">{heading.toUpperCase()}</p><h1>Keep the <span>promise.</span></h1><p className="subtext">Your assigned conversations and follow-ups.</p></div></div> : <div className="admin-leads-heading"><div className="admin-heading-main"><p className="eyebrow">{heading.toUpperCase()}</p><h1>{adminTitle}</h1><p className="subtext">{adminSubtext}</p></div>{adminMetrics}<div className="admin-heading-actions">{isAssignmentDesk && <button className="button primary" onClick={autoAssign} disabled={!leads.length}>↻ Auto assign {leads.length} leads</button>}</div></div>}
    {isAdminAllLeads && <div className="admin-lead-tabs">{allLeadStatusFilters.map(item => <button key={item.value} className={allLeadStatus === item.value ? "active" : ""} onClick={() => { setAllLeadStatus(item.value); setSelectedReassignmentLeads([]); setSelectedReassignmentUsers([]); if (item.value !== "reassignment") { setFilters(current => ({ ...current, status: undefined, branch: undefined })); setActiveFilters(current => ({ ...current, status: undefined, branch: undefined })); } setPage(1); }}>{item.label}</button>)}</div>}
    {isAdminAllLeads && allLeadStatus === "reassignment" && <section className="panel reassignment-console">
      <header><div><p className="eyebrow">OFFBOARDING HANDOFF</p><h2>Route stranded work</h2></div><div className="reassignment-role-tabs"><button className={reassignmentRole === "CRE" ? "active" : ""} onClick={() => { setReassignmentRole("CRE"); setSelectedReassignmentLeads([]); setSelectedReassignmentUsers([]); }}>CRE</button><button className={reassignmentRole === "SO" ? "active" : ""} onClick={() => { setReassignmentRole("SO"); setSelectedReassignmentLeads([]); setSelectedReassignmentUsers([]); }}>PS/SO</button></div></header>
      <div className="reassignment-controls"><div><b>{selectedReassignmentLeads.length} of {leads.length} leads selected</b><button className="filter" onClick={() => setSelectedReassignmentLeads(selectedReassignmentLeads.length === leads.length ? [] : leads.map(lead => lead.id))}>{selectedReassignmentLeads.length === leads.length && leads.length ? "Clear page" : "Select page"}</button></div><div className="reassignment-recipient-list">{reassignmentUsers.map(user => <label className={selectedReassignmentUsers.includes(user.id) ? "selected" : ""} key={user.id}><input type="checkbox" checked={selectedReassignmentUsers.includes(user.id)} onChange={() => toggleReassignmentUser(user.id)} /><span><b>{user.name}</b><small>{reassignmentRole === "SO" ? user.location || "No branch" : `${user.assigned} active leads`}</small></span></label>)}</div><button className="button primary" disabled={!selectedReassignmentLeads.length || !selectedReassignmentUsers.length || reassigning} onClick={() => void assignReassignmentQueue()}>{reassigning ? "Assigning…" : "Balance and assign"}</button></div>
      {reassignmentRole === "SO" && <p className="reassignment-note">PS/SO leads only move to selected employees in the same branch. Unmatched leads stay here.</p>}
    </section>}
    {adminFilterBand}
    {officerMode && <section className="lead-toolbar"><label className="search" style={{ flex: 1 }}><span>⌕</span><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search by name or mobile..." /></label><button className="button primary" onClick={() => { setError(""); setAddingLead(true); }}>＋ Add lead</button></section>}
    {upload && (
      <section className="panel" style={{ padding: "1rem", marginBottom: "1rem" }}>
        <b>Import: {upload.status === "PARSING" ? "Checking file…" : upload.status}</b>
        <span> · {importableRows}/{upload.total_rows} rows ready to import</span>
        {upload.removed_duplicates > 0 && <span> · {upload.removed_duplicates} duplicates auto-removed</span>}
        {upload.pending_duplicates > 0 && <span> · {upload.pending_duplicates} duplicates need review</span>}
        <div style={{ display: "inline-flex", gap: ".5rem", marginLeft: "1rem" }}>
          <button className="filter" disabled={checkingUpload || uploading} onClick={() => void checkUpload()}>{checkingUpload ? "Checking…" : "Check import"}</button>
          {upload.status === "READY" && !duplicateRows.length && <button className="button primary" disabled={importingUpload} onClick={() => void importUpload()}>{importingUpload ? "Importing…" : "Import leads"}</button>}
        </div>
        {upload.removed_duplicates > 0 && (
          <div style={{ marginTop: "1rem" }}>
            <p className="subtext">{upload.removed_duplicates} duplicate {upload.removed_duplicates === 1 ? "row was" : "rows were"} removed automatically: {upload.crm_duplicates_found} already in CRM, {upload.file_duplicates_found} repeated inside this file.</p>
            {removedDuplicateRows.length > 0 && <div style={{ display: "grid", gap: ".5rem", marginTop: ".75rem" }}>{removedDuplicateRows.map(row => <div key={row.id} className="lead-summary"><b>Row {row.row_number} · {row.data.name || "Unnamed lead"}</b><span>{row.duplicate_type === "CRM" ? "Already in CRM" : "Duplicate in Excel"}</span><small>{row.normalized_phone} · Matches {row.existing_name || "matching lead"}</small></div>)}</div>}
          </div>
        )}
        {duplicateRows.length > 0 && <div style={{ marginTop: "1rem" }}><p className="subtext">Duplicates need review. Remove them from this import to keep the existing lead.</p><button className="filter" onClick={() => void removeDuplicates(duplicateRows.map(row => row.id))}>Remove all duplicates</button><div style={{ display: "grid", gap: ".5rem", marginTop: ".75rem" }}>{duplicateRows.map(row => <div key={row.id} className="lead-summary"><b>Row {row.row_number} · {row.data.name || "Unnamed lead"}</b><span>{row.duplicate_type === "CRM" ? "Already in CRM" : "Duplicate in Excel"}</span><small>{row.normalized_phone} · Matches {row.existing_name || "matching lead"}</small><button className="row-action" onClick={() => void removeDuplicates([row.id])}>Remove duplicate</button></div>)}</div></div>}
        {upload.error_message && <p className="subtext">{upload.error_message}</p>}
      </section>
    )}
    {error && <div className="empty-state">{error}</div>}
    {isAssignmentDesk && <aside className="officer-rail officer-grid"><header><p className="eyebrow">ACTIVE {targetLabel}</p><span>Select CREs for bucket assignment</span></header>{assignmentUsers.map(officer => <div className={`officer-card ${draggedOfficerId === officer.id ? "dragging" : ""} ${bucketOfficerIds.includes(officer.id) ? "selected" : ""}`} key={officer.id} draggable onClick={() => toggleBucketOfficer(officer.id)} onDragStart={event => { event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("application/incheon-officer", String(officer.id)); setDraggedOfficerId(officer.id); }} onDragEnd={() => { setDraggedOfficerId(null); setDropTargetId(null); }}><span className={`avatar ${officer.color}`}>{officer.initials}</span><span><b>{officer.name}</b><small>{targetLabel}</small></span><span className="officer-load"><small>LEAD LOAD</small><b>{officer.assigned}</b><small>CALLS TODAY</small><b>{officer.calls}</b></span></div>)}</aside>}
    {(officerMode || isAdminAllLeads) && <section className={officerMode ? "lead-layout one-column" : "lead-layout admin-lead-layout"}>
      <article className={officerMode ? "panel lead-pool" : "panel lead-pool admin-lead-pool"}><header className="panel-heading"><div><p className="eyebrow">{officerMode ? "ACTIVE LEADS" : poolLabel.toUpperCase()}</p><h2>{loading ? "Loading leads…" : `${leads.length} leads in pool`}</h2></div></header><div className="lead-list">{!loading && visible.length ? visible.map(lead => <div className={`lead-row ${dropTargetId === lead.id ? "drop-target" : ""} ${isAdminAllLeads && allLeadStatus === "reassignment" ? "reassignment-row" : ""}`} key={lead.id} onDragOver={event => { if (isAssignmentDesk) { event.preventDefault(); setDropTargetId(lead.id); } }} onDragLeave={() => setDropTargetId(null)} onDrop={event => { event.preventDefault(); const officerId = Number(event.dataTransfer.getData("application/incheon-officer")) || draggedOfficerId; if (officerId) void assign(lead, officerId); setDraggedOfficerId(null); }}>{isAssignmentDesk && <span className="drag-slot">↓</span>}{isAdminAllLeads && allLeadStatus === "reassignment" && <input type="checkbox" aria-label={`Select ${lead.name}`} checked={selectedReassignmentLeads.includes(lead.id)} onChange={() => toggleReassignmentLead(lead.id)} />}<div><b>{lead.name}</b><small>{lead.phone} · #{lead.id}</small>{allLeadStatus === "reassignment" && <span className="reassignment-badges">{lead.needsCreReassignment && <em>CRE needed</em>}{lead.needsSoReassignment && <em>PS/SO needed</em>}</span>}</div><span className={`badge ${sourceClass(lead.source)}`}>{lead.source}</span><span className="model">{lead.model}</span><span className={`status ${lead.status.toLowerCase().replaceAll(" ", "-")}`}>{lead.status}</span>{isAssignmentDesk && <select className="mobile-assign" aria-label={`Assign ${lead.name} to ${targetLabel}`} value="" onChange={event => { const officerId = Number(event.target.value); if (officerId) void assign(lead, officerId); }}><option value="">Assign to {targetLabel}…</option>{assignmentUsers.map(officer => <option key={officer.id} value={officer.id}>{officer.name}</option>)}</select>}<button className="row-action" onClick={() => openLead(lead)}>{officerMode ? "Log call →" : "Open →"}</button></div>) : !loading && <div className="empty-state">No leads match this view.</div>}</div></article>
    </section>}
    {isAdminAllLeads && <LeadPagination page={page} total={totalLeads} loading={loading} onPageChange={next => { setSelectedReassignmentLeads([]); setPage(next); }} />}
    {notice && <div className="toast" role="status">{notice}<button aria-label="Dismiss" onClick={() => setNotice("")}>×</button></div>}
    {addingLead && <div className="modal-layer" role="presentation"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="add-lead-title"><button className="modal-close" onClick={() => setAddingLead(false)} aria-label="Close">×</button><p className="eyebrow">LEAD INTAKE</p><h2 id="add-lead-title">Add a lead</h2><form className="lead-form" onSubmit={event => { event.preventDefault(); void saveLead(); }}><div className="form-grid"><label>Full name<input required maxLength={160} value={newLead.name} onChange={event => setNewLead(current => ({ ...current, name: event.target.value }))} placeholder="Customer name" /></label><label>Phone number<input required inputMode="numeric" pattern="[0-9]{10}" maxLength={10} value={newLead.phone} onChange={event => setNewLead(current => ({ ...current, phone: event.target.value.replace(/\D/g, "") }))} placeholder="10-digit mobile number" /></label><label>Email<input type="email" inputMode="email" pattern={emailPattern.source} title="Use a complete email such as name@example.com" value={newLead.email} onChange={event => setNewLead(current => ({ ...current, email: event.target.value }))} placeholder="name@example.com" /></label><label>City<input maxLength={100} value={newLead.city} onChange={event => setNewLead(current => ({ ...current, city: event.target.value }))} placeholder="City" /></label><label>Lead source<select required value={newLead.source} onChange={event => setNewLead(current => ({ ...current, source: event.target.value }))}><option value="">Select source</option>{sourceOptions.map(item => <option key={item} value={item}>{sourceName(item)}</option>)}</select></label><label>Enquiry date<DateInput required value={newLead.enquiry_date || ""} max={formatDate(new Date())} onChange={value => setNewLead(current => ({ ...current, enquiry_date: value }))} ariaLabel="Enquiry date, DD/MM/YYYY" /></label><label>Vehicle interest<select required value={newLead.model_interest || ""} onChange={event => setNewLead(current => ({ ...current, model_interest: event.target.value }))} disabled={!models.length}><option value="">{models.length ? "Select model" : "Add models in Lists first"}</option>{models.map(model => <option key={model} value={model}>{model}</option>)}</select></label><label>Color interested<select required value={newLeadColor} onChange={event => setNewLeadColor(event.target.value)} disabled={!colorVariantOptions.length}><option value="">{colorVariantOptions.length ? "Select color" : "Add color variants in Lists first"}</option>{colorVariantOptions.map(color => <option key={color} value={color}>{color}</option>)}</select></label></div><label style={{ marginTop: "13px", display: "block" }}>Source detail<input maxLength={100} value={newLead.source_label} onChange={event => setNewLead(current => ({ ...current, source_label: event.target.value }))} placeholder="Ad set, partner, referral, or other detail" /></label>{error && <p className="form-error" role="alert">{error}</p>}<p className="subtext">New leads start as Fresh and appear unassigned, ready to hand to CRE.</p><footer><button type="button" className="filter" onClick={() => setAddingLead(false)}>Cancel</button><button className="button primary" disabled={creatingLead}>{creatingLead ? "Adding…" : "Add lead"}</button></footer></form></section></div>}
    {submittedLead && <div className="modal-layer" role="presentation"><section className="modal success-modal" role="dialog" aria-modal="true" aria-labelledby="submitted-title"><button className="modal-close" onClick={() => setSubmittedLead(null)} aria-label="Close">×</button><div className="success-mark" aria-hidden="true">✓</div><p className="eyebrow">LEAD SUBMITTED</p><h2 id="submitted-title">Thank you, lead submitted.</h2><p className="subtext">{submittedLead} is now in the unassigned pool, ready for CRE assignment.</p><button className="button primary" onClick={() => setSubmittedLead(null)}>Done</button></section></div>}
    {activeLead && !officerMode && <div className="modal-layer admin-follow-up-layer" role="presentation"><section className="modal sales-detail-modal admin-follow-up-modal" role="dialog" aria-modal="true" aria-labelledby="lead-detail-title" style={{ maxWidth: "44rem" }}>
      <header className="sales-detail-header"><div><p className="eyebrow">LEAD DETAILS</p><h2 id="lead-detail-title">Lead details</h2><p className="subtext">Review customer information and update saved lead details.</p></div><div className="admin-lead-header-actions"><button type="button" className="admin-delete-lead" disabled={deletingLead} onClick={() => void removeActiveLead()}>{deletingLead ? "Deleting…" : "Delete"}</button><button className="modal-close" onClick={() => { setActiveLead(null); setLeadDetail(null); }} aria-label="Close">×</button></div></header>
      <div className="sales-detail-scroll">
        {error && <p className="form-error" role="alert">{error}</p>}
        <section className="sales-info-card admin-customer-card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3>Customer information</h3>
            {!editingCustomer && <button type="button" className="filter" onClick={startEditing} style={{ padding: "0.25rem 0.75rem", fontSize: "0.875rem" }}>Edit details</button>}
          </div>
          {editingCustomer ? (
            <div className="form-grid" style={{ marginTop: "1rem" }}>
              <label>Customer name<input value={editDetails.name} onChange={e => setEditDetails({ ...editDetails, name: e.target.value })} maxLength={160} /></label>
              <label>Mobile<input value={editDetails.phone} onChange={e => setEditDetails({ ...editDetails, phone: e.target.value.replace(/\D/g, "") })} maxLength={10} /></label>
              <label>Model<select value={editDetails.model} onChange={e => setEditDetails({ ...editDetails, model: e.target.value })} disabled={!models.length && !editDetails.model}><option value="">{models.length ? "Select model" : "Add models in Lists first"}</option>{optionsWithCurrent(models, editDetails.model).map(model => <option key={model} value={model}>{model}</option>)}</select></label>
              <label>Color variant<select value={editDetails.variant} onChange={e => setEditDetails({ ...editDetails, variant: e.target.value })} disabled={!colorVariantOptions.length && !editDetails.variant}><option value="">{colorVariantOptions.length ? "Select color variant" : "Add color variants in Lists first"}</option>{optionsWithCurrent(colorVariantOptions, editDetails.variant).map(option => <option key={option} value={option}>{option}</option>)}</select></label>
              <label>Trade-in<select value={editDetails.trade_in === true ? "true" : editDetails.trade_in === false ? "false" : ""} onChange={e => setEditDetails({ ...editDetails, trade_in: e.target.value === "true" ? true : e.target.value === "false" ? false : null })}><option value="">—</option><option value="true">Yes</option><option value="false">No</option></select></label>
              <label>Category<select value={editDetails.category} onChange={e => setEditDetails({ ...editDetails, category: e.target.value })}><option value="HOT">Hot</option><option value="WARM">Warm</option><option value="COLD">Cold</option></select></label>
              <div style={{ gridColumn: "1 / -1", display: "flex", gap: "0.5rem", marginTop: "0.5rem" }}><button type="button" className="filter" onClick={() => setEditingCustomer(false)}>Cancel</button><button type="button" className="button primary" disabled={savingDetails} onClick={() => void saveCustomerDetails()}>{savingDetails ? "Saving…" : "Save details"}</button></div>
            </div>
          ) : (
            <>
              <div className="sales-info-grid" style={{ marginTop: "1rem" }}>
                <span><small>Customer name</small><b>{activeLead.name}</b></span>
                <span><small>Mobile</small><b>{activeLead.phone}</b></span>
                <span><small>Model</small><b>{activeLead.model}</b></span>
                <span><small>Color variant</small><b>{leadDetail?.qualification?.variant || "—"}</b></span>
                <span><small>Buying plan</small><b>{leadDetail?.qualification?.buying_timeline || "—"}</b></span>
                <span><small>Finance</small><b>{leadDetail?.qualification?.finance_type || "—"}</b></span>
                {isAdminAllLeads && (activeLead.assignedSoId ? <div className="admin-manual-assign"><span>Manual CRE assignment</span><b>Lead has already been assigned to {activeLead.assignedSoName || "CRE"}</b></div> : <label className="admin-manual-assign">Manual CRE assignment<select value="" disabled={manualAssigning} onChange={event => { const officerId = Number(event.target.value); if (officerId) void manualAssignCre(officerId); }}><option value="">{manualAssigning ? "Assigning…" : "Assign to CRE…"}</option>{creUsers.map(officer => <option key={officer.id} value={officer.id}>{officer.name}</option>)}</select></label>)}
              </div>
              <div className="sales-detail-meta"><span>Trade-in <b>{leadDetail?.qualification?.trade_in === true ? "Yes" : leadDetail?.qualification?.trade_in === false ? "No" : "—"}</b></span><span>Category <b className={`category-pill ${activeLead.category?.toLowerCase() || "warm"}`}>{activeLead.category || "WARM"}</b></span></div>
            </>
          )}

        </section>
        {leadDetail?.followUpHistory.some(item => item.reminder_held && !item.resolved_at) && <section className="sales-form-card held-followup-review">
          <header><div><p className="eyebrow">ADMIN REVIEW REQUIRED</p><h3>Held follow-up reminders</h3></div><span>{leadDetail.followUpHistory.filter(item => item.reminder_held && !item.resolved_at).length}</span></header>
          <p>These schedules were preserved during an employee handoff. Review each one before a reminder is sent.</p>
          <div className="held-followup-list">{leadDetail.followUpHistory.filter(item => item.reminder_held && !item.resolved_at).map(item => <article key={item.id}><div><b>{item.so_name || "Awaiting owner"}</b><small>{item.so_active ? `Originally scheduled ${formatDateTime(item.scheduled_for)}` : "Assign an active owner or resolve this follow-up"}</small></div><input type="datetime-local" aria-label={`Schedule for follow-up ${item.id}`} value={followupDrafts[item.id] || dateTimeInputValue(item.scheduled_for)} onChange={event => setFollowupDrafts(current => ({ ...current, [item.id]: event.target.value }))} /><div><button className="filter" disabled={reviewingFollowup === item.id} onClick={() => void reviewHeldFollowup(item.id, "RESOLVE", item.scheduled_for)}>Resolve</button><button className="button primary" disabled={reviewingFollowup === item.id || !item.so_active} onClick={() => void reviewHeldFollowup(item.id, "APPROVE", item.scheduled_for)}>{reviewingFollowup === item.id ? "Saving…" : "Approve reminder"}</button></div></article>)}</div>
        </section>}
        {(detailLoading || leadDetail?.callHistory.length) ? <section className="sales-form-card admin-call-history">
          <h3>Sales call history</h3>
          {detailLoading ? <p className="subtext">Loading call history…</p> : <div className="admin-history-list">{leadDetail?.callHistory.map((call, index) => <div className="sales-history-row" key={`call-${call.id}`}><div><b>Call #{leadDetail.callHistory.length - index} · {call.so_name || "Admin"}</b><small>{call.remarks || "No remarks"}</small><div style={{ display: "flex", gap: "0.25rem", flexWrap: "wrap", marginTop: "0.25rem" }}>{call.call_status && <span className="admin-history-outcome" style={{ background: "#e2e8f0", color: "#1e293b" }}>{call.call_status}</span>}{call.outcome && <span className="admin-history-outcome">{call.outcome}</span>}</div></div><time>{formatCallDate(call.created_at)}</time></div>)}</div>}
        </section> : null}
      </div>
      <footer className="sales-detail-footer"><button className="filter" onClick={() => { setActiveLead(null); setLeadDetail(null); }}>Close</button></footer>
    </section></div>}
    {activeLead && officerMode && <div className="modal-layer" role="presentation"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="call-title-so"><button className="modal-close" onClick={() => setActiveLead(null)} aria-label="Close">×</button><p className="eyebrow">CALL LOG</p><h2 id="call-title-so">Update {activeLead.name}</h2><div className="lead-summary"><b>#{activeLead.id} · {activeLead.model}</b><span>{activeLead.source} lead</span><small>{activeLead.phone} · {activeLead.city || "—"}</small></div>{nextOutcomes[activeLead.status]?.length ? <><div className="form-grid"><label>Next outcome<select value={outcome} onChange={event => { setOutcome(event.target.value); if (!["CALLBACK", "WALKIN"].includes(event.target.value)) setFollowUpAt(""); }}>{nextOutcomes[activeLead.status].map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>{needsAppointment && <label>{outcome === "WALKIN" ? "Walk-in appointment" : "Follow-up time"}<select required value={followUpAt} onChange={event => setFollowUpAt(event.target.value)}><option value="">Select time</option>{followUpOptions().map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}</select></label>}</div><label>Remarks<textarea maxLength={500} value={remarks} onChange={event => setRemarks(event.target.value)} placeholder="Add a clear note from the conversation" /></label><footer><button className="filter" onClick={() => setActiveLead(null)}>Cancel</button><button className="button primary" disabled={savingCall || (needsAppointment && !followUpAt) || !outcome} onClick={() => void saveCall()}>{savingCall ? "Saving…" : "Save call log"}</button></footer></> : <p className="subtext">This lead is closed. Reopen it before recording another outcome.</p>}</section></div>}
  </section>;
}
