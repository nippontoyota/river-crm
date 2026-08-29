"use client";

import { useCallback, useEffect, useMemo, useState, FormEvent } from "react";
import { getUsers, createUser, disableUser, getSystemConfig, type CurrentUser } from "@/lib/crm";

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

  const handleDisable = async (id: number) => {
    if (!confirm("Disable this user?")) return;
    try {
      await disableUser(id);
      loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to disable user.");
    }
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
                return (
                  <div className="team-user-row" key={user.id}>
                    <div className="team-user-main">
                      <b>{`${user.first_name} ${user.last_name}`.trim() || user.email}</b>
                      <small>@{user.email.split("@")[0]} · {user.email}</small>
                    </div>
                    <span>{displayRole(user.role)}</span>
                    <span>{branchLabel(user)}</span>
                    <span className={`team-status ${isActive ? "active" : "disabled"}`}>{isActive ? "Active" : "Disabled"}</span>
                    {isActive ? <button className="button" onClick={() => handleDisable(user.id)}>Disable</button> : <span className="team-muted">No action</span>}
                  </div>
                );
              }) : <div className="empty-state">No users match these filters.</div>}
            </div>
          </div>
        </article>
      </div>

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
          outline-color: var(--orange);
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
          grid-template-columns: minmax(210px, 1.5fr) minmax(115px, .75fr) minmax(115px, .75fr) 86px 88px;
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
          .team-user-row .team-muted {
            justify-self: end;
          }
        }
        @media (max-width: 560px) {
          .team-name-fields,
          .team-form-pair,
          .team-filters {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </section>
  );
}
