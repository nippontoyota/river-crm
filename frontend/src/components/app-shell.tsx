"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { cacheCurrentUser, clearCachedCurrentUser, getCachedCurrentUser, getCurrentUser, logout, type CurrentUser } from "@/lib/crm";
import { ServiceBell } from "@/components/service-bell";
import { canAddService } from "@/lib/service";
import { FeedbackBell } from "@/components/feedback-bell";
import { formatDate, formatWeekday } from "@/lib/dates";

type AppShellProps = { children: ReactNode; role: "Meta Uploader" | "Service Department" | "CEO" | "Admin" | "Sales officer" | "Sales manager" | "Receptionist" | "Feedback Caller" };

function roleType(user: CurrentUser) {
  if (user.role === "META_UPLOADER") return "Meta Uploader";
  if (user.role === "SERVICE") return "Service Department";
  if (user.role === "FEEDBACK") return "Feedback Caller";
  if (user.role === "CEO") return "CEO";
  if (user.role === "ADMIN") return "Admin";
  if (user.role === "SALES_MANAGER") return "Sales manager";
  if (user.role === "RECEPTIONIST") return "Receptionist";
  return "Sales officer";
}

const uploadLinks = [["/bulk-upload", "Bulk upload", "↑"]] as const;
const serviceLinks = [["/services", "Services", "⚒"]] as const;
const ceoLinks = [
  ["/services", "Services", "⚒"],
  ["/ceo/feedback", "Feedback", "◷"], ["/ceo", "Overview", "◱"], ["/ceo/branches", "Branches", "▦"], ["/ceo/people", "People", "◬"],
  ["/ceo/leads", "Leads & follow-ups", "☷"], ["/ceo/markets", "Markets", "◎"], ["/ceo/operations", "Complaints", "◫"],
] as const;
const feedbackLinks = [["/feedback", "Feedback calls", "◷"]] as const;
const adminLinks = [
  ["/call-center", "Call center review", "☎"],
  ["/services", "Services", "⚒"],
  ["/feedback", "Feedback", "◷"],
  ["/business-controls", "Targets & finance", "◫"],
  ["/analytics", "Analytics", "◱"],
  ["/complaints", "Complaints", "⚑"],
  ["/team", "Users", "◬"],
  ["/lists", "Lists", "▤"],
  ["/lead-intake", "Lead intake", "↓"],
  ["/leads", "Assignment", "▦"],
  ["/all-leads", "All leads", "☷"],
] as const;
const officerLinks = [
  ["/my-leads", "Fresh leads", "◫"],
  ["/follow-ups", "Today's follow-ups", "◷"],
  ["/all-my-leads", "All leads", "☰"],
  ["/my-analytics", "My results", "◔"],
] as const;
const managerLinks = [
  ["/feedback", "Feedback", "◷"],
  ["/manager/analytics", "Analytics", "◱"],
  ["/manager/leads", "Branch leads", "☷"],
] as const;
const creLinks = [
  ["/services", "Services", "⚒"],
  ["/my-leads", "My assigned leads", "◫"],
  ["/call-center", "Call center / All customers", "☎"],
  ["/follow-ups", "Follow-ups", "◷"],
  ["/complaints", "Complaints", "⚑"],
  ["/my-analytics", "My results", "◔"],
] as const;
const complaintLinks = [
  ["/complaints", "Complaints", "⚑"],
] as const;
const receptionistLinks = [
  ["/receptionist-dashboard", "Dashboard", "◱"],
  ["/capture", "Capture Lead", "＋"],
  ["/complaints", "Complaints", "⚑"],
] as const;

