"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/crm";
import { type Page } from "@/lib/service";
import { formatDateTime } from "@/lib/dates";

type Notice = { id: number; service_request: number; read_at: string | null; message: string; created_at: string };
export function ServiceBell() {
  const [items, setItems] = useState<Notice[]>([]);
  const [count, setCount] = useState(0);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    const refresh = () => { if (document.hidden) return; void Promise.all([api<Page<Notice>>("/api/notifications/?service=true", { signal: controller.signal }), api<{ count: number }>("/api/notifications/unread_count/?service=true", { signal: controller.signal })]).then(([page, unread]) => { setItems(page.results); setCount(unread.count); setError(""); }).catch(e => { if (e.name !== "AbortError") setError(e.message); }); };
    refresh(); const timer = window.setInterval(refresh, 30000); window.addEventListener("focus", refresh);
    return () => { controller.abort(); clearInterval(timer); window.removeEventListener("focus", refresh); };
  }, []);
  const read = async (id?: number) => { try { await api(`/api/notifications/${id ? `${id}/read/` : "mark_read/?service=true"}`, { method: "POST" }); setItems(rows => rows.map(row => !id || row.id === id ? { ...row, read_at: new Date().toISOString() } : row)); setCount(value => id ? Math.max(0, value - (items.find(item => item.id === id)?.read_at ? 0 : 1)) : 0); } catch (e) { setError(e instanceof Error ? e.message : "Unable to mark notifications read."); } };
  return <details className="feedback-bell"><summary aria-label={`Service notifications, ${count} unread`}>Services <span>{count}</span></summary><div className="feedback-notifications"><header><b>Service notifications</b><button className="filter" onClick={() => void read()}>Mark read</button></header>{error && <p role="alert">{error}</p>}{items.length ? items.map(item => <Link key={item.id} className={item.read_at ? "read" : "unread"} href={`/services?request=${item.service_request}`} onClick={() => { void read(item.id); window.dispatchEvent(new CustomEvent("service:open", { detail: item.service_request })); }}><b>{item.message}</b><small>{formatDateTime(item.created_at)}</small></Link>) : <p>No service notifications yet.</p>}</div></details>;
}
