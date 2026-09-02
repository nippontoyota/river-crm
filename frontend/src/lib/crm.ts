const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
import { formatDate, toApiDate, toDateInputValue } from "@/lib/dates";

type Paginated<T> = { count?: number; next?: string | null; previous?: string | null; results: T[] };
type ApiLead = {
  id: number; name: string; phone: string; email: string; source: string; source_label: string; campaign: string; model_interest: string; city: string;
  branch: string; enquiry_date: string | null; status: string; category: string; sales_outcome: string; assigned_so: number | null; assigned_so_name: string; assigned_ps: number | null; assigned_ps_name: string; next_follow_up: string | null; call_count: number; qualification: LeadQualification | null; created_at: string;
};
type ApiSalesLead = { id: number; status: string; name: string; phone: string; source: string; flagged_to_manager: boolean };
type ApiOfficer = { id: number; first_name: string; last_name: string; email: string; phone: string; location: string; is_active: boolean };

export type Lead = {
  id: number; name: string; phone: string; source: string; sourceCode: string; model: string; city: string; enquiryDate: string | null; enquiredAt: string;
  branch: string; campaign: string; category: string; salesOutcome: string; nextFollowUp: string | null; callCount: number; statusCode: string; status: string; assignedSoId: number | null; assignedSoName: string; assignedPsId: number | null; assignedPsName: string;
};
export type SalesLead = { id: number; status: string; statusCode: string; name: string; phone: string; source: string; sourceCode: string; flagged_to_manager: boolean };
export type LeadInput = { name: string; phone: string; email?: string; source: string; source_label?: string; campaign?: string; model_interest?: string; city?: string; branch?: string; enquiry_date?: string; profession?: string; ps_officer_id?: number; status?: string; category?: string; qualification?: LeadQualification; qualification_input?: LeadQualification };
export type LeadFilters = { source?: string; status?: string; model?: string; city?: string; source_label?: string; date_from?: string; date_to?: string; q?: string };
export type LeadQualification = { variant: string; buying_timeline: string; finance_type: string; trade_in: boolean | null; test_drive: string; notes: string; updated_at?: string };
export type CallHistory = { id: number; status: string; outcome: string; remarks: string; so_name: string; created_at: string; call_status?: string };
export type FollowUpHistory = { id: number; lead: number; customer: string; scheduled_for: string; resolved_at: string | null; notified_at: string | null };
export type LeadDetail = Lead & { email: string; sourceLabel: string; campaign: string; qualification: LeadQualification | null; callHistory: CallHistory[]; followUpHistory: FollowUpHistory[]; auditHistory: { event: string; before: Record<string, unknown>; after: Record<string, unknown>; actor: string; created_at: string }[] };
export type SalesDashboard = { summary: { total: number; fresh: number; followups: number; pending: number; qualified: number; walkin: number; won: number; lost: number; won_lost: number; untouched: number; called: number; scheduled: number }; section: string; results: SalesLead[] };
export type PersonalAnalytics = { range: string; summary: { total: number; assigned: number; qualified: number; booked: number; lost: number; retailed: number; conversion_rate: number }; status_counts: { status: string; count: number }[]; source: { source: string; total: number; qualified: number; booked: number; retailed: number }[]; models: { model_interest: string; total: number; qualified: number; booked: number }[]; monthly: { month: string; total: number; qualified: number; booked: number; retailed: number }[] };
export type Officer = { id: number; name: string; initials: string; color: "blue" | "green" | "violet" | "orange"; location: string; assigned: number; calls: number; qualified: number; won: number };
export type Metrics = { total_assigned: number; total_called: number; calls_today?: number; qualified: number; walkins: number; won: number; lost: number; conversion_rate: number };
export type Analytics = { summary: Metrics; source: { source: string; total: number; qualified: number; won: number }[]; cre: (Metrics & { id: number; name: string })[]; officers: (Metrics & { id: number; name: string })[] };
export type CurrentUser = { id: number; first_name: string; last_name: string; email: string; role: "ADMIN" | "CRE" | "SO" | "SALES_MANAGER" | "RECEPTIONIST" | "COMPLAINTS"; is_active?: boolean; location?: string };
type ApiOptions = RequestInit & { skipCsrf?: boolean };

