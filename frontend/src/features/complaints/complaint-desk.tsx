"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  createComplaint, getComplaintAnalytics, getComplaintDetail, getComplaints,
  getSystemConfig, updateComplaint,
  type Complaint, type ComplaintAnalytics, type ComplaintDetail, type ComplaintFilters, type ComplaintInput, type CurrentUser,
} from "@/lib/crm";
import { formatDate, formatDateTime } from "@/lib/dates";

// ── Constants ────────────────────────────────────────────────────────────────

const CATEGORIES: [string, string][] = [
  ["SERVICE_DELAY", "Service Delay"],
  ["PRODUCT_DEFECT", "Product Defect"],
  ["DELIVERY_ISSUE", "Delivery Issue"],
  ["BILLING_FINANCE", "Billing / Finance"],
  ["AFTER_SALES", "After-Sales"],
  ["STAFF_BEHAVIOUR", "Staff Behaviour"],
  ["WARRANTY", "Warranty"],
  ["OTHER", "Other"],
];

const PRIORITIES: [string, string][] = [
  ["LOW", "Low"],
  ["MEDIUM", "Medium"],
  ["HIGH", "High"],
  ["CRITICAL", "Critical"],
];

const STATUSES: [string, string][] = [
  ["OPEN", "Open"],
  ["IN_PROGRESS", "In Progress"],
  ["ESCALATED", "Escalated"],
  ["RESOLVED", "Resolved"],
  ["CLOSED", "Closed"],
];

const SOURCES: [string, string][] = [
  ["PHONE", "Phone"],
  ["EMAIL", "Email"],
  ["WALKIN", "Walk-in"],
  ["SOCIAL_MEDIA", "Social Media"],
  ["OTHER", "Other"],
];

const categoryLabel = (v: string) => CATEGORIES.find(([k]) => k === v)?.[1] ?? v;
const priorityLabel = (v: string) => PRIORITIES.find(([k]) => k === v)?.[1] ?? v;
const statusLabel = (v: string) => STATUSES.find(([k]) => k === v)?.[1] ?? v;

const emptyInput = (): ComplaintInput => ({
  customer_name: "", customer_phone: "", customer_email: "",
  category: "", priority: "MEDIUM", subject: "", description: "",
  model_interest: "", branch: "",
});

const formatNoteTime = formatDateTime;

// ── Complaint Desk ────────────────────────────────────────────────────────────

