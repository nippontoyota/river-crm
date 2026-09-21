"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FeedbackManagement } from "./feedback-requests";
import { FeedbackIssuePanel } from "./feedback-issue";
import { getCurrentUser, type CurrentUser } from "@/lib/crm";
import { formatDate, formatDateTime, todayInIST } from "@/lib/dates";
import { callOutcomes, exportFeedback, feedbackBuckets, feedbackNames, getFeedback, getFeedbackDetail, getFeedbackOptions, getFeedbackReport, reassignFeedback, recordFeedback, type FeedbackDetail, type FeedbackOptions, type FeedbackPage, type FeedbackReport, type FeedbackTask } from "@/lib/feedback";

const errorText = (error: unknown) => error instanceof Error ? error.message : "Unable to load feedback. Try again.";
const label = (value: string) => value.replaceAll("_", " ").toLowerCase();

export function FeedbackDesk({ currentUser }: { currentUser?: CurrentUser }) {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const query = search.toString();
  const params = new URLSearchParams(query);
  const [user, setUser] = useState(currentUser);
  const [options, setOptions] = useState<FeedbackOptions | null>(null);
  const [report, setReport] = useState<FeedbackReport | null>(null);
  const [page, setPage] = useState<FeedbackPage | null>(null);
  const [detail, setDetail] = useState<FeedbackDetail | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);
  const [exporting, setExporting] = useState(false);
  const [searchText, setSearchText] = useState(params.get("q") || "");
  const [dateFrom, setDateFrom] = useState(params.get("date_from") || "");
  const [dateTo, setDateTo] = useState(params.get("date_to") || "");
  const taskId = Number(params.get("task")) || null;
  const manager = user?.role === "ADMIN" || user?.role === "SALES_MANAGER";
  const monitor = user?.role !== "FEEDBACK";
  const update = (values: Record<string, string | null>) => {
    const next = new URLSearchParams(query);
    if (!("page" in values)) next.delete("page");
    for (const [key, value] of Object.entries(values)) { next.delete(key); if (value) next.set(key, value); }
    router.replace(`${pathname}?${next}`, { scroll: false });
  };
  useEffect(() => {
    let active = true;
    void Promise.all([currentUser ? Promise.resolve({ user: currentUser }) : getCurrentUser(), getFeedbackOptions()])
      .then(([session, data]) => { if (active) { setUser(session.user); setOptions(data); } })
      .catch(e => { if (active) setError(errorText(e)); });
    return () => { active = false; };
  }, [currentUser]);
  useEffect(() => {
    const controller = new AbortController();
    const refresh = () => {
      setLoading(true);
      void Promise.all([getFeedback(query, controller.signal), getFeedbackReport(query, controller.signal)])
        .then(([tasks, data]) => { setPage(tasks); setReport(data); setError(""); })
        .catch(e => { if (e.name !== "AbortError") { setError(errorText(e)); setPage(null); setReport(null); } })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    };
    refresh();
    const timer = window.setInterval(refresh, 30000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [query, version]);
  useEffect(() => {
    const controller = new AbortController();
    if (taskId) void getFeedbackDetail(taskId, controller.signal).then(setDetail).catch(e => { if (e.name !== "AbortError") { setDetail(null); setError(errorText(e)); } });
    return () => controller.abort();
  }, [taskId, version]);
  const refresh = () => { setVersion(v => v + 1); window.dispatchEvent(new Event("feedback:changed")); };
  const exportRows = async () => { setExporting(true); try { await exportFeedback(query); } catch (e) { setError(errorText(e)); } finally { setExporting(false); } };
  const chooseBucket = (bucket: string, kind?: string, backlog = false) => update({ bucket, kind: kind || null, backlog: backlog ? "true" : null });

  return <section className="page feedback-page">
    <header className="feedback-heading"><div><p className="eyebrow">CUSTOMER EXPERIENCE · {monitor ? "FEEDBACK REPORTING" : "CALL CENTER"}</p><h1>{monitor ? "Feedback performance" : "Customer feedback calls"}</h1><p className="subtext">Test drive. Booking. Ownership. Service. {monitor ? "Follow every stage of customer feedback." : "Your customer calls, ready when they’re due."}</p></div><button className="filter" onClick={refresh} disabled={loading}>{loading ? "Refreshing…" : "Refresh"}</button></header>
    <div className="feedback-toolbar">
      <label>Original due date<select value={params.get("range") || "all"} onChange={e => { if (e.target.value === "custom") { const from = dateFrom || todayInIST(); const to = dateTo || todayInIST(); setDateFrom(from); setDateTo(to); update({ range: "custom", date_from: from, date_to: to, backlog: null }); } else update({ range: e.target.value, backlog: null }); }}><option value="all">All dates</option><option value="today">Today</option><option value="mtd">Month to date</option><option value="previous_month">Previous month</option><option value="quarter">This quarter</option><option value="custom">Custom dates</option></select></label>
      {params.get("range") === "custom" && <form className="feedback-date-range" onSubmit={e => { e.preventDefault(); update({ date_from: dateFrom, date_to: dateTo }); }}><label>From<input type="date" required value={dateFrom} onChange={e => setDateFrom(e.target.value)} /></label><label>To<input type="date" required min={dateFrom} value={dateTo} onChange={e => setDateTo(e.target.value)} /></label><button className="filter" type="submit">Apply dates</button></form>}
      {monitor && <label>Branch<select value={params.get("branch") || ""} onChange={e => update({ branch: e.target.value, caller: null })}><option value="">{user?.role === "SALES_MANAGER" ? "My branch" : "All branches"}</option>{options?.branches.map(b => <option key={b} value={b}>{b}</option>)}{user?.role !== "SALES_MANAGER" && <option value="__unknown__">No branch recorded</option>}</select></label>}
      {monitor && <label>Caller<select value={params.get("caller") || ""} onChange={e => update({ caller: e.target.value })}><option value="">All callers</option><option value="unassigned">Unassigned</option>{options?.callers.map(c => <option key={c.id} value={c.id}>{c.name}{c.active ? "" : " · Inactive"}</option>)}</select></label>}
      <button className="filter feedback-export" disabled={exporting} onClick={() => void exportRows()}>{exporting ? "Exporting…" : "Export CSV"}</button>
    </div>
    {error && <p className="feedback-error" role="alert">{error}</p>}
    {report && <>
      <div className="feedback-backlog"><b>Current backlog <small>All due dates</small></b>{["due", "overdue", ...(monitor ? ["unassigned"] : [])].map(bucket => <button key={bucket} onClick={() => chooseBucket(bucket, undefined, true)}><strong>{report.backlog[bucket as "due"]}</strong>{feedbackBuckets[bucket]}</button>)}<span>{report.activity.attempts} attempts · {report.activity.customers} customers<small>Call activity in selected period</small></span></div>
      <div className="feedback-type-grid">{report.types.map(type => <article key={type.kind} className={`feedback-type-card ${type.kind.toLowerCase()}`}>
        <header><button onClick={() => update({ kind: type.kind, bucket: null, backlog: null })}>{type.kind}</button><span>{feedbackNames[type.kind]}</span></header>
        <div className="feedback-type-total"><button onClick={() => update({ kind: type.kind, bucket: null, backlog: null })}>{type.total}<small>total calls</small></button><span><b>{type.completion_rate}%</b> completed</span></div>
        <progress max={type.total || 1} value={type.completed} aria-label={`${type.kind} completion`} />
        <div className="feedback-type-counts">{["completed", "due", "overdue", "upcoming", "unreachable", "declined", "invalid_number", ...(monitor ? ["unassigned"] : [])].map(bucket => <button key={bucket} onClick={() => chooseBucket(bucket, type.kind)}><b>{type[bucket as "completed"]}</b><span>{feedbackBuckets[bucket]}</span></button>)}</div>
      </article>)}</div>
      <p className="feedback-caption">{report.customers} distinct customers · {report.summary.completed} of {report.summary.total} calls completed · {report.summary.on_time} completed on time. On-time totals exclude historical catch-up.</p>
      <p className="feedback-caption">{monitor ? "Feedback" : "Your feedback"} covers {report.coverage.leads_with_feedback} of {report.coverage.all_leads} leads {monitor ? "in the selected branch scope" : "across all branches"}, across all dates since launch{options ? ` on ${formatDate(options.activated_at)}` : ""}. Sales-lead coverage excludes service, requested feedback, and historical catch-up.</p>
    </>}
    {report && <section className="panel feedback-quality"><h2>Customer satisfaction</h2><p>{report.summary.average_satisfaction?.toFixed(1) || "—"} / 5 from {report.summary.rated} ratings · Not provided is excluded.</p><div className="feedback-actions">{report.satisfaction.map(row => <span key={row.rating}>{row.rating} stars: <b>{row.count}</b></span>)}<button className="filter" onClick={() => update({ bucket: "issues", backlog: "true" })}>View unresolved issues</button><span>{report.unresolved_issues} unresolved across all dates</span></div><p>{report.origins.HISTORICAL.total} historical catch-up calls · {report.origins.MANUAL.total} requested calls</p></section>}
    {manager && <FeedbackManagement admin={user?.role === "ADMIN"} changed={refresh} version={version} />}
    <section className="panel feedback-queue"><header><div><h2>{params.get("backlog") === "true" ? "Current backlog · all due dates" : "Feedback calls"}</h2><p className="subtext">{page?.count ?? 0} calls {params.get("backlog") === "true" ? "across all due dates" : "in the selected period"}</p></div><form onSubmit={e => { e.preventDefault(); update({ q: searchText }); }}><input aria-label="Search customer or phone" placeholder="Customer name or phone" value={searchText} onChange={e => setSearchText(e.target.value)} /><button className="filter">Search</button></form></header>
      <div className="feedback-queue-filters"><div className="feedback-tabs" role="group" aria-label="Feedback type">{["", ...Object.keys(feedbackNames)].map(kind => <button key={kind} aria-pressed={(params.get("kind") || "") === kind} onClick={() => update({ kind })}>{kind || "All types"}</button>)}</div><label>Origin<select value={params.get("origin") || ""} onChange={e => update({ origin: e.target.value })}><option value="">All origins</option><option value="AUTOMATIC">Automatic</option><option value="MANUAL">Requested feedback</option><option value="HISTORICAL">Historical catch-up</option></select></label><label>Status<select value={params.get("bucket") || ""} onChange={e => update({ bucket: e.target.value })}><option value="">All statuses</option>{Object.entries(feedbackBuckets).filter(([key]) => monitor || key !== "unassigned").map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select></label>{params.get("backlog") === "true" && <button className="filter" onClick={() => update({ backlog: null })}>Use selected date period</button>}</div>
      <div className="feedback-table-scroll"><table className="feedback-table"><thead><tr><th>Customer</th><th>Type / lead stage</th><th>Branch / caller</th><th>Next call</th><th>Feedback status</th><th>Action</th></tr></thead><tbody>{page?.results.map(task => <tr key={task.id}><td><button className="feedback-text-button" onClick={() => update({ task: String(task.id) })}>{task.customer}</button><small>{task.phone} · {task.model || "Model not recorded"}</small></td><td><span className={`feedback-tag ${task.kind.toLowerCase()}`}>{task.kind}</span><small>{task.service_ticket || `${label(task.sales_outcome)} · ${label(task.lead_status)}`}</small>{task.origin === "HISTORICAL" && <small>Historical catch-up</small>}</td><td>{task.branch || "No branch"}<small>{task.caller_name}</small>{task.unassigned_reason && <small>{task.unassigned_reason}</small>}</td><td>{task.status === "OPEN" ? formatDateTime(task.next_call_at) : "—"}<small>Original: {formatDateTime(task.original_due_at)}</small></td><td><span className={`feedback-status ${task.status.toLowerCase()}`}>{label(task.status)}</span><small>{task.unsuccessful_attempts}/3 unsuccessful attempts</small>{task.issue_status && <small>Issue: {label(task.issue_status)}</small>}</td><td><button className="filter" onClick={() => update({ task: String(task.id) })}>Open call</button></td></tr>)}</tbody></table></div>
      {!page?.results.length && <div className="empty-state">{loading ? "Loading feedback calls…" : "No calls match these filters. Completed test drives, bookings, retails, and resolved service requests generate calls automatically."}</div>}
      <footer className="feedback-pagination"><button className="filter" disabled={!page?.previous} onClick={() => update({ page: String(Math.max(1, Number(params.get("page") || 1) - 1)) })}>Previous</button><span>Page {params.get("page") || 1}</span><button className="filter" disabled={!page?.next} onClick={() => update({ page: String(Number(params.get("page") || 1) + 1) })}>Next</button></footer>
    </section>
    {monitor && report && <section className="panel feedback-comparisons"><h2>Branch and caller performance</h2><p className="subtext">Selected original due-date period. Select a row to view its calls.</p><div className="feedback-table-scroll"><table className="feedback-table"><thead><tr><th>Branch</th><th>Caller</th><th>Total</th><th>Completed</th><th>Completion</th><th>Overdue</th><th>Unreachable</th><th>Rating</th><th>Unresolved issues</th><th>Historical</th></tr></thead><tbody>{report.comparisons.map(row => <tr key={`${row.branch}-${row.assigned_to_id}`}><td>{row.branch || "No branch"}</td><td><button className="feedback-text-button" onClick={() => update({ branch: row.branch || "__unknown__", caller: row.assigned_to_id ? String(row.assigned_to_id) : "unassigned", kind: null, bucket: null, backlog: null })}>{[row.assigned_to__first_name, row.assigned_to__last_name].filter(Boolean).join(" ") || row.assigned_to__email || "Unassigned"}</button></td><td>{row.total}</td><td>{row.completed}</td><td>{row.total ? (100 * row.completed / row.total).toFixed(1) : 0}%</td><td>{row.overdue}</td><td>{row.unreachable}</td><td>{row.average_satisfaction?.toFixed(1) || "—"}</td><td>{row.unresolved_issues}</td><td>{row.historical}</td></tr>)}</tbody></table></div>{!report.comparisons.length && <p className="empty-state">No feedback tasks in this reporting period.</p>}</section>}
    {detail && taskId === detail.id && user && <FeedbackCallDialog key={detail.id} task={detail} user={user} options={options} canReassign={manager} close={() => update({ task: null })} saved={task => { setDetail(task); refresh(); }} />}
  </section>;
}

function FeedbackCallDialog({ task, user, options, canReassign, close, saved }: { task: FeedbackDetail; user: CurrentUser; options: FeedbackOptions | null; canReassign: boolean; close: () => void; saved: (task: FeedbackDetail) => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [outcome, setOutcome] = useState("COLLECTED");
  const [notes, setNotes] = useState("");
  const [callback, setCallback] = useState("");
  const [satisfaction, setSatisfaction] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [furtherHelp, setFurtherHelp] = useState(false);
  const [helpDetails, setHelpDetails] = useState("");
  const [assignee, setAssignee] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => dialog?.close(); }, []);
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 30000); return () => window.clearInterval(timer); }, []);
  const canCall = user.role === "FEEDBACK" && task.assigned_to === user.id && task.status === "OPEN";
  const due = new Date(task.next_call_at).getTime() <= now;
  const save = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError("");
    try { saved(await recordFeedback(task, outcome, notes, outcome === "CALLBACK" ? callback : undefined, outcome === "COLLECTED" ? { satisfaction: satisfaction ? Number(satisfaction) : null, answers, further_help: furtherHelp, help_details: helpDetails } : undefined)); setNotes(""); setCallback(""); }
    catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  };
  const reassign = async () => { setBusy(true); setError(""); try { saved(await reassignFeedback(task, Number(assignee))); } catch (e) { setError(errorText(e)); } finally { setBusy(false); } };
  return <dialog ref={ref} className="feedback-dialog" onCancel={event => { event.preventDefault(); close(); }} aria-labelledby="feedback-call-title"><header><div><span className={`feedback-tag ${task.kind.toLowerCase()}`}>{task.kind} · {feedbackNames[task.kind]}</span><h2 id="feedback-call-title">{task.customer}</h2><p>{task.model || "Model not recorded"} · {task.branch || "No branch"}</p></div><button className="filter" onClick={close} aria-label="Close feedback call">Close</button></header>
    <div className="feedback-customer"><a href={canCall && due ? `tel:${task.phone}` : undefined} className="feedback-phone">{task.phone}</a><span>{label(task.status)}</span></div>
    <dl className="feedback-details"><div><dt>Current lead stage</dt><dd>{label(task.lead_status)} · {label(task.sales_outcome)}</dd></div><div><dt>SO / CRE</dt><dd>{task.so_name} / {task.cre_name}</dd></div><div><dt>Event recorded</dt><dd>{formatDateTime(task.occurred_at)}</dd></div><div><dt>Original due date</dt><dd>{formatDateTime(task.original_due_at)}</dd></div><div><dt>Feedback caller</dt><dd>{task.caller_name}</dd></div><div><dt>Next call / closed</dt><dd>{formatDateTime(task.closed_at || task.next_call_at)}</dd></div></dl>
    {task.origin === "HISTORICAL" && <p className="feedback-tag">Historical catch-up</p>}
    {task.service && <section><h3>{task.service.ticket} · {label(task.service.status)}</h3><p>{task.service.issue}</p><p>Resolution: {task.service.resolution_notes}</p><p>Chassis: {task.service.vehicle.chassis_number}</p></section>}
    {task.request_reason && <p><b>Requested feedback:</b> {task.request_reason}</p>}
    {task.cancellation_reason && <p>{task.cancellation_reason}</p>}
    {!!task.other_open_tasks.length && <p>Other open calls: {task.other_open_tasks.map(t => `${t.kind} · ${formatDateTime(t.next_call_at)}`).join("; ")}</p>}
    {error && <p className="feedback-error" role="alert">{error}</p>}
    {canCall && <form onSubmit={save} className="feedback-call-form"><h3>Record this call</h3>{!due && <p className="subtext">This call becomes available at {formatDateTime(task.next_call_at)}.</p>}<label>Call outcome<select value={outcome} onChange={e => setOutcome(e.target.value)}>{Object.entries(callOutcomes).map(([key, name]) => <option value={key} key={key}>{name}</option>)}</select></label>{outcome === "COLLECTED" && <fieldset className="feedback-questionnaire"><legend>Customer experience</legend><label>Overall satisfaction<select aria-label="Overall satisfaction" value={satisfaction} onChange={e => setSatisfaction(e.target.value)}><option value="">Not provided</option>{[1,2,3,4,5].map(rating => <option key={rating} value={rating}>{rating} / 5</option>)}</select></label>{Object.entries(task.questions).map(([key, question]) => <label key={key}>{question}<select required name={key} value={answers[key] || ""} onChange={e => setAnswers(previous => ({ ...previous, [key]: e.target.value }))}><option value="">Choose answer</option><option value="YES">Yes</option><option value="NO">No</option><option value="NOT_DISCUSSED">Not discussed</option></select></label>)}<label>Further help needed?<select value={furtherHelp ? "YES" : "NO"} onChange={e => setFurtherHelp(e.target.value === "YES")}><option value="NO">No</option><option value="YES">Yes</option></select></label>{furtherHelp && <label>Help needed<textarea required maxLength={5000} value={helpDetails} onChange={e => setHelpDetails(e.target.value)} /></label>}</fieldset>}<label>{outcome === "COLLECTED" ? "Customer feedback" : "Call notes"}<textarea required={["COLLECTED", "DECLINED", "INVALID_NUMBER"].includes(outcome)} maxLength={5000} value={notes} onChange={e => setNotes(e.target.value)} placeholder="Record what the customer shared or the reason for closing this call." /></label>{outcome === "CALLBACK" && <label>Callback date and time · India time<input type="datetime-local" required value={callback} onChange={e => setCallback(e.target.value)} /></label>}<p className="subtext">{task.unsuccessful_attempts}/3 unsuccessful attempts. Unanswered calls retry at 9 AM the next day.</p><button className="button primary" disabled={busy || !due}>{busy ? "Saving…" : "Save call outcome"}</button></form>}
    {canReassign && task.status === "OPEN" && <section className="feedback-reassign"><h3>Reassign call</h3><label>Feedback caller<select value={assignee} onChange={e => setAssignee(e.target.value)}><option value="">Choose caller</option>{options?.callers.filter(c => c.active && c.id !== task.assigned_to).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label><button className="filter" disabled={!assignee || busy} onClick={() => void reassign()}>Reassign call</button></section>}
    {task.status === "COMPLETED" && <section className="feedback-answers"><h3>Collected feedback{task.questionnaire_version ? ` · questionnaire v${task.questionnaire_version}` : " · legacy notes"}</h3><p>Overall satisfaction: {task.satisfaction ? `${task.satisfaction} / 5` : "Not provided"}</p>{Object.entries(task.answers).map(([key, answer]) => <p key={key}>{task.questions[key]} <b>{label(answer)}</b></p>)}{task.further_help && <p>Further help needed: {task.help_details}</p>}</section>}
    <FeedbackIssuePanel task={task} manager={canReassign} caller={user.role === "FEEDBACK"} options={options} saved={saved} />
    <section className="feedback-history"><h3>Call history</h3>{task.attempts.length ? task.attempts.map(attempt => <article key={attempt.id}><header><b>{callOutcomes[attempt.outcome]}</b><time>{formatDateTime(attempt.created_at)}</time></header><small>{attempt.caller_name} · {attempt.branch}</small>{attempt.notes && <p>{attempt.notes}</p>}{attempt.callback_at && <small>Requested callback: {formatDateTime(attempt.callback_at)}</small>}</article>) : <p className="subtext">No calls recorded yet.</p>}</section>
    <section className="feedback-history"><h3>Customer contact history</h3>{task.contact_history.filter(a => a.task !== task.id).map(attempt => <article key={attempt.id}><header><b>{attempt.kind} · {callOutcomes[attempt.outcome]}</b><time>{formatDateTime(attempt.created_at)}</time></header><small>{attempt.caller_name}</small><p>{attempt.notes}</p></article>)}{!task.contact_history.some(a => a.task !== task.id) && <p className="subtext">No other feedback calls visible for this customer.</p>}</section>
    <details className="feedback-assignment-history"><summary>Assignment history</summary>{task.assignments.map(a => <p key={a.id}><b>{a.previous_owner_name} → {a.assigned_to_name}</b><br />{a.reason} · {a.branch || "No branch"} · {a.actor_name}<br /><small>{formatDateTime(a.created_at)}</small></p>)}</details>
  </dialog>;
}
