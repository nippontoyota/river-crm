"use client";

import { useEffect, useId, useRef, useState } from "react";
import type { RtoOption } from "@/lib/crm";

export function RtoField({ options, value, onChange }: { options: RtoOption[]; value: string; onChange: (value: string) => void }) {
  const id = useId();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const activeOption = useRef<HTMLButtonElement>(null);
  const selected = options.find(option => option.value === value);
  const normalize = (text: string) => text.toLowerCase().replace(/[^a-z0-9]/g, "");
  const matches = options.filter(option => normalize(option.label).includes(normalize(query)));
  const choose = (option: RtoOption) => { onChange(option.value); setQuery(""); setOpen(false); };

  useEffect(() => {
    if (open) activeOption.current?.scrollIntoView({ block: "nearest" });
  }, [active, open, query]);

  return <div className="rto-field" onBlur={event => {
    if (!event.currentTarget.contains(event.relatedTarget)) { setOpen(false); setQuery(""); }
  }}>
    <label htmlFor={id}>RTO *</label>
    <input id={id} name="rto" role="combobox" required autoComplete="off"
      aria-expanded={open} aria-controls={`${id}-options`} aria-autocomplete="list"
      aria-activedescendant={open && matches[active] ? `${id}-option-${active}` : undefined}
      placeholder={options.length ? "Search RTO code or place" : "RTO list unavailable"}
      value={open ? query : selected?.label || ""}
      ref={input => { input?.setCustomValidity(selected ? "" : "Choose an RTO from the list."); }}
      onFocus={() => { setOpen(true); setQuery(selected?.label || ""); setActive(0); }}
      onClick={() => { if (!open) { setQuery(""); setOpen(true); setActive(0); } }}
      onChange={event => { setQuery(event.target.value); onChange(""); setOpen(true); setActive(0); }}
      onKeyDown={event => {
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
          event.preventDefault();
          if (!open) { setOpen(true); setQuery(""); setActive(0); }
          else setActive(index => Math.max(0, Math.min(matches.length - 1, index + (event.key === "ArrowDown" ? 1 : -1))));
        } else if (event.key === "Enter" && open) {
          event.preventDefault();
          if (matches[active]) choose(matches[active]);
        } else if (event.key === "Escape" && open) {
          event.preventDefault(); event.stopPropagation(); setOpen(false); setQuery("");
        }
      }} />
    {open && <div id={`${id}-options`} className="rto-options" role="listbox" aria-label="Kerala RTOs">
      {matches.map((option, index) => <button type="button" role="option" tabIndex={-1}
        id={`${id}-option-${index}`} key={option.value} aria-selected={index === active}
        ref={index === active ? activeOption : undefined}
        onMouseDown={event => event.preventDefault()} onClick={() => choose(option)}>{option.label}</button>)}
      {!matches.length && <p role="status">{options.length ? "No matching RTOs" : "RTO list unavailable. Please reload the form."}</p>}
    </div>}
  </div>;
}
