'use client';

import { useEffect, useState } from 'react';
import { api, getUpload, type UploadBatch, type UploadRow } from '@/lib/crm';
import { customerFields, getMappings, type Mapping } from '@/lib/intake';
import { MappingEditor } from './mapping-editor';

export function UploadReview({ batch, onChange }: { batch: UploadBatch; onChange: (batch: UploadBatch) => void }) {
  const [templates, setTemplates] = useState<Mapping[]>([]);
  const [mappingId, setMappingId] = useState(String(batch.mapping_version || ''));
  const [mappingOpen, setMappingOpen] = useState(false);
  const [row, setRow] = useState<UploadRow | null>(null);
  const [draft, setDraft] = useState<Record<string, string | null>>({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { void getMappings('?excel=true').then(setTemplates).catch(e => setError(e.message)); }, []);
  const run = async (work: () => Promise<void>) => {
    setBusy(true); setError('');
    try { await work(); onChange(await getUpload(batch.id, true)); }
    catch (e) { setError(e instanceof Error ? e.message : 'Upload review failed.'); }
    finally { setBusy(false); }
  };
  return <div className="intake-page upload-review">
    {error && <p role="alert" className="intake-error">{error}</p>}
    {batch.validation_errors_found > 0 && <p className="intake-error">{batch.validation_errors_found} rows need correction. Invalid rows will be skipped at commit.</p>}
    <div className="intake-actions"><label>Excel template<select value={mappingId} onChange={e => setMappingId(e.target.value)}><option value="">Automatic mapping</option>{templates.map(m => <option value={m.id} key={m.id}>{m.template_name} · v{m.version}</option>)}</select></label><button className="button" disabled={busy || batch.status !== 'READY'} onClick={() => void run(async () => { await api(`/api/uploads/${batch.id}/reparse/`, { method: 'POST', body: JSON.stringify({ mapping_version: mappingId ? Number(mappingId) : null }) }); })}>Reparse with template</button><button className="button" disabled={!batch.rows?.length} onClick={() => setMappingOpen(!mappingOpen)}>Preview / edit mapping</button></div>
    {mappingOpen && <MappingEditor key={mappingId} entries={batch.rows?.[0]?.answers || []} excel mapping={templates.find(m => m.id === Number(mappingId))} onSaved={m => { setTemplates([m, ...templates]); setMappingId(String(m.id)); }} />}
    {!!batch.rows?.length && <details open={batch.validation_errors_found > 0}><summary>Review all {batch.rows.length} rows</summary><div className="intake-table-wrap"><table><thead><tr><th>Row</th><th>Customer</th><th>Validation</th><th>Resolution</th><th>Correct</th></tr></thead><tbody>{batch.rows.map(r => <tr key={r.id}><td>{r.row_number}</td><td>{String(r.data.name || 'Missing name')}<small>{r.normalized_phone || 'Missing phone'}</small></td><td>{r.validation_error || 'Valid'}</td><td><select aria-label={`Resolution for row ${r.row_number}`} value={r.resolution} disabled={busy || batch.status !== 'READY'} onChange={e => void run(async () => { await api(`/api/uploads/${batch.id}/resolve-duplicates/`, { method: 'POST', body: JSON.stringify({ rows: [{ id: r.id, resolution: e.target.value }] }) }); })}><option value="PENDING">Pending review</option><option value="SKIP">Skip</option><option value="IMPORT">Import separately</option>{r.duplicate_of && <option value="OVERWRITE">Overwrite matched lead</option>}</select></td><td><button className="button" disabled={busy || batch.status !== 'READY'} onClick={() => { setRow(r); setDraft({ ...r.data, phone: r.normalized_phone }); }}>Edit row {r.row_number}</button></td></tr>)}</tbody></table></div></details>}
    {row && <section className="intake-panel"><h3>Correct row {row.row_number}</h3><div className="intake-grid">{[...customerFields, 'source'].map(field => <label key={field}>{field.replaceAll('_', ' ')}<input type={field === 'enquiry_date' ? 'date' : 'text'} value={draft[field] || ''} onChange={e => setDraft({ ...draft, [field]: e.target.value || (field === 'enquiry_date' ? null : '') })} /></label>)}</div><div className="intake-actions"><button className="button primary" disabled={busy} onClick={() => void run(async () => { const corrections = Object.fromEntries([...customerFields, 'source'].map(field => [field, draft[field] ?? (field === 'enquiry_date' ? null : '')])); await api(`/api/uploads/${batch.id}/correct-row/`, { method: 'POST', body: JSON.stringify({ row_id: row.id, corrections }) }); setRow(null); })}>Save row correction</button><button className="button" onClick={() => setRow(null)}>Cancel correction</button></div></section>}
  </div>;
}
