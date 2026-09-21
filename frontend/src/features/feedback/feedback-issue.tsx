"use client";
import { useState, type FormEvent } from "react";
import { formatDateTime } from "@/lib/dates";
import { raiseFeedbackComplaint, updateFeedbackIssue, type FeedbackDetail, type FeedbackOptions } from "@/lib/feedback";

export function FeedbackIssuePanel({ task, manager, caller, options, saved }: { task: FeedbackDetail; manager: boolean; caller: boolean; options: FeedbackOptions | null; saved: (task: FeedbackDetail) => void }) {
  const [notes, setNotes] = useState("");
  const [category, setCategory] = useState("");
  const [subtype, setSubtype] = useState("");
  const [description, setDescription] = useState(task.help_details || task.attempts.find(a => a.outcome === "COLLECTED")?.notes || "");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const review = async (status: string) => {
    setBusy(true); setError("");
    try { saved(await updateFeedbackIssue(task, status, notes)); setNotes(""); } catch (e) { setError(e instanceof Error ? e.message : "Unable to update issue."); } finally { setBusy(false); }
  };
  const complain = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError("");
    try { saved(await raiseFeedbackComplaint(task, category, subtype, description, confirmed)); } catch (e) { setError(e instanceof Error ? e.message : "Unable to raise complaint."); } finally { setBusy(false); }
  };
  return <section className="feedback-issue">
    {task.issue && <><h3>Customer issue · {task.issue.status.toLowerCase()}</h3><p>{task.issue.reason}</p>{task.complaint_ticket && <p><b>{task.complaint_ticket}</b> · {task.complaint_status?.toLowerCase().replaceAll("_", " ")} · Complaints department</p>}
      {task.issue.resolution_notes && <p>Resolution: {task.issue.resolution_notes}</p>}
      {manager && task.issue.status !== "RESOLVED" && <div className="feedback-request-form"><label>Review notes<textarea maxLength={5000} value={notes} onChange={e => setNotes(e.target.value)} /></label><div className="feedback-actions">{task.issue.status === "OPEN" && <button className="filter" disabled={busy || !notes.trim()} onClick={() => void review("ACKNOWLEDGED")}>Acknowledge issue</button>}{!task.complaint_ticket && <button className="filter" disabled={busy || !notes.trim()} onClick={() => void review("RESOLVED")}>Resolve issue</button>}</div></div>}
      <details><summary>Issue history</summary>{task.issue.events.map((event, i) => <p key={i}><b>{event.status.toLowerCase()} · {event.reviewer}</b><br />{event.note}<br /><small>{formatDateTime(event.created_at)}</small></p>)}</details>
    </>}
    {caller && task.status === "COMPLETED" && !task.complaint_ticket && task.issue?.status !== "RESOLVED" && <details><summary>Raise complaint</summary><form onSubmit={complain} className="feedback-request-form"><label>Complaint category<select required value={category} onChange={e => { setCategory(e.target.value); setSubtype(""); }}><option value="">Choose category</option>{Object.entries(options?.complaint_categories || {}).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select></label><label>Complaint subtype<select required value={subtype} onChange={e => setSubtype(e.target.value)}><option value="">Choose subtype</option>{options?.complaint_subtypes[category]?.map(name => <option key={name}>{name}</option>)}</select></label><label>Complaint description<textarea required maxLength={5000} value={description} onChange={e => { setDescription(e.target.value); setConfirmed(false); }} /></label><label className="feedback-checkbox"><input type="checkbox" required checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />I confirm this description for the Complaints department.</label><button className="button primary" disabled={busy || !confirmed}>Raise complaint</button></form></details>}
    {error && <p role="alert" className="feedback-error">{error}</p>}
  </section>;
}
