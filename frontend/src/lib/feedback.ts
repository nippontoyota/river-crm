import { api, download } from "./crm";

export type FeedbackKind = "TDF" | "PBF" | "PSF";
export const feedbackNames: Record<FeedbackKind, string> = { TDF: "Test drive feedback", PBF: "Post booking feedback", PSF: "Post sales feedback" };
export const callOutcomes: Record<string, string> = { COLLECTED: "Feedback collected", NO_ANSWER: "No answer", BUSY: "Busy", SWITCHED_OFF: "Switched off", CALLBACK: "Customer requested callback", DECLINED: "Declined", INVALID_NUMBER: "Invalid number" };
export const feedbackBuckets: Record<string, string> = { open: "All open", upcoming: "Upcoming", due: "Due today", overdue: "Overdue", completed: "Completed", unreachable: "Unreachable", declined: "Declined", invalid_number: "Invalid number", unassigned: "Unassigned" };
export type FeedbackTask = {
  id: number; lead: number; customer: string; phone: string; model: string; branch: string; lead_branch: string;
  lead_status: string; sales_outcome: string; cre_name: string; so_name: string; kind: FeedbackKind;
  assigned_to: number | null; caller_name: string; status: string; occurred_at: string; original_due_at: string;
  next_call_at: string; unsuccessful_attempts: number; completed_at: string | null; closed_at: string | null;
  on_time: boolean | null; revision: number; created_at: string;
};
export type FeedbackDetail = FeedbackTask & {
  attempts: { id: number; caller: number; caller_name: string; branch: string; outcome: string; notes: string; scheduled_for: string; callback_at: string | null; created_at: string }[];
  assignments: { id: number; actor_name: string; previous_owner_name: string; assigned_to_name: string; previous_branch: string; branch: string; reason: string; created_at: string }[];
};
export type FeedbackCounts = Record<"total" | "leads" | "on_time" | "open" | "upcoming" | "due" | "overdue" | "completed" | "unreachable" | "declined" | "invalid_number" | "unassigned" | "completion_rate", number>;
export type FeedbackReport = {
  summary: FeedbackCounts; types: (FeedbackCounts & { kind: FeedbackKind })[]; backlog: FeedbackCounts;
  activity: { attempts: number; customers: number }; coverage: { leads_with_feedback: number; all_leads: number };
  comparisons: { branch: string; assigned_to_id: number | null; assigned_to__first_name: string | null; assigned_to__last_name: string | null; assigned_to__email: string | null; total: number; completed: number; overdue: number; unreachable: number }[];
  date_basis: string; date_from: string | null; date_to: string | null; generated_at: string;
};
export type FeedbackOptions = { branches: string[]; callers: { id: number; name: string; branch: string; active: boolean }[]; activated_at: string };
export type FeedbackPage = { count: number; next: string | null; previous: string | null; results: FeedbackTask[] };
export type FeedbackNotification = { id: number; message: string; feedback_task: number; feedback_kind: FeedbackKind; read_at: string | null; created_at: string };
export const getFeedback = (query: string, signal?: AbortSignal) => api<FeedbackPage>(`/api/feedback/?${query}`, { signal });
export const getFeedbackReport = (query: string, signal?: AbortSignal) => api<FeedbackReport>(`/api/feedback/summary/?${query}`, { signal });
export const getFeedbackOptions = () => api<FeedbackOptions>("/api/feedback/options/");
export const getFeedbackDetail = (id: number, signal?: AbortSignal) => api<FeedbackDetail>(`/api/feedback/${id}/`, { signal });
export const recordFeedback = (task: FeedbackTask, outcome: string, notes: string, callbackAt?: string) => api<FeedbackDetail>(`/api/feedback/${task.id}/attempt/`, { method: "POST", body: JSON.stringify({ revision: task.revision, outcome, notes, ...(callbackAt ? { callback_at: `${callbackAt}:00+05:30` } : {}) }) });
export const reassignFeedback = (task: FeedbackTask, assignedTo: number) => api<FeedbackDetail>(`/api/feedback/${task.id}/reassign/`, { method: "POST", body: JSON.stringify({ revision: task.revision, assigned_to: assignedTo }) });
export const exportFeedback = (query: string) => download(`/api/feedback/export/?${query}`, "feedback-tasks.csv");