let csrfToken = "";
const currentUserCacheKey = "incheon.currentUser";
let currentUserRequest: Promise<{ user: CurrentUser }> | null = null;
let systemConfigRequest: Promise<SystemConfig> | null = null;
let systemConfigCache: SystemConfig | null = null;

export function cacheCurrentUser(user: CurrentUser) {
  if (typeof window !== "undefined") sessionStorage.setItem(currentUserCacheKey, JSON.stringify(user));
}

export function getCachedCurrentUser() {
  if (typeof window === "undefined") return null;
  try { return JSON.parse(sessionStorage.getItem(currentUserCacheKey) || "null") as CurrentUser | null; }
  catch { return null; }
}

export function clearCachedCurrentUser() {
  if (typeof window !== "undefined") sessionStorage.removeItem(currentUserCacheKey);
}

function responseError(body: unknown, fallback: string) {
  if (!body || typeof body !== "object") return fallback;
  if (typeof (body as { detail?: unknown }).detail === "string") return (body as { detail: string }).detail;
  const messages = Object.entries(body as Record<string, unknown>).flatMap(([field, value]) => {
    const label = field === "non_field_errors" ? "" : `${field}: `;
    return (Array.isArray(value) ? value : [value]).map(message => `${label}${String(message)}`);
  });
  return messages.join(" ") || fallback;
}

async function csrf() {
  if (csrfToken) return csrfToken;
  const response = await fetch(`${API_URL}/api/auth/csrf/`, { credentials: "include" });
  const body = await response.json().catch(() => ({})) as { csrfToken?: string };
  if (!response.ok || !body.csrfToken) throw new Error(responseError(body, `Unable to initialize security (${response.status}).`));
  csrfToken = body.csrfToken;
  return csrfToken;
}

