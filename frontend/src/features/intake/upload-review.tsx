'use client';

import { useEffect, useState } from 'react';
import { getUpload, getUploadRows, rejectPendingUploadRows, resolveUploadDuplicates, type UploadBatch, type UploadRowPage } from '@/lib/crm';

const fieldLabels: Record<string, string> = { name: 'Name', phone: 'Phone', email: 'Email', source: 'Source', model_interest: 'Model', city: 'City', pincode: 'Pincode', rto: 'RTO', enquiry_date: 'Enquiry date', campaign: 'Campaign' };
const emptyPage: UploadRowPage = { count: 0, results: [], next: null, previous: null };

function Pages({ label, data, page, disabled, onPage }: { label: string; data: UploadRowPage; page: number; disabled: boolean; onPage: (page: number) => void }) {
  return <nav className="intake-actions" aria-label={`${label} pages`}>
    <button className="filter" aria-label={`Previous ${label} page`} disabled={disabled || !data.previous} onClick={() => onPage(page - 1)}>Previous</button>
    <span>Page {page} · {data.count} rows</span>
    <button className="filter" aria-label={`Next ${label} page`} disabled={disabled || !data.next} onClick={() => onPage(page + 1)}>Next</button>
  </nav>;
}

export function UploadReview({ batch, onChange, disabled, onBusyChange }: { batch: UploadBatch; onChange: (batch: UploadBatch) => void; disabled: boolean; onBusyChange: (busy: boolean) => void }) {
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState<{ batch: UploadBatch; invalidPage: number; duplicatePage: number } | null>(null);
  const [invalidPage, setInvalidPage] = useState(1);
  const [duplicatePage, setDuplicatePage] = useState(1);
  const [invalid, setInvalid] = useState<UploadRowPage>(emptyPage);
  const [duplicates, setDuplicates] = useState<UploadRowPage>(emptyPage);
  const loading = batch.status === 'READY' && (loaded?.batch !== batch || loaded.invalidPage !== invalidPage || loaded.duplicatePage !== duplicatePage);

  useEffect(() => {
    onBusyChange(busy || (batch.status === 'READY' && loading));
    return () => onBusyChange(false);
  }, [busy, loading, batch.status, onBusyChange]);

  useEffect(() => {
    if (batch.status !== 'READY') return;
    let cancelled = false;
    Promise.all([getUploadRows(batch.id, 'invalid', invalidPage), getUploadRows(batch.id, 'duplicates', duplicatePage)])
      .then(([invalidRows, duplicateRows]) => {
        if (!cancelled) { setInvalid(invalidRows); setDuplicates(duplicateRows); setError(''); }
      })
      .catch(error => { if (!cancelled) setError(error instanceof Error ? error.message : 'Unable to load review rows. Use Check import to retry.'); })
      .finally(() => { if (!cancelled) setLoaded({ batch, invalidPage, duplicatePage }); });
    return () => { cancelled = true; };
  }, [batch, invalidPage, duplicatePage]);

  const decide = async (id?: number, resolution: 'APPROVE' | 'SKIP' = 'SKIP') => {
    setBusy(true); setError('');
    try {
      if (id === undefined) await rejectPendingUploadRows(batch.id);
      else await resolveUploadDuplicates(batch.id, [{ id, resolution }]);
      onChange(await getUpload(batch.id));
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to save the duplicate decision.'); }
    finally { setBusy(false); }
  };
  if (batch.status !== 'READY') return null;
  const locked = busy || loading || disabled;
  return <div className="intake-page upload-review" aria-busy={busy || loading}>
    {error && <p role="alert" className="intake-error">{error}</p>}
    {loading && <p role="status">Loading review rows…</p>}
    {invalid.count > 0 && <section><h3>Fix {invalid.count} {invalid.count === 1 ? 'row' : 'rows'} in your spreadsheet</h3><p className="subtext">Correct these values offline, then upload the corrected file. No leads will be imported until these errors are fixed.</p>
      <div className="intake-table-wrap"><table><thead><tr><th>Row</th><th>Customer</th><th>What to fix</th></tr></thead><tbody>{invalid.results.map(row => <tr key={row.id}><td>{row.row_number}</td><td>{row.data.name || 'Missing name'}<small>{row.normalized_phone || 'Invalid phone'}</small></td><td>{Object.entries(row.validation_errors).map(([field, message]) => <p key={field}><b>{fieldLabels[field] || field}:</b> {message}</p>)}</td></tr>)}</tbody></table></div>
      <Pages label="invalid rows" data={invalid} page={invalidPage} disabled={locked} onPage={setInvalidPage} />
    </section>}
    {duplicates.count > 0 && <section><h3>Review duplicate phone numbers</h3><p className="subtext">Approve uses this row’s details for that phone. If the phone is already in CRM, its customer details are updated; its assignment and sales status stay the same. For repeated phones in this file, choose one row. Reject skips a row.</p>
      {batch.pending_duplicates > 0 && <div className="intake-actions"><button className="filter" disabled={locked} onClick={() => void decide()}>Reject all pending duplicates</button></div>}
      <div className="intake-table-wrap"><table><thead><tr><th>Row</th><th>Incoming customer / phone</th><th>Duplicate found</th><th>Decision</th></tr></thead><tbody>{duplicates.results.map(row => <tr key={row.id}><td>{row.row_number}</td><td><b>{row.data.name}</b><small>{row.normalized_phone}</small><details><summary>View row</summary>{Object.entries(fieldLabels).filter(([field]) => !['name', 'phone'].includes(field) && row.data[field as keyof typeof row.data]).map(([field, label]) => <p key={field}>{label}: {row.data[field as keyof typeof row.data]}</p>)}</details></td>
        <td>{row.duplicate_type === 'CRM' ? `Already in CRM: ${row.existing_name}` : row.duplicate_type === 'INTAKE' ? 'Pending in Lead Intake' : 'Repeated in this file'}{row.file_rows.length > 0 && <small>File rows: {row.file_rows.join(', ')}{row.file_row_count > row.file_rows.length && ` (showing ${row.file_rows.length} of ${row.file_row_count} matching rows)`}</small>}</td>
        <td><b>{row.resolution === 'PENDING' ? 'Needs review' : row.resolution === 'SKIP' ? 'Rejected / skipped' : 'Approved'}</b><div className="intake-actions"><button className="filter" aria-label={`Approve row ${row.row_number}`} disabled={locked || ['IMPORT', 'OVERWRITE'].includes(row.resolution)} onClick={() => void decide(row.id, 'APPROVE')}>Approve</button><button className="filter" aria-label={`Reject row ${row.row_number}`} disabled={locked || row.resolution === 'SKIP'} onClick={() => void decide(row.id)}>Reject</button></div></td>
      </tr>)}</tbody></table></div>
      <Pages label="duplicates" data={duplicates} page={duplicatePage} disabled={locked} onPage={setDuplicatePage} />
    </section>}
    {!loading && !error && !invalid.count && !duplicates.count && <p>No duplicate phone numbers or invalid rows found.</p>}
  </div>;
}
