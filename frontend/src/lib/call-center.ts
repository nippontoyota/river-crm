import { api, toLeadDetail, type LeadDetail, type OwnerContact, type ComplaintDetail } from "./crm";
import type { Page, ServiceRequest, Vehicle } from "./service";

export type Interaction = {
  id: number; kind: string; state: string; lead_id: number | null; customer: string; caller_name: string; caller_phone: string;
  reason: string; notes: string; handled_by: number; handled_by_name: string; callback_at: string | null;
  follow_up_id: number | null; complaint_id: number | null; service_request_id: number | null;
  created_at: string; updated_at: string; review_of: number | null;
};
export type CallbackTask = {
  id: number; lead_id: number; lead_version: string; customer: string; phone: string; owner_id: number; owner_name: string;
  scheduled_for: string; resolved_at: string | null; reminder_held: boolean; origin: string; version: string; notes?: string[];
};
export type SharedDetail = LeadDetail & {
  updated_at: string; callback_destination: { role: string; owner: OwnerContact | null; available: boolean };
  interactions: Interaction[]; callbacks: CallbackTask[]; vehicles: Vehicle[];
};
type RawSharedDetail = Parameters<typeof toLeadDetail>[0] & Pick<SharedDetail, "updated_at" | "callback_destination" | "interactions" | "callbacks" | "vehicles">;
const mapDetail = (raw: RawSharedDetail): SharedDetail => ({ ...toLeadDetail(raw), updated_at: raw.updated_at, callback_destination: raw.callback_destination, interactions: raw.interactions, callbacks: raw.callbacks, vehicles: raw.vehicles });
export const getSharedLead = async (id: number) => mapDetail(await api<RawSharedDetail>(`/api/call-center/leads/${id}/`, { cache: "no-store" }));
export const updateSharedLead = async (id: number, payload: Record<string, unknown>) => mapDetail(await api<RawSharedDetail>(`/api/call-center/leads/${id}/`, { method: "PATCH", body: JSON.stringify(payload) }));
export const recordInteraction = (payload: Record<string, unknown>, callbackOnly = false) => api<Interaction>(`/api/call-center/${callbackOnly ? "callbacks" : "interactions"}/`, { method: "POST", body: JSON.stringify(payload) });
export const getInteractions = (query = "") => api<Page<Interaction>>(`/api/call-center/interactions/${query}`, { cache: "no-store" });
export const getCallbacks = (page = 1) => api<Page<CallbackTask>>(`/api/call-center/callbacks/?page=${page}`, { cache: "no-store" });
export const getCallSummary = () => api<{ inbound_calls_today: number; by_handler: { handled_by: number; handled_by__first_name: string; handled_by__last_name: string; handled_by__email: string; count: number }[] }>("/api/call-center/summary/", { cache: "no-store" });
export type SharedComplaint = ComplaintDetail & { confirmed_link: boolean };
export type SharedService = ServiceRequest & { confirmed_link: boolean };
export const getSharedTickets = <T extends SharedComplaint | SharedService>(id: number, kind: "complaint" | "service", page = 1, ticketId?: number) => api<Page<T>>(`/api/call-center/leads/${id}/tickets/?kind=${kind}&page=${page}${ticketId ? `&ticket_id=${ticketId}` : ""}`, { cache: "no-store" });
export const kindName = (kind: string) => ({ NOTE: "Inbound call", CALLBACK: "Callback requested", COMPLAINT: "Complaint", SERVICE: "Service request", COMPLAINT_NOTE: "Complaint update", SERVICE_NOTE: "Service update", LEAD_UPDATE: "Lead updated", CALLBACK_COMPLETE: "Callback completed", CALLBACK_RESCHEDULE: "Callback rescheduled", REVIEW: "Admin review" }[kind] || kind);
export const stateName = (state: string) => ({ RECORDED: "Recorded", UNMATCHED: "Unmatched customer", AWAITING_ROUTING: "Awaiting routing", RESOLVED: "Reviewed" }[state] || state);