export async function api<T>(path: string, options: ApiOptions = {}, didRefresh = false): Promise<T> {
  const method = options.method?.toUpperCase() || "GET";
  const headers = new Headers(options.headers);
  const { skipCsrf, ...fetchOptions } = options;
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (!skipCsrf && !["GET", "HEAD", "OPTIONS"].includes(method)) headers.set("X-CSRFToken", await csrf());
  const response = await fetch(`${API_URL}${path}`, { ...fetchOptions, headers, credentials: "include" });
  if (!response.ok) {
    if (response.status === 401 && !didRefresh && await refreshSession()) return api<T>(path, options, true);
    const body = await response.json().catch(() => ({}));
    throw new Error(responseError(body, `The request could not be completed (${response.status}).`));
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

async function refreshSession() {
  const headers = new Headers();
  if (csrfToken) headers.set("X-CSRFToken", csrfToken);
  const response = await fetch(`${API_URL}/api/auth/refresh/`, { method: "POST", headers, credentials: "include" });
  return response.ok;
}

async function download(path: string, filename: string) {
  const fetchFile = () => fetch(`${API_URL}${path}`, { credentials: "include" });
  let response = await fetchFile();
  if (response.status === 401 && await refreshSession()) response = await fetchFile();
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(responseError(body, `Download failed (${response.status}).`));
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

const sourceNames: Record<string, string> = { META: "Meta Ads", WEBSITE: "Website", CARWALE: "CarWale", WALKIN: "Walk-in", CAMPAIGN: "Campaign", OTHER: "Other", UNKNOWN: "Unknown" };
const statusNames: Record<string, string> = { FRESH: "Fresh", RNR: "RNR", SWITCHED_OFF: "Switch off", CALLBACK: "Callback", PENDING: "Pending", QUALIFIED: "Qualified", UNQUALIFIED: "Unqualified", WALKIN: "Walk-in", WON: "Won", LOST: "Lost" };
const colors: Officer["color"][] = ["blue", "green", "violet", "orange"];

export const sourceName = (source: string) => sourceNames[source] || source;
export const statusName = (status: string) => statusNames[status] || status;
export const sourceClass = (source: string) => sourceName(source).toLowerCase().replaceAll(" ", "-");
export const toLead = (lead: ApiLead): Lead => ({ ...lead, source: sourceName(lead.source), sourceCode: lead.source, model: lead.model_interest || "—", enquiryDate: lead.enquiry_date, enquiredAt: formatDate(lead.enquiry_date || lead.created_at), statusCode: lead.status, status: statusName(lead.status), category: lead.category, salesOutcome: lead.sales_outcome, nextFollowUp: lead.next_follow_up, callCount: lead.call_count, assignedSoId: lead.assigned_so, assignedSoName: lead.assigned_so_name, assignedPsId: lead.assigned_ps, assignedPsName: lead.assigned_ps_name });
const toSalesLead = (lead: ApiSalesLead): SalesLead => ({ id: lead.id, name: lead.name, phone: lead.phone, source: sourceName(lead.source), sourceCode: lead.source, statusCode: lead.status, status: statusName(lead.status), flagged_to_manager: lead.flagged_to_manager });
const toLeadDetail = (lead: ApiLead & { call_history: CallHistory[]; follow_up_history: FollowUpHistory[]; audit_history: LeadDetail["auditHistory"] }): LeadDetail => ({ ...toLead(lead), email: lead.email, sourceLabel: lead.source_label, campaign: lead.campaign, qualification: lead.qualification, callHistory: lead.call_history, followUpHistory: lead.follow_up_history, auditHistory: lead.audit_history });
export const toOfficer = (officer: ApiOfficer, metrics?: Metrics): Officer => ({ id: officer.id, name: `${officer.first_name} ${officer.last_name}`.trim() || officer.email, initials: `${officer.first_name[0] || ""}${officer.last_name[0] || ""}` || officer.email.slice(0, 2).toUpperCase(), color: colors[officer.id % colors.length], location: officer.location, assigned: metrics?.total_assigned || 0, calls: metrics?.calls_today || 0, qualified: metrics?.qualified || 0, won: metrics?.won || 0 });

export async function getLeadsPage(query = "") { const data = await api<Paginated<ApiLead>>(`/api/leads/${query}`); return { count: data.count ?? data.results.length, next: data.next ?? null, previous: data.previous ?? null, results: data.results.map(toLead) }; }
export async function getLeads(query = "") { return (await getLeadsPage(query)).results; }
export async function getMyDashboard(params: Record<string, string>) { const query = new URLSearchParams(params).toString(); const data = await api<{ summary: SalesDashboard["summary"]; section: string; results: ApiSalesLead[] }>(`/api/leads/my-dashboard/${query ? `?${query}` : ""}`); return { ...data, results: data.results.map(toSalesLead) }; }
export async function getLeadDetail(id: number) { const data = await api<ApiLead & { call_history: CallHistory[]; follow_up_history: FollowUpHistory[]; audit_history: LeadDetail["auditHistory"] }>(`/api/leads/${id}/`); return toLeadDetail(data); }
const withApiDate = <T extends { enquiry_date?: string | null }>(payload: T): T => payload.enquiry_date === undefined ? payload : { ...payload, enquiry_date: toApiDate(payload.enquiry_date) };
export async function updateMyLead(id: number, payload: { name?: string; phone?: string; email?: string; source?: string; source_label?: string; campaign?: string; model_interest?: string; city?: string; branch?: string; enquiry_date?: string | null; status?: string; category?: string; sales_outcome?: string; remarks?: string; call_status?: string; call_outcome?: string; follow_up_at?: string | null; ps_officer_id?: number; qualification?: LeadQualification; flagged_to_manager?: boolean }) { const data = await api<ApiLead & { call_history: CallHistory[]; follow_up_history: FollowUpHistory[]; audit_history: LeadDetail["auditHistory"] }>(`/api/leads/${id}/so-update/`, { method: "PATCH", body: JSON.stringify(withApiDate(payload)) }); return toLeadDetail(data); }
export const createLead = (payload: LeadInput) => api<ApiLead>("/api/leads/", { method: "POST", body: JSON.stringify(withApiDate(payload)) });
export async function getCres() { const data = await api<Paginated<ApiOfficer>>("/api/auth/cre-users/"); return data.results; }
export async function getOfficers(location = "") { const query = location ? `?${new URLSearchParams({ location }).toString()}` : ""; const data = await api<Paginated<ApiOfficer>>(`/api/auth/sales-officers/${query}`); return data.results; }
export const getAdminAnalytics = () => api<Analytics>("/api/analytics/admin/");
export const getMyAnalytics = () => api<Metrics>("/api/analytics/me/");
export async function getMyAnalyticsDashboard(range = "mtd", dateFrom = "", dateTo = "") { const from = toDateInputValue(dateFrom); const to = toDateInputValue(dateTo); const query = new URLSearchParams({ range, ...(from ? { date_from: from } : {}), ...(to ? { date_to: to } : {}) }).toString(); return api<PersonalAnalytics>(`/api/analytics/me/?${query}`); }
export const exportMyAnalytics = () => download("/api/analytics/me/export/", "incheon-my-analytics.csv");
export type ManagerSummary = { total: number; untouched: number; contacted: number; open: number; qualified: number; walkin: number; booked: number; retailed: number; lost: number; flagged: number; lead_to_qualified_rate: number; lead_to_retail_rate: number; qualified_to_booked_rate: number; booked_to_retail_rate: number; followups_due: number; stale_untouched: number; delta: Record<string, number> };
export type ManagerRoleRow = { id: number; name: string; email: string; location: string; total: number; untouched: number; qualified: number; booked: number; retailed: number; lost: number; calls: number; followups: number; last_activity: string | null; conversion_rate: number; qualification_rate: number };
export type ManagerPerformanceRow = { total: number; qualified: number; booked: number; retailed: number; lost: number; conversion_rate: number };
export type ManagerPSFollowupRow = { id: number; name: string; email: string; total_leads: number; test_drive: number; unattended: number; f1: number; f2: number; f3: number; f4: number; f5: number };
export type ManagerPSFollowupLead = { id: number; name: string; phone: string; source: string; created_at: string; model: string; test_drive: string; status: string };
export type ManagerPSFollowups = { rows: ManagerPSFollowupRow[]; leads: ManagerPSFollowupLead[] };
export type ManagerFilterOption = { id: number; name: string };
export type ManagerAnalytics = { range: string; date_from: string | null; date_to: string | null; branch: string; summary: ManagerSummary; funnel: { key: string; label: string; count: number; rate: number }[]; cre: ManagerRoleRow[]; ps: ManagerRoleRow[]; source: ({ source: string } & ManagerPerformanceRow)[]; models: ({ model: string } & ManagerPerformanceRow)[]; status: { status: string; count: number }[]; categories: { category: string; count: number }[]; monthly: { month: string | null; total: number; qualified: number; booked: number; retailed: number }[]; followups: { due: number; overdue: number; by_owner: { so__id: number; so__first_name: string; so__last_name: string; so__email: string; count: number }[] }; lost_reasons: { outcome: string; count: number }[]; stale_leads: { id: number; name: string; phone: string; source: string; model_interest: string; created_at: string }[]; filters?: { source: string[]; models: string[]; cre: ManagerFilterOption[]; ps: ManagerFilterOption[] }; generated_at: string };
const managerParams = ({ date_from, date_to, ...params }: Record<string, string>) => ({ ...params, ...(toDateInputValue(date_from) ? { date_from: toDateInputValue(date_from) } : {}), ...(toDateInputValue(date_to) ? { date_to: toDateInputValue(date_to) } : {}) });
export async function getSalesManagerAnalytics(params: Record<string, string>) { const query = new URLSearchParams(managerParams(params)).toString(); return api<ManagerAnalytics>(`/api/analytics/sales-manager/${query ? `?${query}` : ""}`); }
export async function getSalesManagerPSFollowups(params: Record<string, string>) { const query = new URLSearchParams(managerParams(params)).toString(); return api<ManagerPSFollowups>(`/api/analytics/sales-manager/ps-followups/${query ? `?${query}` : ""}`); }
export function exportSalesManagerAnalytics(section: string, params: Record<string, string>) { const query = new URLSearchParams({ ...managerParams(params), section }).toString(); return download(`/api/analytics/sales-manager/export/?${query}`, `incheon-sales-manager-${section}.csv`); }
export async function getManagerLeads(query = "") { return getLeadsPage(`manager-leads/${query.startsWith("?") ? query : query ? `?${query}` : ""}`); }
export const assignLead = (leadId: number, officerId: number) => api<Lead>(`/api/leads/${leadId}/assign/`, { method: "POST", body: JSON.stringify({ sales_officer_id: officerId }) });
export const assignPsLead = (leadId: number, officerId: number) => api<Lead>(`/api/leads/${leadId}/assign-ps/`, { method: "POST", body: JSON.stringify({ sales_officer_id: officerId }) });
const withApiDateFilters = (filters: LeadFilters): LeadFilters => ({ ...filters, date_from: toDateInputValue(filters.date_from) || undefined, date_to: toDateInputValue(filters.date_to) || undefined });
export const assignFilteredLeads = (officerId: number, filters: LeadFilters) => api<{ assigned: number }>("/api/leads/bulk-assign/", { method: "POST", body: JSON.stringify({ sales_officer_id: officerId, filters: withApiDateFilters(filters) }) });
export const assignFilteredPsLeads = (officerId: number, filters: LeadFilters) => api<{ assigned: number }>("/api/leads/bulk-assign-ps/", { method: "POST", body: JSON.stringify({ sales_officer_id: officerId, filters: withApiDateFilters(filters) }) });
export const distributeFilteredLeads = (officerIds: number[], filters: LeadFilters) => api<{ assigned: number; distribution: { sales_officer_id: number; name: string; assigned: number }[] }>("/api/leads/bulk-distribute/", { method: "POST", body: JSON.stringify({ sales_officer_ids: officerIds, filters: withApiDateFilters(filters) }) });
export const autoAssignLeads = () => api<{ assigned: number }>("/api/leads/auto-assign/", { method: "POST", body: JSON.stringify({}) });
export const logCall = (leadId: number, payload: { status: string; remarks?: string; follow_up_at?: string }) => api<Lead>(`/api/leads/${leadId}/log-call/`, { method: "POST", body: JSON.stringify(payload) });
export const login = (email: string, password: string) => api<{ user: CurrentUser }>("/api/auth/login/", { method: "POST", body: JSON.stringify({ email, password }), skipCsrf: true });
export const logout = () => api<void>("/api/auth/logout/", { method: "POST" });
export function getCurrentUser() {
  if (!currentUserRequest) currentUserRequest = api<{ user: CurrentUser }>("/api/auth/me/").finally(() => { currentUserRequest = null; });
  return currentUserRequest;
}
export const uploadLeads = (file: File) => { const body = new FormData(); body.append("file", file); return api<UploadBatch>("/api/uploads/", { method: "POST", body }); };
export const getUpload = (id: number, includeRows = false) => api<UploadBatch>(`/api/uploads/${id}/${includeRows ? "?include_rows=true" : ""}`);
export const resolveUploadDuplicates = (id: number, rows: { id: number; resolution: "SKIP" }[]) => api<{ detail: string; duplicates_found: number }>(`/api/uploads/${id}/resolve-duplicates/`, { method: "POST", body: JSON.stringify({ rows }) });
export const commitUpload = (id: number) => api<{ created: number; overwritten: number; skipped: number }>(`/api/uploads/${id}/commit/`, { method: "POST", body: JSON.stringify({}) });
export type UploadRow = { id: number; row_number: number; data: { name?: string }; normalized_phone: string; validation_error: string; duplicate_of: number | null; existing_name: string; existing_status: string; duplicate_type: "CRM" | "FILE" | ""; resolution: "PENDING" | "SKIP" | "OVERWRITE" | "IMPORT" };
export type UploadBatch = { id: number; status: "PARSING" | "READY" | "COMMITTED" | "FAILED"; total_rows: number; parsed_ok: number; duplicates_found: number; crm_duplicates_found: number; file_duplicates_found: number; removed_duplicates: number; pending_duplicates: number; skipped: number; error_message: string; rows?: UploadRow[] };

export type SystemConfig = { lists: { branches?: string[]; sources?: string[]; activities?: string[]; models?: string[]; colorVariants?: string[] }; updated_at?: string };
export function getSystemConfig() {
  if (systemConfigCache) return Promise.resolve(systemConfigCache);
  if (!systemConfigRequest) systemConfigRequest = api<SystemConfig>("/api/system-config/").then(config => systemConfigCache = config).finally(() => { systemConfigRequest = null; });
  return systemConfigRequest;
}
export async function updateSystemConfig(lists: SystemConfig["lists"]) {
  const config = await api<SystemConfig>("/api/system-config/", { method: "PUT", body: JSON.stringify({ lists }) });
  systemConfigCache = config;
  return config;
}
export const getUsers = async () => { const data = await api<any>("/api/auth/users/"); return (data.results || data) as CurrentUser[]; };
export const createUser = (payload: any) => api<CurrentUser>("/api/auth/users/", { method: "POST", body: JSON.stringify(payload) });
export const disableUser = (userId: number) => api<void>(`/api/auth/users/${userId}/`, { method: "DELETE" });

export type ReceptionistAnalytics = { summary: { total: number; walkin: number; digital: number }; so_breakdown: { name: string; count: number }[] };
export const getReceptionistAnalytics = () => api<ReceptionistAnalytics>("/api/analytics/receptionist/");

// ── Complaints ────────────────────────────────────────────────────────────────
export type Complaint = {
  id: number; uid: string; ticket_number: string;
  customer_name: string; customer_phone: string; customer_email: string;
  category: string; priority: string; status: string;
  subject: string; description: string; model_interest: string; branch: string; source: string;
  resolution_notes: string; resolved_at: string | null;
  logged_by: number; logged_by_name: string;
  assigned_to: number | null; assigned_to_name: string;
  note_count: number; created_at: string; updated_at: string;
};
export type ComplaintDetail = Complaint & {
  notes: ComplaintNote[];
};
export type ComplaintNote = { id: number; author_name: string; content: string; created_at: string };
export type ComplaintInput = {
  customer_name: string; customer_phone: string; customer_email?: string;
  category: string; priority: string; subject: string; description: string;
  model_interest?: string; branch: string; source?: string;
};
export type ComplaintFilters = {
  status?: string; category?: string; priority?: string; source?: string;
  date_from?: string; date_to?: string; q?: string;
};
export type ComplaintAnalytics = {
  summary: { total: number; open: number; in_progress: number; escalated: number; resolved: number; closed: number; avg_resolution_hours: number };
  by_category: { category: string; count: number }[];
  by_priority: { priority: string; count: number }[];
  by_status: { status: string; count: number }[];
  trend: { date: string; opened: number; resolved: number }[];
  by_resolution_team?: { id: number; name: string; total: number; open: number; in_progress: number; escalated: number; resolved: number; closed: number; resolution_rate: number; avg_resolution_hours: number }[];
};

export async function getComplaints(query = "") {
  const data = await api<{ count?: number; results: Complaint[] }>(`/api/complaints/${query}`);
  return { count: data.count ?? data.results.length, results: data.results };
}
export const createComplaint = (payload: ComplaintInput) =>
  api<Complaint>("/api/complaints/", { method: "POST", body: JSON.stringify(payload) });
export const getComplaintDetail = (id: number) =>
  api<ComplaintDetail>(`/api/complaints/${id}/`);
export const updateComplaint = (id: number, payload: Partial<{ status: string; priority: string; resolution_notes: string }>) =>
  api<ComplaintDetail>(`/api/complaints/${id}/`, { method: "PATCH", body: JSON.stringify(payload) });
export const addComplaintNote = (id: number, content: string) =>
  api<ComplaintNote>(`/api/complaints/${id}/add-note/`, { method: "POST", body: JSON.stringify({ content }) });
export const getComplaintAnalytics = (range = "mtd", dateFrom = "", dateTo = "") => {
  const from = toDateInputValue(dateFrom);
  const to = toDateInputValue(dateTo);
  const params = new URLSearchParams({ range, ...(from ? { date_from: from } : {}), ...(to ? { date_to: to } : {}) });
  return api<ComplaintAnalytics>(`/api/complaints/analytics/?${params.toString()}`);
};
