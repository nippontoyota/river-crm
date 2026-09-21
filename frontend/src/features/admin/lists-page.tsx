"use client";

import { useEffect, useState, FormEvent } from "react";
import { getSystemConfig, sourceName, updateSystemConfig, type SystemConfig } from "@/lib/crm";

type ListName = Exclude<keyof SystemConfig["lists"], "subActivities">;
type ListEdit = { name: keyof SystemConfig["lists"]; item: string; parent?: string };
const maxLengths = { branches: 100, sources: 100, activities: 160, models: 100, colorVariants: 120, subActivities: 160 };
const listSections: { title: string; name: ListName; placeholder: string }[] = [
  { title: "Branches", name: "branches", placeholder: "Add branch" },
  { title: "Sources", name: "sources", placeholder: "Add source" },
  { title: "Activities", name: "activities", placeholder: "Add activity" },
  { title: "Model names", name: "models", placeholder: "Add model name" },
  { title: "Color variants", name: "colorVariants", placeholder: "Add color variant" },
];

export function ListsPage() {
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activity, setActivity] = useState("");
  const [subActivity, setSubActivity] = useState("");
  const [editing, setEditing] = useState<ListEdit | null>(null);
  const [editValue, setEditValue] = useState("");
  const [editError, setEditError] = useState("");

  const saveLists = async (lists: SystemConfig["lists"]) => {
    setSaving(true);
    setError("");
    try {
      setConfig(await updateSystemConfig(lists));
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update list.");
      return false;
    } finally { setSaving(false); }
  };

  useEffect(() => {
    getSystemConfig()
      .then(res => setConfig(res))
      .catch(err => setError(err instanceof Error ? err.message : "Failed to load lists."))
      .finally(() => setLoading(false));
  }, []);

  const handleAdd = async (listName: ListName, value: string) => {
    if (!value.trim() || !config) return;
    const currentList = config.lists[listName] || [];
    if (currentList.includes(value.trim())) return; // Duplicate
    
    const newLists = { ...config.lists, [listName]: [...currentList, value.trim()] };
    return saveLists(newLists);
  };

  const handleRemove = async (listName: ListName, value: string) => {
    if (!config || (listName === "sources" && value === "WALKIN")) return;
    const currentList = config.lists[listName] || [];
    const newLists = { ...config.lists, [listName]: currentList.filter(item => item !== value) };
    if (listName === "activities") {
      newLists.subActivities = { ...config.lists.subActivities };
      delete newLists.subActivities[value];
    }
    if (await saveLists(newLists)) {
      if (listName === "activities" && activity === value) setActivity("");
      setEditing(null);
    }
  };

  const handleEdit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!config || !editing || saving) return;
    const { name, item, parent = "" } = editing;
    const value = editValue.trim();
    if (!value) { setEditError("Enter a name."); return; }
    const items = name === "subActivities" ? config.lists.subActivities?.[parent] || [] : config.lists[name] || [];
    const key = (text: string) => name === "sources" ? text.toLowerCase().replace(/[^\p{L}\p{N}]/gu, "") : text.toLowerCase();
    if (items.some(other => other !== item && key(other) === key(value))) {
      setEditError("This name already exists in the list.");
      return;
    }
    if (value === item) { setEditing(null); return; }
    const renamed = items.map(other => other === item ? value : other);
    const lists = { ...config.lists };
    if (name === "subActivities") lists.subActivities = { ...lists.subActivities, [parent]: renamed };
    else lists[name] = renamed;
    if (name === "activities" && lists.subActivities && Object.hasOwn(lists.subActivities, item)) {
      lists.subActivities = { ...lists.subActivities, [value]: lists.subActivities[item] };
      delete lists.subActivities[item];
    }
    if (await saveLists(lists)) {
      if (name === "activities" && activity === item) setActivity(value);
      setEditing(null);
    }
  };

  const renderItem = (name: ListEdit["name"], item: string, parent?: string) => {
    const isEditing = editing?.name === name && editing.item === item && editing.parent === parent;
    const permanent = name === "sources" && item === "WALKIN";
    return <li key={item}>
      {isEditing ? <form className="list-edit-form" onSubmit={handleEdit} onKeyDown={event => { if (event.key === "Escape" && !saving) setEditing(null); }}>
        <input autoFocus aria-label={`Edit ${item}`} required maxLength={maxLengths[name]} value={editValue} disabled={saving} onChange={event => { setEditValue(event.target.value); setEditError(""); }} />
        <div className="list-row-actions">
          <button type="submit" className="button primary" disabled={saving}>{saving ? "Saving…" : "Save"}</button>
          <button type="button" className="filter" disabled={saving} onClick={() => setEditing(null)}>Cancel</button>
        </div>
        {editError && <p className="form-error" role="alert">{editError}</p>}
      </form> : <>
        <span>{name === "sources" ? sourceName(item) : item}</span>
        <div className="list-row-actions">
          {!permanent && <button type="button" className="filter" disabled={saving || Boolean(editing)} onClick={() => { setEditing({ name, item, parent }); setEditValue(item); setEditError(""); setError(""); }}>Edit</button>}
          <button type="button" className="button" disabled={saving || permanent || Boolean(editing)} onClick={() => {
            if (name === "subActivities") {
              if (config && parent) void saveLists({ ...config.lists, subActivities: { ...config.lists.subActivities, [parent]: (config.lists.subActivities?.[parent] || []).filter(child => child !== item) } });
            } else void handleRemove(name, item);
          }}>{permanent ? "Permanent" : "Remove"}</button>
        </div>
      </>}
    </li>;
  };

  const renderListSection = ({ title, name }: { title: string, name: ListName }) => {
    const items = config?.lists?.[name] || [];
    const placeholder = listSections.find(section => section.name === name)?.placeholder || `Add ${title.toLowerCase()}`;
    return (
      <article className="panel list-manager" key={name}>
        <header className="panel-heading list-manager-heading">
          <div>
            <p className="eyebrow">LIST</p>
            <h2>{title}</h2>
          </div>
          <b>{items.length}</b>
        </header>
        <form 
          onSubmit={async (e: FormEvent<HTMLFormElement>) => {
            e.preventDefault();
            const input = e.currentTarget.elements.namedItem("itemValue") as HTMLInputElement;
            if (await handleAdd(name, input.value)) input.value = "";
          }}
          className="list-add-form"
        >
          <input name="itemValue" required maxLength={maxLengths[name]} placeholder={placeholder} disabled={saving || Boolean(editing)} />
          <button type="submit" className="button primary" disabled={saving || Boolean(editing)}>Add</button>
        </form>
        <ul className="list-items">
          {items.length ? items.map(item => renderItem(name, item)) : <li className="list-empty">No items yet.</li>}
        </ul>
      </article>
    );
  };

  if (loading) return <div className="page" style={{ textAlign: "center", padding: "4rem" }}>Loading...</div>;

  return (
    <section className="page lists-admin-page">
      <div className="page-heading compact">
        <div>
          <h1>Lists <span>Administrator</span></h1>
          <p className="subtext">Maintain lead sources, activities and linked sub-activities, branches, models, and color variants.</p>
        </div>
      </div>
      
      {error && <div className="empty-state" role="alert">{error}</div>}

      <div className="lists-workspace">
        {listSections.map(renderListSection)}
        <article className="panel list-manager">
          <header className="panel-heading list-manager-heading"><div><p className="eyebrow">LINKED TO ACTIVITY</p><h2>Sub-activities</h2></div></header>
          <label style={{ padding: "12px 20px" }}>Parent activity<select className="filter" aria-label="Parent activity" value={activity} disabled={saving || Boolean(editing)} onChange={event => { setActivity(event.target.value); setSubActivity(""); }}><option value="">Select activity</option>{config?.lists.activities?.map(item => <option key={item}>{item}</option>)}</select></label>
          <form className="list-add-form" onSubmit={async event => {
            event.preventDefault();
            if (!config || !activity || !subActivity.trim() || saving) return;
            const children = config.lists.subActivities?.[activity] || [];
            if (await saveLists({ ...config.lists, subActivities: { ...config.lists.subActivities, [activity]: Array.from(new Set([...children, subActivity.trim()])) } })) setSubActivity("");
          }}><input aria-label="New sub-activity" required maxLength={160} placeholder="e.g. Roadshow at Kochi" value={subActivity} onChange={event => setSubActivity(event.target.value)} disabled={!activity || saving || Boolean(editing)} /><button className="button primary" disabled={!activity || saving || Boolean(editing)}>Add</button></form>
          <ul className="list-items">{(config?.lists.subActivities?.[activity] || []).map(item => renderItem("subActivities", item, activity))}</ul>
        </article>
      </div>

      <style>{`
        .lists-admin-page {
          max-width: none;
          min-height: calc(100vh - 83px);
          padding-bottom: 24px;
        }
        .lists-workspace {
          display: grid;
          grid-template-columns: repeat(3, minmax(260px, 1fr));
          gap: 18px;
          align-items: stretch;
        }
        .list-manager {
          display: flex;
          flex-direction: column;
          min-height: 0;
          height: calc((100vh - 222px) / 2);
          min-height: 238px;
          padding: 0;
          overflow: hidden;
          border-radius: 8px;
        }
        .list-manager-heading {
          padding: 18px 20px 14px;
          border-bottom: 1px solid var(--line);
        }
        .list-manager-heading b {
          display: grid;
          place-items: center;
          min-width: 28px;
          height: 28px;
          border-radius: 6px;
          background: #202226;
          color: #fff;
          font: 11px ui-monospace, SFMono-Regular, Menlo, monospace;
        }
        .list-add-form {
          display: grid;
          grid-template-columns: minmax(0, 1fr) 64px;
          gap: 10px;
          padding: 14px 20px;
          border-bottom: 1px solid var(--line);
          background: #fbfbf8;
        }
        .list-add-form input,
        .list-edit-form input {
          min-width: 0;
          border: 1px solid #dededb;
          border-radius: 6px;
          background: #fff;
          color: var(--ink);
          font: 11px Arial, sans-serif;
          outline-color: var(--accent);
          padding: 10px;
        }
        .list-items {
          list-style: none;
          margin: 0;
          padding: 0;
          overflow-y: auto;
        }
        .list-items li {
          display: grid;
          grid-template-columns: minmax(0, 1fr) auto;
          gap: 12px;
          align-items: center;
          padding: 12px 20px;
          border-bottom: 1px solid #f1f0ed;
          font-size: 12px;
        }
        .list-items span {
          overflow-wrap: anywhere;
        }
        .list-items .button {
          padding: 10px 12px;
        }
        .list-row-actions { display: flex; gap: 6px; align-items: center; }
        .list-row-actions .filter { padding: 9px 12px; }
        .list-edit-form { grid-column: 1 / -1; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; align-items: center; }
        .list-edit-form .form-error { grid-column: 1 / -1; margin: 0; }
        .list-empty {
          display: block !important;
          color: #868b91;
          font-size: 11px;
        }
        @media (max-width: 1250px) {
          .lists-workspace {
            grid-template-columns: repeat(2, minmax(280px, 1fr));
          }
        }
        @media (max-width: 820px) {
          .lists-workspace {
            grid-template-columns: 1fr;
          }
          .list-manager {
            height: auto;
            max-height: 52vh;
          }
        }
        @media (max-width: 560px) {
          .list-add-form,
          .list-edit-form,
          .list-items li {
            grid-template-columns: 1fr;
          }
          .list-items .button {
            justify-self: start;
          }
        }
      `}</style>
    </section>
  );
}
