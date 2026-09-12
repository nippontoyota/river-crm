import { api, download } from "@/lib/crm";

export type Cell = string | number | boolean | null | undefined;
export type ReportRow = Record<string, unknown>;
export type PageData = { count: number; next: string | null; previous: string | null; results: ReportRow[]; summary?: Record<string, unknown> };
export type Target = { available: boolean; values?: Record<string, number | string | null>; allocated?: Record<string, number | string | null>; allocation_gap?: Record<string, number | string>; missing_branches?: string[]; reason?: string };
export type Overview = { generated_at: string; mode: string; etbr: Record<string, number>; conversions: Record<string, number | null>; current: Record<string, number>; activity: Record<string, number | null>; complaints: Record<string, unknown>; coverage: Record<string, number>; targets: Target; branches: ReportRow[]; trend?: ReportRow[]; trend_interval?: string; previous_etbr?: Record<string, number> | null; ageing?: Record<string, number> };
export type ReportOptions = { branches: { value: string; label: string }[]; employees: { id: number; name: string; role: string; branch: string; lifecycle: string }[]; roles: { value: string; label: string }[]; rtos: { value: string; label: string }[]; statuses: { value: string; label: string }[]; source: string[]; campaign: string[]; model_interest: string[]; activities: string[]; sub_activities: Record<string, string[]> };
export type HistoryEvent = { id: number; kind: string; occurred_at: string; actor: string | null; actor_role: string | null; branch: string; before: Record<string, unknown>; after: Record<string, unknown>; provenance: string; lead_id: number | null; complaint_id: number | null };
export type HistoryPage = Omit<PageData, "results"> & { results: HistoryEvent[] };
export const object = (value: unknown): ReportRow => value && typeof value === "object" && !Array.isArray(value) ? value as ReportRow : {};
export const text = (value: unknown, fallback = "—") => value === null || value === undefined || value === "" ? fallback : String(value);
export const numeric = (value: unknown) => Number(value) || 0;
export const count = (value: unknown) => value === undefined || value === null ? "—" : new Intl.NumberFormat("en-IN").format(Number(value));
export const money = (value: unknown) => value === undefined || value === null ? "Not recorded" : new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value));
export const labels: Record<string, string> = { E: "Enquiries", T: "Test drives", B: "Bookings", R: "Retail", CRE: "CE", SO: "PS/SO", RECEPTIONIST: "Receptionist", SALES_MANAGER: "Sales manager", COMPLAINTS: "Complaints", FRESH: "Fresh", QUALIFIED: "Qualified", PENDING: "Pending", RNR: "RNR", SWITCHED_OFF: "Switched off", CALLBACK: "Callback", WALKIN: "Booked", WON: "Retailed", LOST: "Lost", UNQUALIFIED: "Unqualified", BOOKED: "Booked", RETAILED: "Retailed", ACTIVE: "Active", DISABLED: "Disabled", DELETED: "Deleted", OPEN: "Open", IN_PROGRESS: "In progress", ESCALATED: "Escalated", RESOLVED: "Resolved", CLOSED: "Closed", PAYMENT: "Payment", REFUND: "Refund", REVERSAL: "Reversal", VALUATION: "Sale value revision" };
export const label = (value: unknown) => labels[String(value)] || text(value).replaceAll("_", " ");
export const ceoGet = <T>(path: string, query = "", signal?: AbortSignal) => api<T>(`/api/ceo/${path}/${query ? `?${query}` : ""}`, { signal });
export const exportReport = (section: string, query: string) => download(`/api/ceo/export/${section}/?${query}`, `ceo-${section}.csv`);
