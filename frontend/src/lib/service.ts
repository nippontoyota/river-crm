import { api } from "./crm";

export type Customer = { customer_name: string; customer_phone: string; customer_email: string };
export type Vehicle = Customer & {
  id: number; chassis_number: string; model: string; registration_number: string; related_lead: number | null;
  sale: { id: number; branch: string; sales_outcome: string; enquiry_date: string | null } | null;
  history?: ServiceRequest[];
  corrections?: { reason: string; before: Record<string, unknown>; after: Record<string, unknown>; created_at: string }[];
};
export const serviceStatuses: Record<string, string> = { RECORDED: "Recorded", FORWARDED: "Incoming", IN_PROGRESS: "In progress", WAITING: "Waiting", RESOLVED: "Resolved", CANCELLED: "Cancelled" };
export type ServiceRequest = {
  id: number; ticket_number: string; vehicle: number; customer_snapshot: Customer;
  vehicle_snapshot: { chassis_number: string; model: string; registration_number: string };
  issue: string; branch: string; status: string; source: string; priority: string; odometer: number | null;
  preferred_appointment: string | null; resolution_notes: string; resolved_at: string | null;
  created_by: number; created_by_name: string; revision: number; created_at: string; updated_at: string; branch_staff_available: boolean;
  vehicle_details?: Vehicle; history?: ServiceRequest[];
  events?: { id: number; action: string; note: string; actor_name: string; before: Record<string, unknown>; after: Record<string, unknown>; created_at: string }[];
};
export type Page<T> = { count: number; results: T[]; next: string | null; previous: string | null };
export const getServiceRequest = (id: number) => api<ServiceRequest>(`/api/service-requests/${id}/`);
export const getVehicle = (vehicle: Pick<Vehicle, "id" | "chassis_number">) => api<Vehicle>(`/api/vehicles/${vehicle.id}/?chassis=${encodeURIComponent(vehicle.chassis_number)}`);
export const serviceAction = (row: ServiceRequest, action: string, values: Record<string, unknown> = {}) => api<ServiceRequest>(`/api/service-requests/${row.id}/${action}/`, { method: "POST", body: JSON.stringify({ revision: row.revision, ...values }) });
