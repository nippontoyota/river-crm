'use client';

import { useEffect, useState } from 'react';
import { customerFields, previewMapping, saveMapping, type Entry, type Mapping, type MappingPreview, type MappingRules } from '@/lib/intake';

export function MappingEditor({ entries, form = null, mapping, excel = false, onSaved }: { entries: Entry[]; form?: number | null; mapping?: Mapping; excel?: boolean; onSaved: (mapping: Mapping) => void }) {
  const [rules, setRules] = useState<MappingRules>(mapping?.rules || {});
  const [name, setName] = useState(mapping?.template_name || '');
  const [preview, setPreview] = useState<MappingPreview | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [aliasText, setAliasText] = useState(JSON.stringify(mapping?.rules.value_aliases || {}, null, 2));
  const [defaultsText, setDefaultsText] = useState(JSON.stringify(mapping?.rules.defaults || {}, null, 2));
  const fields = [...customerFields, ...(excel ? ['source'] : [])];
  useEffect(() => {
    let alive = true;
    void previewMapping(entries, rules, excel).then(result => { if (alive) setPreview(result); }).catch(e => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [entries, rules, excel]);
  const readRules = (): MappingRules => ({ ...rules, value_aliases: JSON.parse(aliasText), defaults: JSON.parse(defaultsText) });
  const run = async (save = false) => {
    setBusy(true); setError('');
    try {
      const next = readRules();
      const result = await previewMapping(entries, next, excel);
      setRules(next); setPreview(result);
      if (save) onSaved(await saveMapping(form, excel ? name : '', next));
    } catch (e) { setError(e instanceof Error ? e.message : 'Mapping could not be saved.'); }
    finally { setBusy(false); }
  };
  return <section className="intake-mapping">
    <h3>{mapping ? `Mapping version ${mapping.version}` : 'New mapping'}</h3>
    <p className="subtext">Choose where each answer belongs. A new version applies to future submissions. To reprocess a pending enquiry, open it from Receipts and choose “Map this form’s answers”.</p>
    {excel && <label>Template name<input required value={name} onChange={e => setName(e.target.value)} /></label>}
    <div className="intake-table-wrap"><table><thead><tr><th>Incoming label</th><th>Sample</th><th>Destination</th><th>Primary</th></tr></thead><tbody>
      {(preview?.entries || entries.map(e => ({ ...e, sample: String(e.value || ''), destination: '' }))).map(entry => <tr key={entry.id}>
        <td>{entry.label || '(blank header)'}<small>{entry.id}</small></td><td>{entry.sample || '—'}</td>
        <td><select aria-label={`Map ${entry.id}`} value={rules.fields?.[entry.id] || ''} onChange={e => {
          const next = { ...rules.fields }; if (e.target.value) next[entry.id] = e.target.value; else delete next[entry.id];
          setRules({ ...rules, fields: next });
        }}><option value="">Automatic{entry.destination ? ` (${entry.destination})` : ' · unmapped'}</option><option value="ignore">Ignore</option>{[...fields, 'first_name', 'last_name'].map(field => <option key={field} value={field}>{field.replaceAll('_', ' ')}</option>)}</select></td>
        <td>{entry.destination && entry.destination !== 'ignore' && <input type="checkbox" aria-label={`Use ${entry.id} as primary`} checked={rules.primary?.[entry.destination] === entry.id} onChange={e => {
          const primary = { ...rules.primary }; if (e.target.checked) primary[entry.destination] = entry.id; else delete primary[entry.destination];
          setRules({ ...rules, primary });
        }} />}</td>
      </tr>)}
    </tbody></table></div>
    <fieldset><legend>Required mappings</legend><div className="intake-checks">{fields.map(field => <label key={field}><input type="checkbox" checked={rules.required?.includes(field) || false} onChange={e => setRules({ ...rules, required: e.target.checked ? [...(rules.required || []), field] : rules.required?.filter(v => v !== field) })} />{field.replaceAll('_', ' ')}</label>)}</div></fieldset>
    <details><summary>Value aliases and defaults</summary><p className="subtext">Aliases use an approved field and incoming → approved values, for example {`{"model_interest":{"Advertised model":"Admin Lists model"}}`}. Defaults use field → value.</p><div className="intake-grid"><label>Value aliases (JSON)<textarea rows={5} value={aliasText} onChange={e => setAliasText(e.target.value)} /></label><label>Defaults (JSON)<textarea rows={5} value={defaultsText} onChange={e => setDefaultsText(e.target.value)} /></label></div></details>
    {preview && <div aria-live="polite">{Object.entries(preview.errors).map(([field, message]) => <p className="intake-error" key={field}>{field}: {message}</p>)}{!Object.keys(preview.errors).length && <p className="intake-success">Sample passes validation.</p>}</div>}
    {error && <p role="alert" className="intake-error">{error}</p>}
    <div className="intake-actions"><button className="button" disabled={busy} onClick={() => void run()}>Preview mapping</button><button className="button primary" disabled={busy || (excel && !name.trim())} onClick={() => void run(true)}>Save new version</button></div>
  </section>;
}
