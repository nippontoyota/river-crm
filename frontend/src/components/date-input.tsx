"use client";

import { useRef, type CSSProperties } from "react";
import { formatDate, toDateInputValue } from "@/lib/dates";

type DateInputProps = {
  value: string;
  onChange: (value: string) => void;
  min?: string;
  max?: string;
  required?: boolean;
  disabled?: boolean;
  className?: string;
  name?: string;
  id?: string;
  ariaLabel?: string;
  style?: CSSProperties;
};

export function DateInput({ value, onChange, min, max, required, disabled, className = "", name, id, ariaLabel = "Date in DD/MM/YYYY format", style }: DateInputProps) {
  const pickerRef = useRef<HTMLInputElement>(null);
  const constrain = (next: string) => {
    const iso = toDateInputValue(next);
    const minIso = toDateInputValue(min);
    const maxIso = toDateInputValue(max);
    if (iso && minIso && iso < minIso) return formatDate(minIso);
    if (iso && maxIso && iso > maxIso) return formatDate(maxIso);
    return next;
  };

  return <span className={`date-input ${className}`.trim()} style={style}>
    <input id={id} name={name} className="date-input-text" type="text" inputMode="numeric" autoComplete="off" pattern="\d{2}/\d{2}/\d{4}" maxLength={10} placeholder="DD/MM/YYYY" value={value} required={required} disabled={disabled} aria-label={ariaLabel} onChange={event => onChange(constrain(event.target.value))} />
    <button className="date-input-icon" type="button" disabled={disabled} aria-label={`Open ${ariaLabel} calendar`} onClick={() => pickerRef.current?.showPicker()}><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M7 3v4M17 3v4M3 10h18" /></svg></button>
    <input ref={pickerRef} className="date-input-picker" type="date" lang="en-IN" tabIndex={-1} aria-hidden="true" value={toDateInputValue(value)} min={toDateInputValue(min)} max={toDateInputValue(max)} disabled={disabled} onChange={event => onChange(constrain(formatDate(event.target.value)))} />
  </span>;
}
