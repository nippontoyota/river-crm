"use client";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { count, label, text, type ReportRow } from "@/lib/ceo";

export function Drawer({ title, onClose, children, wide = false }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  return <dialog ref={ref} className={`ceo-drawer ${wide ? "wide" : ""}`} aria-label={title} onCancel={onClose} onClick={event => { if (event.target === event.currentTarget) { const box = event.currentTarget.getBoundingClientRect(); if (event.clientX < box.left || event.clientX > box.right) onClose(); } }}><header><h2>{title}</h2><button className="ceo-icon" onClick={onClose} aria-label={`Close ${title}`}>×</button></header>{children}</dialog>;
}

export function Badge({ value }: { value: unknown }) {
  const key = String(value || "");
  return <span className={`ceo-badge ${["LOST", "CRITICAL", "ESCALATED", "DISABLED", "DELETED"].includes(key) ? "danger" : ["WON", "RETAILED", "RESOLVED", "CLOSED", "BOOKED"].includes(key) ? "good" : ""}`}>{label(value)}</span>;
}

export type Column = { key: string; title: string; render?: (row: ReportRow) => ReactNode; numeric?: boolean; optional?: boolean };
export function ReportTable({ columns, rows, caption, onOpen, sort, onSort, loading = false }: { columns: Column[]; rows: ReportRow[]; caption: string; onOpen?: (row: ReportRow) => void; sort?: string; onSort?: (key: string) => void; loading?: boolean }) {
  const [hidden, setHidden] = useState<string[]>(columns.filter(c => c.optional).map(c => c.key));
  const visible = columns.filter(c => !hidden.includes(c.key));
  return <section className="ceo-table-card" aria-busy={loading}><header><h2>{caption}</h2><details className="ceo-columns"><summary>Columns</summary><div>{columns.map(c => <label key={c.key}><input type="checkbox" checked={!hidden.includes(c.key)} disabled={c === columns[0]} onChange={e => setHidden(current => e.target.checked ? current.filter(key => key !== c.key) : [...current, c.key])} />{c.title}</label>)}</div></details></header><div className="ceo-table-scroll"><table><caption className="ceo-sr-only">{caption}</caption><thead><tr>{visible.map(c => <th key={c.key} className={c.numeric ? "number" : ""} scope="col" aria-sort={sort?.replace("-", "") === c.key ? sort.startsWith("-") ? "descending" : "ascending" : undefined}>{onSort && ["name", "status", "branch", "enquiry_date"].includes(c.key) ? <button onClick={() => onSort(c.key)}>{c.title} ↕</button> : c.title}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={text(row.id ?? row.key, String(index))}>{visible.map((c, cell) => <td key={c.key} className={c.numeric ? "number" : ""}>{cell === 0 && onOpen ? <button className="ceo-link" onClick={() => onOpen(row)}>{c.render ? c.render(row) : text(row[c.key])}<span aria-hidden="true"> ↗</span></button> : c.render ? c.render(row) : c.numeric ? count(row[c.key] ?? 0) : text(row[c.key])}</td>)}</tr>)}</tbody></table>{!rows.length && <div className="ceo-empty">{loading ? "Loading report…" : "No records match these filters."}</div>}</div></section>;
}

export function Pagination({ page, total, size = 25, onChange }: { page: number; total: number; size?: number; onChange: (value: number) => void }) {
  return <div className="ceo-pagination"><span>{total ? `${(page - 1) * size + 1}–${Math.min(page * size, total)} of ${count(total)}` : "0 records"}</span><div><button disabled={page <= 1} onClick={() => onChange(page - 1)}>Previous</button><button disabled={page * size >= total} onClick={() => onChange(page + 1)}>Next</button></div></div>;
}

export function SearchField({ value, onSearch }: { value: string; onSearch: (value: string) => void }) {
  const ref = useRef<HTMLInputElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => { if (ref.current && document.activeElement !== ref.current) ref.current.value = value; }, [value]);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  return <label className="ceo-search"><span className="ceo-sr-only">Search customer, phone or ID</span><input ref={ref} type="search" defaultValue={value} placeholder="Search name, phone or ID…" onChange={event => { const next = event.target.value; if (timer.current) clearTimeout(timer.current); timer.current = setTimeout(() => onSearch(next), 250); }} /></label>;
}