export function ComplaintDesk({ adminView = false, currentUser }: { adminView?: boolean; currentUser?: CurrentUser }) {
  const userRole = currentUser?.role;
  const canCreate = userRole === "CRE";
  const canResolve = userRole === "COMPLAINTS";
  const canUseAnalytics = adminView || canResolve;
  const heading = adminView
    ? {
      eyebrow: "COMPLAINT OVERSIGHT",
      title: <>Keep every <span>complaint moving.</span></>,
      subtext: "Monitor resolution health and complaints department ownership across every branch.",
    }
    : canResolve
      ? {
        eyebrow: "RESOLUTION QUEUE",
        title: <>Resolve every <span>complaint.</span></>,
        subtext: "Work the shared complaints department queue and keep customer updates moving.",
      }
      : {
        eyebrow: "COMPLAINT INTAKE",
        title: <>Log customer <span>complaints.</span></>,
        subtext: "Register complaints and track tickets you logged.",
      };
  // List state
  const [complaints, setComplaints] = useState<Complaint[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<ComplaintFilters>({});
  const [activeFilters, setActiveFilters] = useState<ComplaintFilters>({});
  const [page, setPage] = useState(1);

  // Analytics state
  const [analytics, setAnalytics] = useState<ComplaintAnalytics | null>(null);
  const [analyticsRange, setAnalyticsRange] = useState("mtd");
  const listRequest = useRef(0);

  // Add complaint form
  const [addingComplaint, setAddingComplaint] = useState(false);
  const [newComplaint, setNewComplaint] = useState<ComplaintInput>(emptyInput);
  const [submitting, setSubmitting] = useState(false);
  const [submittedTicket, setSubmittedTicket] = useState<string | null>(null);
  const [formError, setFormError] = useState("");

  // Detail modal
  const [activeComplaint, setActiveComplaint] = useState<Complaint | null>(null);
  const [detail, setDetail] = useState<ComplaintDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [updatingStatus, setUpdatingStatus] = useState(false);
  const [newStatus, setNewStatus] = useState("");
  const [newPriority, setNewPriority] = useState("");
  const [resolutionNotes, setResolutionNotes] = useState("");
  const [detailError, setDetailError] = useState("");

  // System config
  const [models, setModels] = useState<string[]>([]);
  const [branches, setBranches] = useState<string[]>([]);

  // Build query string
  const buildQuery = useCallback(() => {
    const params = new URLSearchParams();
    params.set("page", String(page));
    if (query.trim()) params.set("q", query.trim());
    Object.entries(activeFilters).forEach(([k, v]) => { if (v) params.set(k, v); });
    return `?${params.toString()}`;
  }, [page, query, activeFilters]);

  // Load the list independently; analytics has its own range-aware effect.
  const refresh = useCallback(async () => {
    const request = ++listRequest.current;
    setLoading(true); setError("");
    try {
      const data = await getComplaints(buildQuery());
      if (request !== listRequest.current) return;
      setComplaints(data.results);
      setTotalCount(data.count);
    } catch (e) {
      if (request === listRequest.current) setError(e instanceof Error ? e.message : "Unable to load complaints.");
    } finally { if (request === listRequest.current) setLoading(false); }
  }, [buildQuery]);

  useEffect(() => {
    const t = setTimeout(() => void refresh(), 0);
    return () => clearTimeout(t);
  }, [refresh]);

  // Reload analytics when range changes
  useEffect(() => {
    if (!canUseAnalytics) return;
    void getComplaintAnalytics(analyticsRange).then(setAnalytics).catch(() => null);
  }, [analyticsRange, canUseAnalytics]);

  useEffect(() => {
    const t = setTimeout(() => setActiveFilters({ ...filters }), 250);
    return () => clearTimeout(t);
  }, [filters]);

  useEffect(() => {
    void getSystemConfig().then(c => {
      setModels(c.lists?.models || []);
      setBranches(c.lists?.branches || []);
    }).catch(() => { setModels([]); setBranches([]); });
  }, []);

  // Pagination
  const pageSize = 50;
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

  // ── Add Complaint ──────────────────────────────────────────────────────────

  const submitComplaint = async () => {
    if (submitting) return;
    const { customer_name, customer_phone, category, subject, description, priority, branch } = newComplaint;
    if (!customer_name.trim()) { setFormError("Customer name is required."); return; }
    if (!/^\d{10}$/.test(customer_phone)) { setFormError("Enter a valid 10-digit phone number."); return; }
    if (!category) { setFormError("Select a complaint category."); return; }
    if (!subject.trim()) { setFormError("Enter a complaint subject."); return; }
    if (!description.trim()) { setFormError("Describe the complaint."); return; }
    if (!branch) { setFormError("Select the complaint branch."); return; }
    setSubmitting(true); setFormError("");
    try {
      const created = await createComplaint({ ...newComplaint, customer_name: customer_name.trim(), subject: subject.trim(), description: description.trim() });
      setComplaints(cur => [created, ...cur]);
      setTotalCount(c => c + 1);
      setAddingComplaint(false);
      setNewComplaint(emptyInput());
      setSubmittedTicket(created.ticket_number);
      if (canUseAnalytics) void getComplaintAnalytics(analyticsRange).then(setAnalytics).catch(() => null);
    } catch (e) { setFormError(e instanceof Error ? e.message : "Could not register complaint."); }
    finally { setSubmitting(false); }
  };

  // ── Open Detail ────────────────────────────────────────────────────────────

  const openComplaint = async (c: Complaint) => {
    setActiveComplaint(c);
    setNewStatus(c.status);
    setNewPriority(c.priority);
    setResolutionNotes("");
    setDetailError(""); setDetail(null);
    setDetailLoading(true);
    try { const d = await getComplaintDetail(c.id); setDetail(d); }
    catch { /* modal still usable with list data */ }
    finally { setDetailLoading(false); }
  };

  // ── Save Status Update ─────────────────────────────────────────────────────

  const saveUpdate = async () => {
    if (!activeComplaint || updatingStatus) return;
    if (!resolutionNotes.trim()) {
      setDetailError("Remarks are required before saving an update."); return;
    }
    setUpdatingStatus(true); setDetailError("");
    try {
      const updated = await updateComplaint(activeComplaint.id, {
        status: newStatus, priority: newPriority,
        ...(resolutionNotes.trim() ? { resolution_notes: resolutionNotes.trim() } : {}),
      });
      setComplaints(cur => cur.map(c => c.id === activeComplaint.id ? { ...c, status: updated.status, priority: updated.priority, resolution_notes: updated.resolution_notes } : c));
      setActiveComplaint({ ...activeComplaint, status: updated.status, priority: updated.priority, resolution_notes: updated.resolution_notes });
      if (detail) setDetail({ ...detail, ...updated });
      setNotice(`${activeComplaint.ticket_number} updated.`);
      if (canUseAnalytics) void getComplaintAnalytics(analyticsRange).then(setAnalytics).catch(() => null);
    } catch (e) { setDetailError(e instanceof Error ? e.message : "Update failed."); }
    finally { setUpdatingStatus(false); }
  };

  // ── Analytics Helpers ──────────────────────────────────────────────────────

  const s = analytics?.summary;
  const maxCategory = Math.max(...(analytics?.by_category.map(x => x.count) || [1]), 1);
  const maxTrend = Math.max(...(analytics?.trend.map(x => x.opened) || [1]), 1);
  const priorityColors: Record<string, string> = { LOW: "blue", MEDIUM: "yellow", HIGH: "orange", CRITICAL: "red" };
  const statusColors: Record<string, string> = { OPEN: "open", IN_PROGRESS: "in-progress", ESCALATED: "escalated", RESOLVED: "resolved", CLOSED: "closed" };

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <section className="page complaint-page">
      {/* Header */}
      <div className="complaint-heading">
        <div>
          <p className="eyebrow">{heading.eyebrow}</p>
          <h1>{heading.title}</h1>
          <p className="subtext">{heading.subtext}</p>
        </div>
        {/* Analytics range + add button */}
        <div className="complaint-heading-actions">
          {canUseAnalytics && <select className="filter" value={analyticsRange} onChange={e => setAnalyticsRange(e.target.value)} aria-label="Analytics range">
            <option value="today">Today</option>
            <option value="mtd">Month to date</option>
            <option value="week">Last 7 days</option>
            <option value="all">All time</option>
          </select>}
          {canCreate && <button className="button primary" id="add-complaint-btn" onClick={() => { setFormError(""); setAddingComplaint(true); }}>⚑ Log complaint</button>}
        </div>
      </div>

      {/* Analytics metrics row */}
      {s && (
        <section className="complaint-metrics">
          <article className="sales-metric blue"><span>TOTAL</span><strong>{s.total}</strong><small>All time for range</small></article>
          <article className="sales-metric open-metric"><span>OPEN</span><strong>{s.open}</strong><small>Awaiting action</small></article>
          <article className="sales-metric yellow"><span>IN PROGRESS</span><strong>{s.in_progress}</strong><small>Being handled</small></article>
          <article className="sales-metric red"><span>ESCALATED</span><strong>{s.escalated}</strong><small>Needs urgent attention</small></article>
          <article className="sales-metric green"><span>RESOLVED</span><strong>{s.resolved + s.closed}</strong><small>Closed / Resolved</small></article>
          <article className="sales-metric mint"><span>AVG RESOLUTION</span><strong>{s.avg_resolution_hours > 0 ? `${s.avg_resolution_hours}h` : "—"}</strong><small>Average close time</small></article>
        </section>
      )}

      {/* Analytics charts row */}
      {adminView && analytics && (
        <section className="complaint-analytics-row">
          {/* Category breakdown */}
            <article className="panel complaint-chart-card">
            <header><div><p className="eyebrow">CATEGORY BREAKDOWN</p><h2>What they&apos;re calling about</h2></div></header>
            <div className="complaint-category-list">
              {analytics.by_category.length ? analytics.by_category.map(item => (
                <div className="complaint-cat-row" key={item.category}>
                  <span className={`complaint-cat-badge cat-${item.category.toLowerCase().replace("_", "-")}`}>{categoryLabel(item.category)}</span>
                  <div className="complaint-cat-bar-wrap">
                    <div className="complaint-cat-bar" style={{ width: `${Math.max(3, (item.count / maxCategory) * 100)}%` }} />
                  </div>
                  <b>{item.count}</b>
                </div>
              )) : <p className="subtext" style={{ padding: "1rem 0" }}>No data yet.</p>}
            </div>
          </article>

          {/* Priority distribution */}
          <article className="panel complaint-chart-card">
            <header><div><p className="eyebrow">PRIORITY SPLIT</p><h2>Urgency at a glance</h2></div></header>
            <div className="complaint-priority-grid">
              {analytics.by_priority.map(item => (
                <div className={`complaint-priority-card priority-${(item.priority || "").toLowerCase()}`} key={item.priority}>
                  <span>{priorityLabel(item.priority)}</span>
                  <strong>{item.count}</strong>
                </div>
              ))}
            </div>
          </article>

          {/* Trend */}
          <article className="panel complaint-chart-card">
            <header><div><p className="eyebrow">DAILY TREND</p><h2>Opened vs resolved</h2></div></header>
            <div className="complaint-trend-bars">
              {analytics.trend.length ? analytics.trend.map(item => (
                <div className="complaint-trend-col" key={item.date}>
                  <span className="complaint-trend-val">{item.opened}</span>
                  <div className="complaint-trend-stack">
                    <div className="complaint-trend-bar opened" style={{ height: `${Math.max(4, (item.opened / maxTrend) * 100)}px` }} />
                    <div className="complaint-trend-bar resolved" style={{ height: `${Math.max(0, (item.resolved / maxTrend) * 100)}px`, position: "absolute", bottom: 0 }} />
                  </div>
                  <small>{formatDate(item.date)}</small>
                </div>
              )) : <p className="subtext" style={{ padding: "2rem 0", textAlign: "center" }}>No trend data yet.</p>}
            </div>
            <div className="complaint-trend-legend">
              <span><i className="legend-opened" />Opened</span>
              <span><i className="legend-resolved" />Resolved</span>
            </div>
          </article>
        </section>
      )}

      {adminView && analytics?.by_resolution_team && (
        <section className="panel complaint-cre-performance">
          <header className="panel-heading">
            <div>
              <p className="eyebrow">COMPLAINTS DEPARTMENT</p>
              <h2>Resolution ownership</h2>
            </div>
          </header>
          <div className="table-scroll">
            <table>
              <thead><tr><th>Resolver</th><th>Total</th><th>Open</th><th>In progress</th><th>Escalated</th><th>Resolved</th><th>Rate</th><th>Avg resolution</th></tr></thead>
              <tbody>
                {analytics.by_resolution_team.length ? analytics.by_resolution_team.map(resolver => (
                  <tr key={resolver.id}>
                    <td><b>{resolver.name}</b></td><td>{resolver.total}</td><td>{resolver.open}</td><td>{resolver.in_progress}</td><td>{resolver.escalated}</td><td>{resolver.resolved + resolver.closed}</td><td><span className="status qualified">{resolver.resolution_rate}%</span></td><td>{resolver.avg_resolution_hours ? `${resolver.avg_resolution_hours}h` : "—"}</td>
                  </tr>
                )) : <tr><td colSpan={8}>No complaints department activity for this range.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Toolbar */}
      <section className="panel complaint-toolbar-panel">
        <div className="complaint-toolbar">
          <label className="search"><span>⌕</span><input id="complaint-search" value={query} onChange={e => { setQuery(e.target.value); setPage(1); }} placeholder="Search by name, phone, or ticket…" /></label>
          <div className="complaint-filters">
            <select className="filter" id="filter-status" value={filters.status || ""} onChange={e => setFilters(f => ({ ...f, status: e.target.value || undefined }))} aria-label="Filter by status">
              <option value="">All statuses</option>
              {STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            <select className="filter" id="filter-category" value={filters.category || ""} onChange={e => setFilters(f => ({ ...f, category: e.target.value || undefined }))} aria-label="Filter by category">
              <option value="">All categories</option>
              {CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            <select className="filter" id="filter-priority" value={filters.priority || ""} onChange={e => setFilters(f => ({ ...f, priority: e.target.value || undefined }))} aria-label="Filter by priority">
              <option value="">All priorities</option>
              {PRIORITIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            {Object.values(filters).some(Boolean) && (
              <button className="filter" onClick={() => setFilters({})}>Clear</button>
            )}
          </div>
        </div>
      </section>

      {error && <div className="empty-state">{error}</div>}

      {/* Complaint list */}
      <section className="panel complaint-list-panel">
        <header className="panel-heading">
          <div>
            <p className="eyebrow">COMPLAINT LOG</p>
            <h2>{loading ? "Loading…" : `${totalCount} complaint${totalCount === 1 ? "" : "s"}`}</h2>
          </div>
        </header>
        <div className="complaint-list">
          {!loading && complaints.length === 0 && (
            <div className="empty-state">{canCreate ? "No complaints match this view. Log one with the button above." : "No complaints match this view."}</div>
          )}
          {complaints.map(c => (
            <div className="complaint-row" key={c.id} id={`complaint-row-${c.id}`}>
              <div className="complaint-row-main">
                <span className="complaint-ticket">{c.ticket_number}</span>
                <div>
                  <b>{c.customer_name}</b>
                  <small>{c.customer_phone}{c.customer_email ? ` · ${c.customer_email}` : ""}</small>
                </div>
              </div>
              <span className={`complaint-cat-badge cat-${c.category.toLowerCase().replace("_", "-")}`}>{categoryLabel(c.category)}</span>
              <span className={`complaint-priority priority-${c.priority.toLowerCase()}`}>{priorityLabel(c.priority)}</span>
              <span className={`complaint-status status-${c.status.toLowerCase().replace("_", "-")}`}>{statusLabel(c.status)}</span>
              <div className="complaint-row-meta">
                <small className="complaint-age">{formatDateTime(c.created_at)}</small>
                {c.note_count > 0 && <small className="complaint-notes-count">✎ {c.note_count}</small>}
              </div>
              <button className="row-action" id={`open-complaint-${c.id}`} onClick={() => void openComplaint(c)}>Open →</button>
            </div>
          ))}
        </div>
        {/* Pagination */}
        {totalCount > pageSize && (
          <nav className="lead-pagination" aria-label="Complaint pages">
            <span>Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, totalCount)} of {totalCount}</span>
            <div>
              <button className="filter" disabled={loading || page <= 1} onClick={() => setPage(p => p - 1)}>‹</button>
              <b>Page {page} of {totalPages}</b>
              <button className="filter" disabled={loading || page >= totalPages} onClick={() => setPage(p => p + 1)}>›</button>
            </div>
          </nav>
        )}
      </section>

      {/* Toast */}
      {notice && (
        <div className="toast" role="status">{notice}<button aria-label="Dismiss" onClick={() => setNotice("")}>×</button></div>
      )}

      {/* ── Add Complaint Modal ───────────────────────────────────────────────── */}
      {addingComplaint && canCreate && (
        <div className="modal-layer" role="presentation">
          <section className="modal" role="dialog" aria-modal="true" aria-labelledby="add-complaint-title" style={{ maxWidth: "44rem" }}>
            <button className="modal-close" onClick={() => setAddingComplaint(false)} aria-label="Close">×</button>
            <p className="eyebrow">COMPLAINT INTAKE</p>
            <h2 id="add-complaint-title">Log a complaint</h2>
            <form className="complaint-form" onSubmit={e => { e.preventDefault(); void submitComplaint(); }}>
              <div className="form-grid">
                <label>Customer name<input required maxLength={160} value={newComplaint.customer_name} onChange={e => setNewComplaint(c => ({ ...c, customer_name: e.target.value }))} placeholder="Full name" /></label>
                <label>Phone number<input required inputMode="numeric" pattern="[0-9]{10}" maxLength={10} value={newComplaint.customer_phone} onChange={e => setNewComplaint(c => ({ ...c, customer_phone: e.target.value.replace(/\D/g, "") }))} placeholder="10-digit mobile" /></label>
                <label>Email <small style={{ fontWeight: 400 }}>(optional)</small><input type="email" value={newComplaint.customer_email} onChange={e => setNewComplaint(c => ({ ...c, customer_email: e.target.value }))} placeholder="customer@example.com" /></label>
                <label>Branch<select required value={newComplaint.branch} onChange={e => setNewComplaint(c => ({ ...c, branch: e.target.value }))} disabled={!branches.length}>
                  <option value="">{branches.length ? "Select branch" : "No branches configured"}</option>
                  {branches.map(branch => <option key={branch} value={branch}>{branch}</option>)}
                </select></label>
                <label>Category<select required value={newComplaint.category} onChange={e => setNewComplaint(c => ({ ...c, category: e.target.value }))}>
                  <option value="">Select category</option>
                  {CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select></label>
                <label>Priority<select required value={newComplaint.priority} onChange={e => setNewComplaint(c => ({ ...c, priority: e.target.value }))}>
                  {PRIORITIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select></label>
                <label>Vehicle model <small style={{ fontWeight: 400 }}>(optional)</small>
                  <select value={newComplaint.model_interest} onChange={e => setNewComplaint(c => ({ ...c, model_interest: e.target.value }))} disabled={!models.length}>
                    <option value="">{models.length ? "Select model" : "No models configured"}</option>
                    {models.map(m => <option key={m} value={m}>{m}</option>)}
                  </select>
                </label>
              </div>
              <label className="complaint-full-label" style={{ marginTop: 14 }}>
                Subject
                <input required maxLength={200} value={newComplaint.subject} onChange={e => setNewComplaint(c => ({ ...c, subject: e.target.value }))} placeholder="Brief summary of the complaint" />
              </label>
              <label className="complaint-full-label" style={{ marginTop: 10 }}>
                Description
                <textarea required rows={4} value={newComplaint.description} onChange={e => setNewComplaint(c => ({ ...c, description: e.target.value }))} placeholder="Detailed complaint description as shared by the customer…" />
              </label>
              {formError && <p className="form-error" role="alert">{formError}</p>}
              <p className="subtext">A unique ticket number will be auto-generated on submission.</p>
              <footer>
                <button type="button" className="filter" onClick={() => setAddingComplaint(false)}>Cancel</button>
                <button className="button primary" disabled={submitting}>{submitting ? "Registering…" : "Register complaint"}</button>
              </footer>
            </form>
          </section>
        </div>
      )}

      {/* ── Success Modal ─────────────────────────────────────────────────────── */}
      {submittedTicket && (
        <div className="modal-layer" role="presentation">
          <section className="modal success-modal" role="dialog" aria-modal="true" aria-labelledby="submitted-complaint-title">
            <button className="modal-close" onClick={() => setSubmittedTicket(null)} aria-label="Close">×</button>
            <div className="success-mark" aria-hidden="true">✓</div>
            <p className="eyebrow">COMPLAINT REGISTERED</p>
            <h2 id="submitted-complaint-title">Ticket raised successfully.</h2>
            <p className="subtext">Ticket <strong>{submittedTicket}</strong> has been logged and is now open for follow-up.</p>
            <button className="button primary" onClick={() => setSubmittedTicket(null)}>Done</button>
          </section>
        </div>
      )}

      {/* ── Detail Modal ──────────────────────────────────────────────────────── */}
      {activeComplaint && (
        <div className="modal-layer" role="presentation">
          <section className="modal complaint-detail-modal" role="dialog" aria-modal="true" aria-labelledby="complaint-detail-title">
            {/* Header */}
            <header className="sales-detail-header">
              <div>
                <p className="eyebrow">COMPLAINT DETAIL</p>
                <h2 id="complaint-detail-title">{activeComplaint.ticket_number}</h2>
                <p className="subtext">{activeComplaint.subject}</p>
              </div>
              <button className="modal-close" onClick={() => { setActiveComplaint(null); setDetail(null); }} aria-label="Close">×</button>
            </header>

            <div className="sales-detail-scroll">
              {detailError && <p className="form-error" role="alert">{detailError}</p>}

              {/* Customer info card */}
              <section className="sales-info-card">
                <h3>Customer information</h3>
                <div className="complaint-info-grid">
                  <span><small>Name</small><b>{activeComplaint.customer_name}</b></span>
                  <span><small>Phone</small><b>{activeComplaint.customer_phone}</b></span>
                  {activeComplaint.customer_email && <span><small>Email</small><b>{activeComplaint.customer_email}</b></span>}
                  <span><small>Source</small><b>{SOURCES.find(([v]) => v === activeComplaint.source)?.[1] ?? activeComplaint.source}</b></span>
                  <span><small>Branch</small><b>{activeComplaint.branch}</b></span>
                  {activeComplaint.model_interest && <span><small>Vehicle</small><b>{activeComplaint.model_interest}</b></span>}
                  <span><small>Logged by</small><b>{activeComplaint.logged_by_name}</b></span>
                </div>
                <div className="complaint-description-block">
                  <small>Description</small>
                  <p>{activeComplaint.description}</p>
                </div>
              </section>

              {/* Status update card */}
              {canResolve && <section className="sales-form-card">
                <h3>Update complaint</h3>
                <div className="sales-form-grid">
                  <label>Status
                    <select id="detail-status" value={newStatus} onChange={e => setNewStatus(e.target.value)}>
                      {STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                    </select>
                  </label>
                  <label>Priority
                    <select id="detail-priority" value={newPriority} onChange={e => setNewPriority(e.target.value)}>
                      {PRIORITIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                    </select>
                  </label>
                </div>
                <label className="sales-full-label" style={{ marginTop: 12 }}>
                  Remarks <span style={{ color: "#e04545" }}>*</span>
                  <textarea id="resolution-notes" rows={3} required value={resolutionNotes} onChange={e => setResolutionNotes(e.target.value)} placeholder="Add the progress remark" />
                </label>
                <footer style={{ display: "flex", justifyContent: "flex-end", marginTop: 14 }}>
                  <button className="button primary" id="save-complaint-update" onClick={() => void saveUpdate()} disabled={updatingStatus}>
                    {updatingStatus ? "Saving…" : "Save update"}
                  </button>
                </footer>
              </section>}

              {/* Remarks & Timeline */}
              <section className="sales-history">
                <h3>Remarks & Timeline</h3>

                {detailLoading && <p className="subtext" style={{ marginTop: 12 }}>Loading remarks...</p>}

                {detail?.notes && detail.notes.length > 0 && (
                  <div style={{ marginTop: 14 }}>
                    {detail.notes.map(n => (
                      <div className="sales-history-row" key={n.id}>
                        <div className="history-dot" />
                        <div>
                          <b>{n.content}</b>
                          <small>{n.author_name}</small>
                          <time style={{ fontSize: 10, color: "#92979e" }}>{formatNoteTime(n.created_at)}</time>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {detail && detail.notes.length === 0 && !detailLoading && (
                  <p className="subtext" style={{ marginTop: 12 }}>No remarks yet.</p>
                )}
              </section>
            </div>
          </section>
        </div>
      )}
    </section>
  );
}
