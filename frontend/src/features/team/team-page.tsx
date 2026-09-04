"use client";

import { useCallback, useEffect, useMemo, useState, FormEvent } from "react";
import { createUser, disableUser, enableUser, getOffboardingImpact, getSystemConfig, getUsers, permanentlyDeleteUser, type CurrentUser, type OffboardingImpact, type OffboardingRoute } from "@/lib/crm";

const roleOptions = [
  { value: "ADMIN", label: "Administrator" },
  { value: "CRE", label: "Marketing" },
  { value: "SO", label: "PS/SO" },
  { value: "SALES_MANAGER", label: "Sales Manager" },
  { value: "COMPLAINTS", label: "Complaints department" },
  { value: "RECEPTIONIST", label: "Receptionist" },
];

const noBranch = "__NO_BRANCH__";

export function TeamPage() {
  const [usersRaw, setUsers] = useState<CurrentUser[]>([]);
  const users = useMemo(() => Array.isArray(usersRaw) ? usersRaw : ((usersRaw as any).results || []) as CurrentUser[], [usersRaw]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [branches, setBranches] = useState<string[]>([]);
  const [selectedRole, setSelectedRole] = useState("");
  const [roleFilter, setRoleFilter] = useState("ALL");
  const [branchFilter, setBranchFilter] = useState("ALL");
  const [statusFilter, setStatusFilter] = useState("ACTIVE");
  const [query, setQuery] = useState("");
  const [offboarding, setOffboarding] = useState<{ user: CurrentUser; action: "DISABLE" | "DELETE"; impact: OffboardingImpact } | null>(null);
  const [routes, setRoutes] = useState<Partial<Record<string, OffboardingRoute>>>({});
  const [reason, setReason] = useState("");
  const [lifecycleBusy, setLifecycleBusy] = useState("");

  const loadUsers = useCallback(() => {
    getUsers()
      .then(setUsers)
      .catch(err => setError(err instanceof Error ? err.message : "Failed to load users."));
  }, []);

  useEffect(() => {
    loadUsers();
    getSystemConfig().then(config => setBranches(config.lists?.branches || []));
  }, [loadUsers]);

  const onSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    const form = e.currentTarget;
    const formData = new FormData(form);
    
    // Map UI roles to Backend roles
    const uiRole = formData.get("role") as string;
    let backendRole = "ADMIN";
    if (uiRole === "Marketing") backendRole = "CRE";
    if (uiRole === "PS/SO") backendRole = "SO";
    if (uiRole === "Sales Manager") backendRole = "SALES_MANAGER";
    if (uiRole === "Complaints department") backendRole = "COMPLAINTS";
    if (uiRole === "Receptionist") backendRole = "RECEPTIONIST";

    const payload: Record<string, string | boolean> = {
      first_name: formData.get("firstName") as string,
      last_name: formData.get("lastName") as string,
      email: formData.get("email") as string,
      password: formData.get("password") as string,
      role: backendRole,
      is_active: true
    };
    
    if (["SO", "SALES_MANAGER"].includes(backendRole)) {
      payload.location = formData.get("branch") as string;
    }

    try {
      await createUser(payload);
      form.reset();
      setSelectedRole("");
      loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create user.");
    } finally {
      setLoading(false);
    }
  };

  const openOffboarding = async (user: CurrentUser, action: "DISABLE" | "DELETE") => {
    setLifecycleBusy(`${action}-${user.id}`); setError("");
    try {
      const impact = await getOffboardingImpact(user.id);
      setRoutes({});
      setReason("");
      setOffboarding({ user, action, impact });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not inspect this employee's workload.");
    } finally { setLifecycleBusy(""); }
  };

  const handleEnable = async (user: CurrentUser) => {
    if (!confirm(`Enable ${`${user.first_name} ${user.last_name}`.trim() || user.email}? Previously routed work will not return.`)) return;
    setLifecycleBusy(`ENABLE-${user.id}`); setError("");
    try { await enableUser(user.id); loadUsers(); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed to enable user."); }
    finally { setLifecycleBusy(""); }
  };

  const setDestination = (status: string, destination: OffboardingRoute["destination"]) => {
    setRoutes(current => ({ ...current, [status]: { status, destination, recipient_ids: destination === "POOL" ? [] : current[status]?.recipient_ids || [] } }));
  };

  const toggleRecipient = (status: string, recipientId: number) => {
    setRoutes(current => {
      const route = current[status];
      if (!route) return current;
      const recipient_ids = route.recipient_ids.includes(recipientId) ? route.recipient_ids.filter(id => id !== recipientId) : [...route.recipient_ids, recipientId];
      return { ...current, [status]: { ...route, recipient_ids } };
    });
  };

  const confirmOffboarding = async () => {
    if (!offboarding) return;
    const payload = offboarding.impact.lead_groups.map(group => routes[group.status]).filter((route): route is OffboardingRoute => Boolean(route));
    setLifecycleBusy(`${offboarding.action}-${offboarding.user.id}`); setError("");
    try {
      if (offboarding.action === "DELETE") await permanentlyDeleteUser(offboarding.user.id, offboarding.impact.version, payload, reason.trim());
      else await disableUser(offboarding.user.id, offboarding.impact.version, payload);
      setOffboarding(null); loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to ${offboarding.action === "DELETE" ? "delete" : "disable"} user.`);
      try {
        const impact = await getOffboardingImpact(offboarding.user.id);
        setOffboarding(current => current ? { ...current, impact } : current);
        setRoutes({});
      } catch { /* The account may have completed in another session. */ }
    } finally { setLifecycleBusy(""); }
  };

  const displayRole = (role: string) => {
    if (role === "CRE") return "Marketing";
    if (role === "SO") return "PS/SO";
    if (role === "SALES_MANAGER") return "Sales Manager";
    if (role === "COMPLAINTS") return "Complaints department";
    if (role === "RECEPTIONIST") return "Receptionist";
    return "Administrator";
  };

  const branchLabel = (user: CurrentUser) => user.location?.trim() || "No branch";
  const branchOptions = useMemo(() => Array.from(new Set([...branches, ...users.map(user => user.location?.trim()).filter(Boolean) as string[]])).sort(), [branches, users]);
  const filteredUsers = users.filter(user => {
    const isActive = user.is_active !== false;
    const branch = user.location?.trim();
    const text = `${user.first_name} ${user.last_name} ${user.email} ${displayRole(user.role)} ${branch || "No branch"}`.toLowerCase();
    if (statusFilter === "ACTIVE" && !isActive) return false;
    if (statusFilter === "DISABLED" && isActive) return false;
    if (roleFilter !== "ALL" && user.role !== roleFilter) return false;
    if (branchFilter === noBranch && branch) return false;
    if (branchFilter !== "ALL" && branchFilter !== noBranch && branch !== branchFilter) return false;
    return !query.trim() || text.includes(query.trim().toLowerCase());
  });

  return (
    <section className="page team-admin-page">
      <div className="page-heading compact">
        <div>
          <h1>Users <span>Administrator</span></h1>
          <p className="subtext">Create team accounts and scan active access by role and branch.</p>
        </div>
      </div>
      
      {error && <div className="empty-state">{error}</div>}

      <div className="team-workspace">
        <article className="panel team-create-panel">
          <header className="panel-heading">
            <div>
              <p className="eyebrow">ADMIN TOOL</p>
              <h2>Create user</h2>
            </div>
          </header>
          <form onSubmit={onSubmit} className="team-create-form">
            <label>Full name *
              <div className="team-name-fields">
                <input name="firstName" required placeholder="First name" />
                <input name="lastName" placeholder="Last name" />
              </div>
            </label>
            <label>Username *
              <input type="email" name="email" required placeholder="Email address" />
            </label>
            <div className="team-form-pair">
              <label>Password (min 6 characters)
                <input type="password" name="password" required minLength={6} />
              </label>
              <label>Role *
                <select name="role" required value={selectedRole} onChange={e => setSelectedRole(e.target.value)}>
                  <option value="">Select...</option>
                  <option value="Admin">Admin</option>
                  <option value="Marketing">Marketing (CRE)</option>
                  <option value="PS/SO">PS/SO</option>
                  <option value="Sales Manager">Sales Manager</option>
                  <option value="Complaints department">Complaints department</option>
                  <option value="Receptionist">Receptionist</option>
                </select>
              </label>
            </div>
            {["PS/SO", "Sales Manager"].includes(selectedRole) && (
              <label>Branch *
                <select name="branch" required>
                  <option value="">Select branch...</option>
                  {branches.map(branch => <option key={branch} value={branch}>{branch}</option>)}
                </select>
              </label>
            )}
            <button type="submit" className="button primary team-submit" disabled={loading}>
              {loading ? "Creating..." : "Create user"}
            </button>
          </form>
        </article>

        <article className="panel team-users-panel">
          <header className="panel-heading team-users-heading">
            <div>
              <p className="eyebrow">TEAM DIRECTORY</p>
              <h2>Users</h2>
            </div>
            <b>Showing {filteredUsers.length} of {users.length}</b>
          </header>

          <div className="team-filters" aria-label="User filters">
            <label className="team-search">
              <span>Search</span>
              <input value={query} onChange={event => setQuery(event.target.value)} placeholder="Name, email, role, branch" />
            </label>
            <label>
              <span>Role</span>
              <select value={roleFilter} onChange={event => setRoleFilter(event.target.value)}>
                <option value="ALL">All roles</option>
                {roleOptions.map(role => <option key={role.value} value={role.value}>{role.label}</option>)}
              </select>
            </label>
            <label>
              <span>Branch</span>
              <select value={branchFilter} onChange={event => setBranchFilter(event.target.value)}>
                <option value="ALL">All branches</option>
                {branchOptions.map(branch => <option key={branch} value={branch}>{branch}</option>)}
                <option value={noBranch}>No branch</option>
              </select>
            </label>
            <label>
              <span>Status</span>
              <select value={statusFilter} onChange={event => setStatusFilter(event.target.value)}>
                <option value="ACTIVE">Active</option>
                <option value="DISABLED">Disabled</option>
                <option value="ALL">All</option>
              </select>
            </label>
          </div>

          <div className="team-user-table">
            <div className="team-user-head" aria-hidden="true">
              <span>User</span>
              <span>Role</span>
              <span>Branch</span>
              <span>Status</span>
              <span>Action</span>
            </div>
            <div className="team-users-scroll">
              {filteredUsers.length ? filteredUsers.map(user => {
                const isActive = user.is_active !== false;
                const managed = ["CRE", "SO"].includes(user.role);
                return (
                  <div className="team-user-row" key={user.id}>
                    <div className="team-user-main">
                      <b>{`${user.first_name} ${user.last_name}`.trim() || user.email}</b>
                      <small>@{user.email.split("@")[0]} · {user.email}</small>
                    </div>
                    <span>{displayRole(user.role)}</span>
                    <span>{branchLabel(user)}</span>
                    <span className={`team-status ${isActive ? "active" : "disabled"}`}>{isActive ? "Active" : "Disabled"}</span>
                    {managed ? <div className="team-row-actions">
                      {isActive ? <button className="filter" disabled={Boolean(lifecycleBusy)} onClick={() => void openOffboarding(user, "DISABLE")}>Disable</button> : <button className="filter team-enable" disabled={Boolean(lifecycleBusy)} onClick={() => void handleEnable(user)}>Enable</button>}
                      <button className="filter team-delete" disabled={Boolean(lifecycleBusy)} onClick={() => void openOffboarding(user, "DELETE")}>{lifecycleBusy === `DELETE-${user.id}` ? "Loading…" : "Delete"}</button>
                    </div> : <span className="team-muted">Not available</span>}
                  </div>
                );
              }) : <div className="empty-state">No users match these filters.</div>}
            </div>
          </div>
        </article>
      </div>

      {offboarding && <div className="modal-layer" role="presentation"><section className="modal team-offboarding-modal" role="dialog" aria-modal="true" aria-labelledby="offboarding-title">
        <button className="modal-close" onClick={() => setOffboarding(null)} aria-label="Close">×</button>
        <p className="eyebrow">{offboarding.action === "DELETE" ? "PERMANENT ACCOUNT REMOVAL" : "TEMPORARY ACCESS PAUSE"}</p>
        <h2 id="offboarding-title">{offboarding.action === "DELETE" ? "Delete" : "Disable"} {`${offboarding.user.first_name} ${offboarding.user.last_name}`.trim() || offboarding.user.email}</h2>
        <p className="team-offboarding-copy">Lead stages and history stay unchanged. Decide where each active status group goes before access is removed.</p>
        <div className="team-impact-strip">
          <span><b>{offboarding.impact.actionable_count}</b> active leads</span>
          <span><b>{offboarding.impact.closed_count}</b> closed retained</span>
          <span><b>{offboarding.impact.followup_count}</b> follow-ups held</span>
          <span><b>{offboarding.impact.complaint_count}</b> complaints pooled</span>
        </div>
        <div className="team-route-list">
          {offboarding.impact.lead_groups.map(group => {
            const route = routes[group.status];
            return <article className="team-route-card" key={group.status}>
              <header><div><span className="team-route-status">{group.label}</span><b>{group.count} lead{group.count === 1 ? "" : "s"}</b></div><small>{group.branches.join(" · ")}</small></header>
              <div className="team-route-choice">
                <button className={route?.destination === "POOL" ? "active" : ""} onClick={() => setDestination(group.status, "POOL")}>Needs reassignment pool</button>
                <button className={route?.destination === "DISTRIBUTE" ? "active" : ""} onClick={() => setDestination(group.status, "DISTRIBUTE")}>Distribute now</button>
              </div>
              {route?.destination === "DISTRIBUTE" && <div className="team-recipient-grid">
                {offboarding.impact.eligible_users.length ? offboarding.impact.eligible_users.map(candidate => <label key={candidate.id} className={route.recipient_ids.includes(candidate.id) ? "selected" : ""}>
                  <input type="checkbox" checked={route.recipient_ids.includes(candidate.id)} onChange={() => toggleRecipient(group.status, candidate.id)} />
                  <span><b>{candidate.name}</b><small>{offboarding.impact.assignment_role === "SO" ? candidate.location || "No branch" : `${candidate.load} active leads`}</small></span>
                  <em>{candidate.load}</em>
                </label>) : <p>No active same-role replacements are available. Use the pool.</p>}
              </div>}
              {route?.destination === "DISTRIBUTE" && offboarding.impact.assignment_role === "SO" && <p className="team-route-note">Only branch-matched PS/SO employees receive leads; unmatched branches stay in the pool.</p>}
            </article>;
          })}
          {!offboarding.impact.lead_groups.length && <div className="team-no-work">No active leads need routing. Closed history remains attached to this employee.</div>}
        </div>
        {offboarding.action === "DELETE" && <label className="team-delete-reason">Reason for permanent deletion *<textarea maxLength={500} value={reason} onChange={event => setReason(event.target.value)} placeholder="Record why this account is being permanently removed" /></label>}
        {error && <p className="form-error" role="alert">{error}</p>}
        <footer><button className="filter" onClick={() => setOffboarding(null)}>Cancel</button><button className={`button ${offboarding.action === "DELETE" ? "team-confirm-delete" : "primary"}`} disabled={Boolean(lifecycleBusy) || (offboarding.action === "DELETE" && !reason.trim()) || offboarding.impact.lead_groups.some(group => !routes[group.status] || (routes[group.status]?.destination === "DISTRIBUTE" && !routes[group.status]?.recipient_ids.length))} onClick={() => void confirmOffboarding()}>{lifecycleBusy ? "Working…" : offboarding.action === "DELETE" ? "Permanently delete" : "Disable account"}</button></footer>
      </section></div>}

      <style>{`
        .team-admin-page {
          max-width: none;
          min-height: calc(100vh - 83px);
          padding-bottom: 24px;
        }
        .team-workspace {
          display: grid;
          grid-template-columns: minmax(320px, 420px) minmax(560px, 1fr);
          gap: 18px;
          align-items: start;
        }
        .team-create-panel,
        .team-users-panel {
          border-radius: 8px;
        }
        .team-create-panel {
          position: sticky;
          top: 20px;
        }
        .team-create-form {
          display: grid;
          gap: 13px;
          margin-top: 18px;
        }
        .team-create-form label,
        .team-filters label {
          display: grid;
          gap: 6px;
          color: #666b71;
          font-size: 10px;
          font-weight: bold;
        }
        .team-create-form input,
        .team-create-form select,
        .team-filters input,
        .team-filters select {
          min-width: 0;
          border: 1px solid #dededb;
          border-radius: 6px;
          background: #fff;
          color: var(--ink);
          font: 11px Arial, sans-serif;
          outline-color: var(--accent);
          padding: 10px;
        }
        .team-name-fields,
        .team-form-pair {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 10px;
        }
        .team-submit {
          width: 100%;
          margin-top: 7px;
        }
        .team-users-panel {
          display: flex;
          flex-direction: column;
          min-height: 0;
          max-height: calc(100vh - 172px);
          padding: 0;
          overflow: hidden;
        }
        .team-users-heading {
          padding: 20px 20px 16px;
          border-bottom: 1px solid var(--line);
        }
        .team-users-heading b {
          color: #6e737a;
          font: 10px ui-monospace, SFMono-Regular, Menlo, monospace;
          margin-top: 4px;
        }
        .team-filters {
          display: grid;
          grid-template-columns: minmax(220px, 1.4fr) minmax(130px, .8fr) minmax(150px, .9fr) minmax(110px, .65fr);
          gap: 10px;
          padding: 14px 20px;
          border-bottom: 1px solid var(--line);
          background: #fbfbf8;
        }
        .team-filters span {
          color: #8d9299;
          font: 9px ui-monospace, SFMono-Regular, Menlo, monospace;
          letter-spacing: .7px;
          text-transform: uppercase;
        }
        .team-user-table {
          min-height: 0;
        }
        .team-user-head,
        .team-user-row {
          display: grid;
          grid-template-columns: minmax(190px, 1.35fr) minmax(105px, .65fr) minmax(105px, .65fr) 78px minmax(146px, .85fr);
          gap: 12px;
          align-items: center;
        }
        .team-user-head {
          padding: 12px 20px 10px;
          color: #94999f;
          font: 9px ui-monospace, SFMono-Regular, Menlo, monospace;
          letter-spacing: .5px;
          text-transform: uppercase;
          border-bottom: 1px solid #efeeeb;
        }
        .team-users-scroll {
          max-height: calc(100vh - 334px);
          min-height: 300px;
          overflow-y: auto;
        }
        .team-user-row {
          padding: 13px 20px;
          border-bottom: 1px solid #f1f0ed;
          color: #555b63;
          font-size: 11px;
        }
        .team-user-main b {
          display: block;
          color: #25272b;
          font-size: 12px;
        }
        .team-user-main small {
          display: block;
          margin-top: 3px;
          color: #93989e;
          font: 9px ui-monospace, SFMono-Regular, Menlo, monospace;
          overflow-wrap: anywhere;
        }
        .team-status {
          width: max-content;
          border-radius: 4px;
          padding: 4px 7px;
          font: 9px ui-monospace, SFMono-Regular, Menlo, monospace;
        }
        .team-status.active {
          background: #e8f6ef;
          color: #257453;
        }
        .team-status.disabled {
          background: #f8eeee;
          color: #b04a4a;
        }
        .team-muted {
          color: #999da3;
          font: 10px ui-monospace, SFMono-Regular, Menlo, monospace;
        }
        .team-row-actions { display: flex; gap: 6px; justify-content: flex-end; }
        .team-row-actions .filter { padding: 7px 9px; }
        .team-row-actions .team-enable { color: #257453; border-color: #b9dfcf; }
        .team-row-actions .team-delete { color: #ae3f3f; border-color: #eccaca; }
        .team-offboarding-modal { width: min(760px, 100%); max-height: min(90vh, 820px); overflow: auto; padding: 28px; }
        .team-offboarding-modal h2 { margin-bottom: 8px; padding-right: 38px; }
        .team-offboarding-copy { margin: 0; color: #687078; font-size: 12px; line-height: 1.55; }
        .team-impact-strip { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px; margin: 20px 0; overflow: hidden; border: 1px solid #e3e5e2; border-radius: 8px; background: #e3e5e2; }
        .team-impact-strip span { display: grid; gap: 4px; background: #fbfbf8; padding: 12px; color: #777e85; font-size: 10px; }
        .team-impact-strip b { color: #20272a; font-size: 18px; }
        .team-route-list { display: grid; gap: 10px; }
        .team-route-card { border: 1px solid #e3e5e2; border-left: 4px solid #d59a2d; border-radius: 8px; padding: 14px; }
        .team-route-card header { display: flex; justify-content: space-between; gap: 14px; align-items: center; }
        .team-route-card header div { display: flex; align-items: center; gap: 9px; }
        .team-route-card header small { color: #8a9095; font: 9px ui-monospace, SFMono-Regular, Menlo, monospace; text-align: right; }
        .team-route-status { border-radius: 4px; background: #fff5dd; color: #92630e; padding: 5px 7px; font: 9px ui-monospace, SFMono-Regular, Menlo, monospace; text-transform: uppercase; }
        .team-route-choice { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; margin-top: 12px; padding: 4px; border-radius: 7px; background: #f2f3f1; }
        .team-route-choice button { border: 0; border-radius: 5px; background: transparent; padding: 9px; color: #757c82; font: 700 10px Arial, sans-serif; cursor: pointer; }
        .team-route-choice button.active { background: #fff; color: #17211f; box-shadow: 0 1px 4px #1f29251a; }
        .team-recipient-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; margin-top: 10px; }
        .team-recipient-grid label { display: grid; grid-template-columns: auto 1fr auto; gap: 8px; align-items: center; border: 1px solid #e1e4e1; border-radius: 7px; padding: 9px; cursor: pointer; }
        .team-recipient-grid label.selected { border-color: #70bda6; background: #eef9f5; }
        .team-recipient-grid input { accent-color: var(--accent); }
        .team-recipient-grid b, .team-recipient-grid small { display: block; }
        .team-recipient-grid b { color: #2c3234; font-size: 10px; }
        .team-recipient-grid small { margin-top: 3px; color: #8b9195; font-size: 9px; }
        .team-recipient-grid em { border-radius: 10px; background: #e8f1ed; padding: 3px 6px; color: #34735e; font: normal 9px ui-monospace, SFMono-Regular, Menlo, monospace; }
        .team-route-note, .team-recipient-grid p { margin: 9px 0 0; color: #8a6c35; font-size: 10px; }
        .team-no-work { border-radius: 8px; background: #f4f7f5; color: #587067; padding: 15px; font-size: 11px; }
        .team-delete-reason { display: grid; gap: 6px; margin-top: 16px; color: #6d7277; font-size: 10px; font-weight: 700; }
        .team-delete-reason textarea { min-height: 74px; border: 1px solid #dededb; border-radius: 6px; padding: 10px; resize: vertical; font: 11px Arial, sans-serif; }
        .button.team-confirm-delete { background: #a63d3d; }
        @media (max-width: 1100px) {
          .team-workspace {
            grid-template-columns: 1fr;
          }
          .team-create-panel {
            position: static;
          }
          .team-users-panel {
            max-height: none;
          }
          .team-users-scroll {
            max-height: 68vh;
          }
        }
        @media (max-width: 820px) {
          .team-filters {
            grid-template-columns: 1fr 1fr;
          }
          .team-user-head {
            display: none;
          }
          .team-user-row {
            grid-template-columns: 1fr auto;
            gap: 8px 12px;
          }
          .team-user-main {
            grid-column: 1 / -1;
          }
          .team-user-row .button,
          .team-user-row .team-row-actions,
          .team-user-row .team-muted {
            justify-self: end;
          }
          .team-impact-strip { grid-template-columns: 1fr 1fr; }
        }
        @media (max-width: 560px) {
          .team-name-fields,
          .team-form-pair,
          .team-filters {
            grid-template-columns: 1fr;
          }
          .team-recipient-grid { grid-template-columns: 1fr; }
          .team-route-card header { align-items: flex-start; flex-direction: column; }
          .team-route-card header small { text-align: left; }
        }
      `}</style>
    </section>
  );
}
