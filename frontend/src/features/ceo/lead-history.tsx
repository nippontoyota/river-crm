import { label, money, text, type HistoryEvent, type ReportOptions, type ReportRow } from "@/lib/ceo";
import { formatDate, formatDateTime } from "@/lib/dates";
import { Badge } from "./report-ui";

export const eventLabels: Record<string, string> = {
  created: "Lead created", imported: "Lead imported", call: "Call logged",
  assigned_cre: "Assigned to CE", assigned_ps: "Assigned to PS/SO",
  auto_assigned_cre: "Automatically assigned to CE", bucket_assigned_cre: "Assigned to CE from bucket",
  reassignment_completed: "Lead reassigned", reassignment_queued: "Awaiting reassignment", deleted: "Lead archived",
  so_updated: "Lead updated", status_changed: "Lead stage changed", details_updated: "Customer details changed",
  qualification_updated: "CE qualification updated", followup_reviewed: "Follow-up reviewed",
  test_drive_completed: "Test drive completed", followup_scheduled: "Follow-up scheduled", followup_resolved: "Follow-up resolved",
  booking_cancelled: "Booking cancelled", reopened: "Lead reopened", complaint_created: "Complaint logged",
  complaint_updated: "Complaint updated", complaint_note: "Complaint note", complaint_resolved: "Complaint resolved",
  finance_payment: "Payment recorded", finance_refund: "Refund recorded", finance_reversal: "Financial entry reversed", finance_valuation: "Sale value revised",
};
const fieldLabels: Record<string, string> = {
  assigned_so: "CE", assigned_ps: "PS/SO", assigned_to_id: "Complaint owner", owner_id: "Follow-up owner",
  status: "Status", sales_outcome: "Sales result", category: "Category", call_status: "Call connection", outcome: "Call outcome",
  scheduled_for: "Scheduled for", agreed_amount: "Agreed amount", retail_amount: "Retail amount", confirmed_on: "Confirmed on",
  occurred_on: "Payment date", amount: "Amount", reference: "Reference", method: "Payment method", branch: "Branch",
  enquiry_date: "Enquiry date", test_drive_completed_at: "Completed at", model_interest: "Model", buying_timeline: "Buying timeline",
  test_drive: "Test-drive request", trade_in: "Trade-in", flagged_to_manager: "Flagged to manager",
  needs_cre_reassignment: "Needs CE reassignment", needs_so_reassignment: "Needs PS/SO reassignment",
};

export function LeadJourney({ detail }: { detail: ReportRow }) {
  const milestones = (detail.milestones as ReportRow[]) || [];
  return <section className="ceo-lead-journey" aria-label="Lead journey">
    <header><h3>Lead journey</h3><span>Current stage <Badge value={detail.status} /></span></header>
    <div className="ceo-milestone-list">{[["E", "Enquiry received"], ["T", "Test drive completed"], ["B", "First booking"], ["R", "First retail"]].map(([kind, title]) => {
      const milestone = milestones.find(item => item.kind === kind);
      return <div key={kind}><span className={milestone ? "done" : ""} aria-hidden="true">{milestone ? "✓" : "—"}</span><div><strong>{title}</strong><small>{milestone ? formatDate(text(milestone.occurred_on, "")) || "Date not recorded" : "Not recorded"}</small></div></div>;
    })}</div>
    <p>Recorded milestones are retained after cancellation or reopening. Unrecorded stages are not assumed.</p>
  </section>;
}

export function HistoryItem({ event, options, day }: { event: HistoryEvent; options: ReportOptions | null; day?: string }) {
  const format = (key: string, value: unknown): string => {
    if (["assigned_so", "assigned_ps", "assigned_to_id", "owner_id"].includes(key)) return options?.employees.find(user => user.id === Number(value))?.name || (value ? `Employee #${value}` : "Unassigned");
    if (value === null || value === undefined || value === "") return "Not recorded";
    if (["scheduled_for", "test_drive_completed_at"].includes(key)) return formatDateTime(String(value)) || "Not recorded";
    if (["enquiry_date", "occurred_on", "confirmed_on"].includes(key)) return formatDate(String(value)) || "Not recorded";
    if (key.includes("amount")) return money(value);
    if (typeof value === "boolean") return value ? "Yes" : "No";
    if (typeof value === "object") return JSON.stringify(value);
    return label(value);
  };
  // A call records the stage at that moment; it does not prove a transition.
  const stageKey = !event.complaint_id && ["so_updated", "status_changed", "reopened", "booking_cancelled"].includes(event.kind)
    ? ["status", "sales_outcome"].find(key => event.after[key] && event.before[key] !== event.after[key]) : undefined;
  const stage = stageKey ? { before: event.before[stageKey], after: event.after[stageKey] } : null;
  const title = event.kind === "call" && (event.after.outcome || event.after.call_status)
    ? `Call · ${format("outcome", event.after.outcome || event.after.call_status)}`
    : stage && ["so_updated", "status_changed"].includes(event.kind) ? "Lead stage changed" : eventLabels[event.kind] || label(event.kind);
  const changes = Object.entries(event.after).filter(([key, value]) => {
    if (["remarks", "notes", "content", "request", "followup_id", stageKey].includes(key)) return false;
    if (stage && key === "sales_outcome" && label(value) === label(stage.after) && label(event.before[key]) === label(stage.before)) return false;
    return event.before[key] !== value || event.kind === "call";
  });
  const notes = ["remarks", "notes", "content"].filter(key => event.after[key]);
  return <li className={`ceo-history-item${stage ? " ceo-history-stage" : ""}`}>
    {day && <h4 className="ceo-history-day">{day}</h4>}
    <div className="ceo-history-dot" aria-hidden="true" />
    <article>
      <header><strong>{title}</strong><time dateTime={event.occurred_at}>{formatDateTime(event.occurred_at)} IST</time></header>
      <small>By {event.actor || "actor not recorded"}{event.actor_role ? ` · ${label(event.actor_role)}` : ""}{event.provenance === "legacy" ? " · Historical record" : ""}{event.complaint_id ? ` · Complaint #${event.complaint_id}` : ""}</small>
      {stage && <div className="ceo-stage-transition" aria-label="Stage transition"><span>{stage.before ? label(stage.before) : "Previous stage not recorded"}</span><span aria-hidden="true">→</span><strong>{label(stage.after)}</strong></div>}
      {notes.map(key => <p key={key} className="ceo-note">{text(event.after[key])}</p>)}
      {changes.length > 0 && <dl className="ceo-event-fields">{changes.map(([key, value]) => <div key={key}><dt>{event.kind === "call" && key === "status" ? "Stage at time of call" : fieldLabels[key] || key.replaceAll("_", " ")}</dt><dd>{key in event.before && event.before[key] !== value ? <><span>{format(key, event.before[key])}</span> → </> : null}{format(key, value)}</dd></div>)}</dl>}
      {!stage && !notes.length && !changes.length && <p className="ceo-history-context">{event.kind === "so_updated" ? "Update recorded with no stage or customer detail changes. See nearby call entries for the conversation." : "No additional details were recorded for this event."}</p>}
    </article>
  </li>;
}
