"use client";

import { useEffect, useState, FormEvent } from "react";
import { getSystemConfig, updateSystemConfig, type SystemConfig } from "@/lib/crm";

const listSections: { title: string; name: keyof SystemConfig["lists"]; placeholder: string }[] = [
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

  useEffect(() => {
    getSystemConfig()
      .then(res => setConfig(res))
      .catch(err => setError(err instanceof Error ? err.message : "Failed to load lists."))
      .finally(() => setLoading(false));
  }, []);

  const handleAdd = async (listName: keyof SystemConfig["lists"], value: string) => {
    if (!value.trim() || !config) return;
    const currentList = config.lists[listName] || [];
    if (currentList.includes(value.trim())) return; // Duplicate
    
    const newLists = { ...config.lists, [listName]: [...currentList, value.trim()] };
    try {
      const updated = await updateSystemConfig(newLists);
      setConfig(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update list.");
    }
  };

  const handleRemove = async (listName: keyof SystemConfig["lists"], value: string) => {
    if (!config) return;
    const currentList = config.lists[listName] || [];
    const newLists = { ...config.lists, [listName]: currentList.filter(item => item !== value) };
    try {
      const updated = await updateSystemConfig(newLists);
      setConfig(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update list.");
    }
  };

  const ListSection = ({ title, name }: { title: string, name: keyof SystemConfig["lists"] }) => {
    const items = config?.lists?.[name] || [];
    const placeholder = listSections.find(section => section.name === name)?.placeholder || `Add ${title.toLowerCase()}`;
    return (
      <article className="panel list-manager">
        <header className="panel-heading list-manager-heading">
          <div>
            <p className="eyebrow">LIST</p>
            <h2>{title}</h2>
          </div>
          <b>{items.length}</b>
        </header>
        <form 
          onSubmit={(e: FormEvent<HTMLFormElement>) => {
            e.preventDefault();
            const input = e.currentTarget.elements.namedItem("itemValue") as HTMLInputElement;
            handleAdd(name, input.value);
            input.value = "";
          }}
          className="list-add-form"
        >
          <input name="itemValue" required placeholder={placeholder} />
          <button type="submit" className="button primary">Add</button>
        </form>
        <ul className="list-items">
          {items.length ? items.map(item => (
            <li key={item}>
              <span>{item}</span>
              <button type="button" className="button" onClick={() => handleRemove(name, item)}>Remove</button>
            </li>
          )) : <li className="list-empty">No items yet.</li>}
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
          <p className="subtext">Maintain lead branches, sources, activities, models, and color variants in one workspace.</p>
        </div>
      </div>
      
      {error && <div className="empty-state">{error}</div>}

      <div className="lists-workspace">
        {listSections.map(section => <ListSection key={section.name} title={section.title} name={section.name} />)}
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
        .list-add-form input {
          min-width: 0;
          border: 1px solid #dededb;
          border-radius: 6px;
          background: #fff;
          color: var(--ink);
          font: 11px Arial, sans-serif;
          outline-color: var(--orange);
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
          grid-template-columns: minmax(0, 1fr) 88px;
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
