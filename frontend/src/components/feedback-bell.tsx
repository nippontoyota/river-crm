"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/crm";
import { feedbackNames, type FeedbackNotification } from "@/lib/feedback";
import { formatDateTime } from "@/lib/dates";

export function FeedbackBell() {
  const [count, setCount] = useState(0);
  const [items, setItems] = useState<FeedbackNotification[]>([]);
  const [kind, setKind] = useState("");
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  const query = `feedback=true${kind ? `&feedback_kind=${kind}` : ""}`;
  useEffect(() => {
    const controller = new AbortController();
    const refresh = () => {
      void Promise.all([
        api<{ count: number }>("/api/notifications/unread_count/?feedback=true", { signal: controller.signal }),
        api<{ results: FeedbackNotification[] }>(`/api/notifications/?${query}`, { signal: controller.signal }),
      ]).then(([unread, notifications]) => { setCount(unread.count); setItems(notifications.results); setError(""); }).catch(e => { if (e.name !== "AbortError") setError(e.message); });
    };
    refresh();
    const timer = window.setInterval(refresh, 30000);
    window.addEventListener("feedback:changed", refresh);
    return () => { controller.abort(); window.clearInterval(timer); window.removeEventListener("feedback:changed", refresh); };
  }, [query, version]);
  const markRead = async (id?: number) => {
    try { await api(`/api/notifications/${id ? `${id}/read/` : `mark_read/?${query}`}`, { method: "POST" }); setVersion(v => v + 1); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to mark notifications read."); }
  };
  return <details className="feedback-bell">
    <summary aria-label={`Feedback notifications, ${count} unread`}><svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></svg><span>{count}</span></summary>
    <div className="feedback-notifications"><header><b>Feedback notifications</b><button className="filter" onClick={() => void markRead()}>Mark read</button></header>
      <label>Call type<select value={kind} onChange={e => setKind(e.target.value)}><option value="">All types</option>{Object.entries(feedbackNames).map(([code, name]) => <option key={code} value={code}>{code} · {name}</option>)}</select></label>
      {error && <p role="alert">{error}</p>}
      {items.length ? items.map(item => <Link className={item.read_at ? "read" : "unread"} key={item.id} href={`/feedback?task=${item.feedback_task}`} onClick={event => { void markRead(item.id); event.currentTarget.closest("details")?.removeAttribute("open"); }}><b>{item.message}</b><small>{formatDateTime(item.created_at)}</small></Link>) : <p>No notifications yet. New assignments and due calls will appear here.</p>}
      <Link href="/feedback?bucket=open">View all open calls</Link>
    </div>
  </details>;
}
