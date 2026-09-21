import { api, download } from "./crm";

export type FeedbackKind = "TDF" | "PBF" | "PSF" | "SVC" | "GEN";
export const feedbackNames: Record<FeedbackKind, string> = { TDF: "Test drive feedback", PBF: "Post booking feedback", PSF: "Post sales feedback", SVC: "Service feedback", GEN: "Requested feedback" };
export const callOutcomes: Record<string, string> = { COLLECTED: "Feedback collected", NO_ANSWER: "No answer", BUSY: "Busy", SWITCHED_OFF: "Switched off", CALLBACK: "Customer requested callback", DECLINED: "Declined", INVALID_NUMBER: "Invalid number" };
export const feedbackBuckets: Record<string, string> = { issues: "Issues needing attention", cancelled: "Cancelled", open: "All open", upcoming: "Upcoming", due: "Due today", overdue: "Overdue", completed: "Completed", unreachable: "Unreachable", declined: "Declined", invalid_number: "Invalid number", unassigned: "Unassigned" };
export type FeedbackTask = {
  id: number; lead: number | null; customer: string; phone: string; model: string; branch: string; lead_branch: string;
  lead_status: string; sales_outcome: string; cre_name: string; so_name: string; kind: FeedbackKind;
  assigned_to: number | null; caller_name: string; status: string; occurred_at: string; original_due_at: string;
  next_call_at: string; unsuccessful_attempts: number; completed_at: string | null; closed_at: string | null;
  on_time: boolean | null; revision: number; created_at: string;
  origin: "AUTOMATIC" | "MANUAL" | "HISTORICAL"; cancellation_reason: string; service_ticket: string | null; request_reason: string;
  unassigned_reason: string; questionnaire_version: number | null; answers: Record<string, string>; satisfaction: number | null;
  further_help: boolean; help_details: string; issue_status: string | null; complaint_ticket: string | null; complaint_status: string | null;
};
export type FeedbackAnswers = { satisfaction: number | null; answers: Record<string, string>; further_help: boolean; help_details: string };
export type FeedbackIssue = { status: string; reason: string; acknowledged_at: string | null; acknowledged_by_name: string | null; resolved_at: string | null; resolved_by_name: string | null; resolution_notes: string; events: { status: string; reviewer: string; note: string; created_at: string }[] };
export type FeedbackDetail = FeedbackTask & {
  questions: Record<string, string>; issue: FeedbackIssue | null;
  service: { ticket: string; status: string; vehicle: Record<string, string | number | null>; issue: string; resolution_notes: string } | null;
  contact_history: { id: number; task: number; kind: FeedbackKind; caller_name: string; outcome: string; notes: string; created_at: string }[];
  other_open_tasks: { id: number; kind: FeedbackKind; next_call_at: string }[];
  attempts: { id: number; caller: number; caller_name: string; branch: string; outcome: string; notes: string; scheduled_for: string; callback_at: string | null; created_at: string }[];
  assignments: { id: number; actor_name: string; previous_owner_name: string; assigned_to_name: string; previous_branch: string; branch: string; reason: string; created_at: string }[];
};
export type FeedbackCounts = Record<"total" | "leads" | "on_time" | "open" | "upcoming" | "due" | "overdue" | "completed" | "unreachable" | "declined" | "invalid_number" | "unassigned" | "completion_rate" | "historical" | "issues" | "rated", number> & { average_satisfaction: number | null };
export type FeedbackReport = {
  unresolved_issues: number; customers: number; satisfaction: { rating: number; count: number }[]; origins: Record<string, FeedbackCounts>;
  summary: FeedbackCounts; types: (FeedbackCounts & { kind: FeedbackKind })[]; backlog: FeedbackCounts;
  activity: { attempts: number; customers: number }; coverage: { leads_with_feedback: number; all_leads: number };
  comparisons: { branch: string; assigned_to_id: number | null; assigned_to__first_name: string | null; assigned_to__last_name: string | null; assigned_to__email: string | null; total: number; completed: number; overdue: number; unreachable: number; unresolved_issues: number; average_satisfaction: number | null; historical: number }[];
  date_basis: string; date_from: string | null; date_to: string | null; generated_at: string;
};
export type FeedbackOptions = { branches: string[]; callers: { id: number; name: string; active: boolean }[]; activated_at: string; complaint_categories: Record<string, string>; complaint_subtypes: Record<string, string[]> };
export type FeedbackPage = { count: number; next: string | null; previous: string | null; results: FeedbackTask[] };
export type FeedbackNotification = { id: number; message: string; feedback_task: number; feedback_kind: FeedbackKind; read_at: string | null; created_at: string };
export const getFeedback = (query: string, signal?: AbortSignal) => api<FeedbackPage>(`/api/feedback/?${query}`, { signal });
export const getFeedbackReport = (query: string, signal?: AbortSignal) => api<FeedbackReport>(`/api/feedback/summary/?${query}`, { signal });
export const getFeedbackOptions = () => api<FeedbackOptions>("/api/feedback/options/");
export const getFeedbackDetail = (id: number, signal?: AbortSignal) => api<FeedbackDetail>(`/api/feedback/${id}/`, { signal });
export const recordFeedback = (task: FeedbackTask, outcome: string, notes: string, callbackAt?: string, answers?: FeedbackAnswers) => api<FeedbackDetail>(`/api/feedback/${task.id}/attempt/`, { method: "POST", body: JSON.stringify({ revision: task.revision, outcome, notes, ...answers, ...(callbackAt ? { callback_at: `${callbackAt}:00+05:30` } : {}) }) });
export const reassignFeedback = (task: FeedbackTask, assignedTo: number) => api<FeedbackDetail>(`/api/feedback/${task.id}/reassign/`, { method: "POST", body: JSON.stringify({ revision: task.revision, assigned_to: assignedTo }) });
export const exportFeedback = (query: string) => download(`/api/feedback/export/?${query}`, "feedback-tasks.csv");

export const updateFeedbackIssue = (task: FeedbackTask, status: string, notes: string) => api<FeedbackDetail>(`/api/feedback/${task.id}/issue/`, { method: "POST", body: JSON.stringify({ revision: task.revision, status, notes }) });
export const raiseFeedbackComplaint = (task: FeedbackTask, category: string, subtype: string, description: string, confirmed: boolean) => api<FeedbackDetail>(`/api/feedback/${task.id}/complaint/`, { method: "POST", body: JSON.stringify({ revision: task.revision, category, subtype, description, confirmed }) });
export type FeedbackRequest = { id: number; lead: number; customer: string; branch: string; requester: string; reason: string; preferred_at: string; status: string; reviewer: string | null; reviewed_at: string | null; review_notes: string; revision: number; created_at: string };
export type HistoricalRecord = { key: string; kind: FeedbackKind; customer: string; branch: string; occurred_at: string; original_due_at: string; exclusion_reason: string; unassigned_reason: string; proposed_caller: { id: number; name: string } | null };