export function AppShell({ children, role }: AppShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const cachedUser = getCachedCurrentUser();
  const cachedUserMatches = cachedUser && roleType(cachedUser) === role;
  const [user, setUser] = useState<CurrentUser | null>(cachedUserMatches ? cachedUser : null);
  const [checkingAccess, setCheckingAccess] = useState(true);
  const [sessionConflict, setSessionConflict] = useState<CurrentUser | null>(null);
  useEffect(() => {
    void getCurrentUser().then(result => {
      const actual = result.user;
      cacheCurrentUser(actual);
      if (role === "Sales officer" && actual.role === "SO" && pathname === "/complaints") {
        router.replace("/my-leads");
        return;
      }
      if (role === "Sales officer" && actual.role === "COMPLAINTS" && pathname !== "/complaints") {
        router.replace("/complaints");
        return;
      }
      if (role !== roleType(actual)) {
        setSessionConflict(actual);
      } else {
        setUser(actual);
      }
    }).catch(() => { clearCachedCurrentUser(); router.replace("/"); }).finally(() => setCheckingAccess(false));
  }, [pathname, role, router]);
  const displayName = user ? `${user.first_name} ${user.last_name}`.trim() || user.email : "Sign in";
  const initials = user ? `${user.first_name[0] || ""}${user.last_name[0] || ""}` || user.email.slice(0, 2).toUpperCase() : "?";
  const workspaceRole = user?.role === "CRE" ? "CE" : user?.role === "SO" ? "PS/SO" : user?.role === "SALES_MANAGER" ? "Sales Manager" : user?.role === "RECEPTIONIST" ? "Receptionist" : user?.role === "COMPLAINTS" ? "Complaints department" : role;
  const links = role === "Meta Uploader" ? uploadLinks : role === "Service Department" ? serviceLinks : role === "Feedback Caller" ? feedbackLinks : role === "CEO" ? ceoLinks : role === "Admin" ? adminLinks : role === "Sales manager" ? managerLinks : role === "Sales officer" ? user?.role === "CRE" ? creLinks : user?.role === "COMPLAINTS" ? complaintLinks : officerLinks : receptionistLinks;
  const shellRoleClass = role === "Feedback Caller" ? "feedback-shell" : role === "CEO" ? "ceo-shell" : role === "Sales manager" ? "manager-shell" : role === "Sales officer" ? user?.role === "SO" ? "ps-shell" : user?.role === "COMPLAINTS" ? "complaints-shell" : "cre-shell" : role === "Receptionist" ? "receptionist-shell" : "";
  const signOut = async () => {
    try { await logout(); }
    finally { clearCachedCurrentUser(); router.replace("/"); }
  };

  if (checkingAccess) return null;

  if (sessionConflict) {
    const actualRole = sessionConflict.role === "META_UPLOADER" ? "Meta Uploader" : sessionConflict.role === "SERVICE" ? "Service Department" : sessionConflict.role === "FEEDBACK" ? "Feedback Caller" : sessionConflict.role === "CEO" ? "CEO" : sessionConflict.role === "ADMIN" ? "Admin" : sessionConflict.role === "SALES_MANAGER" ? "Sales Manager" : sessionConflict.role === "RECEPTIONIST" ? "Receptionist" : sessionConflict.role === "CRE" ? "CE" : sessionConflict.role === "COMPLAINTS" ? "Complaints department" : "PS/SO";
    const actualHome = sessionConflict.role === "META_UPLOADER" ? "/bulk-upload" : sessionConflict.role === "SERVICE" ? "/services" : sessionConflict.role === "FEEDBACK" ? "/feedback" : sessionConflict.role === "CEO" ? "/ceo" : sessionConflict.role === "ADMIN" ? "/leads" : sessionConflict.role === "SALES_MANAGER" ? "/manager/analytics" : sessionConflict.role === "RECEPTIONIST" ? "/receptionist-dashboard" : sessionConflict.role === "COMPLAINTS" ? "/complaints" : "/my-leads";
    const actualName = `${sessionConflict.first_name} ${sessionConflict.last_name}`.trim() || sessionConflict.email;
    return (
      <main className="page" style={{ maxWidth: "32rem", margin: "6rem auto", textAlign: "center" }}>
        <div className="panel" style={{ padding: "2rem", display: "grid", gap: "1rem" }}>
          <p className="eyebrow">SESSION CONFLICT</p>
          <h2 style={{ margin: 0 }}>Signed in as a different user</h2>
          <p className="subtext" style={{ margin: 0 }}>
            You signed in as <strong>{actualName}</strong> ({actualRole}) in another tab.
            That session replaced this one.
          </p>
          <div style={{ display: "flex", gap: "0.75rem", justifyContent: "center", marginTop: "0.5rem" }}>
            <button className="button primary" onClick={() => router.replace(actualHome)}>Continue as {actualRole}</button>
            <button className="button" onClick={() => void signOut()}>Sign in again</button>
          </div>
        </div>
      </main>
    );
  }

  const homeHref = role === "Meta Uploader" ? "/bulk-upload" : role === "Service Department" ? "/services" : role === "Feedback Caller" ? "/feedback" : role === "CEO" ? "/ceo" : role === "Admin" ? "/leads" : role === "Sales manager" ? "/manager/analytics" : role === "Receptionist" ? "/receptionist-dashboard" : user?.role === "COMPLAINTS" ? "/complaints" : "/my-leads";

  return <div className={`app-shell ${["Sales officer", "Sales manager"].includes(role) ? "sales-shell" : ""} ${shellRoleClass}`}>
    <aside className="sidebar">
      <Link className="brand" href={homeHref} aria-label="Incheon Mobility ITS home">
        <span className="sidebar-wordmark-full"><strong>Incheon</strong> Mobility<small className="sidebar-product">ITS</small></span>
        <span className="sidebar-wordmark-short" aria-hidden="true">ITS</span>
      </Link>
      <p className="workspace-label">{role === "Admin" ? "SALES CONTROL" : `${workspaceRole} WORKSPACE`}</p>
      <nav className="nav" aria-label="Main navigation">
        {links.map(([href, label, icon]) => <Link key={href} className={`nav-link ${pathname === href ? "active" : ""}`} href={href} onClick={event => {
          if (role !== "CEO" || event.metaKey || event.ctrlKey) return;
          event.preventDefault();
          const current = new URLSearchParams(window.location.search);
          const next = new URLSearchParams();
          for (const key of ["branch", "range", "date_from", "date_to", "mode", "role", "employee"]) current.getAll(key).forEach(value => next.append(key, value));
          router.push(`${href}${next.size ? `?${next}` : ""}`);
        }}><span>{icon}</span><b>{label}</b></Link>)}
      </nav>
      <div className="sidebar-footer">
        <Link className="support" href="#support"><span>?</span><p>Need a hand?<small>Open the operator guide</small></p></Link>
        <div className="user-card"><div className={`avatar ${role === "Admin" ? "orange" : "blue"}`}>{initials}</div><p><b>{displayName}</b><small>{user ? workspaceRole : "Authenticate to continue"}</small></p><button onClick={() => void signOut()}>Sign out</button></div>
      </div>
    </aside>
    <main className="main-content">
      <header className="topbar"><div><b><span className="mobile-product">ITS · </span>{role === "Meta Uploader" ? "Bulk lead uploads" : role === "Service Department" ? "Branch services" : role === "CEO" ? "Company performance" : role === "Admin" ? "Lead control" : role === "Sales manager" ? "Branch command" : role === "Receptionist" ? "Front Desk" : user?.role === "COMPLAINTS" ? "Complaint queue" : user?.role === "SO" ? displayName : role === "Feedback Caller" ? "Customer feedback" : `${workspaceRole} pipeline`}</b><small>{formatWeekday(new Date())}, {formatDate(new Date())}</small></div><div className="top-actions">{user && canAddService(user) && <button className="button primary" onClick={() => pathname === "/services" ? window.dispatchEvent(new Event("service:create")) : router.push("/services?addService=1")}>＋ Add service</button>}{user && ["SERVICE", "CRE"].includes(user.role) && <ServiceBell />}{user && ["FEEDBACK", "ADMIN", "SALES_MANAGER"].includes(user.role) && <FeedbackBell />}{role === "Admin" && pathname !== "/complaints" && <button className="button primary" onClick={() => ["/leads", "/all-leads"].includes(pathname) ? window.dispatchEvent(new Event("incheon:add-lead")) : router.push("/leads?addLead=1")}>＋ Add lead</button>}<button className="mobile-signout" onClick={() => void signOut()} aria-label="Sign out" title="Sign out">↪</button></div></header>
      {children}
    </main>
  </div>;
}
