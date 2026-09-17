'use client';

import { useState } from 'react';
import { getUpload, resolveUploadDuplicates, type UploadBatch } from '@/lib/crm';

const fieldLabels: Record<string, string> = { name: 'Name', phone: 'Phone', email: 'Email', source: 'Source', model_interest: 'Model', city: 'City', rto: 'RTO', enquiry_date: 'Enquiry date', campaign: 'Campaign' };

export function UploadReview({ batch, onChange, disabled, onBusyChange }: { batch: UploadBatch; onChange: (batch: UploadBatch) => void; disabled: boolean; onBusyChange: (busy: boolean) => void }) {
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const duplicates = batch.rows?.filter(row => row.duplicate_type) || [];
  const invalid = batch.rows?.filter(row => row.validation_error) || [];
  const decide = async (ids: number[], resolution: 'APPROVE' | 'SKIP') => {
    setBusy(true); onBusyChange(true); setError('');
    try {
      await resolveUploadDuplicates(batch.id, ids.map(id => ({ id, resolution })));
      onChange(await getUpload(batch.id, true));
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to save the duplicate decision.'); }
    finally { setBusy(false); onBusyChange(false); }
  };
  if (batch.status !== 'READY') return null;
  return <div className="intake-page upload-review">
    {error && <p role="alert" className="intake-error">{error}</p>}
    {invalid.length > 0 && <section><h3>Fix {invalid.length} {invalid.length === 1 ? 'row' : 'rows'} in your spreadsheet</h3><p className="subtext">Correct these values offline, then upload the corrected file. No leads will be imported until these errors are fixed.</p>
      <div className="intake-table-wrap"><table><thead><tr><th>Row</th><th>Customer</th><th>What to fix</th></tr></thead><tbody>{invalid.map(row => <tr key={row.id}><td>{row.row_number}</td><td>{row.data.name || 'Missing name'}<small>{row.normalized_phone || 'Invalid phone'}</small></td><td>{Object.entries(row.validation_errors).map(([field, message]) => <p key={field}><b>{fieldLabels[field] || field}:</b> {message}</p>)}</td></tr>)}</tbody></table></div>
    </section>}
    {duplicates.length > 0 && <section><h3>Review duplicate phone numbers</h3><p className="subtext">Approve uses this row’s details for that phone. If the phone is already in CRM, its customer details are updated; its assignment and sales status stay the same. For repeated phones in this file, choose one row. Reject skips a row.</p>
      {batch.pending_duplicates > 0 && <div className="intake-actions"><button className="filter" disabled={busy || disabled} onClick={() => void decide(duplicates.filter(row => row.resolution === 'PENDING').map(row => row.id), 'SKIP')}>Reject all pending duplicates</button></div>}
      <div className="intake-table-wrap"><table><thead><tr><th>Row</th><th>Incoming customer / phone</th><th>Duplicate found</th><th>Decision</th></tr></thead><tbody>{duplicates.map(row => <tr key={row.id}><td>{row.row_number}</td><td><b>{row.data.name}</b><small>{row.normalized_phone}</small><details><summary>View row</summary>{Object.entries(fieldLabels).filter(([field]) => !['name', 'phone'].includes(field) && row.data[field as keyof typeof row.data]).map(([field, label]) => <p key={field}>{label}: {row.data[field as keyof typeof row.data]}</p>)}</details></td>
        <td>{row.duplicate_type === 'CRM' ? `Already in CRM: ${row.existing_name}` : row.duplicate_type === 'INTAKE' ? 'Pending in Lead Intake' : 'Repeated in this file'}{row.file_rows.length > 0 && <small>File rows: {row.file_rows.join(', ')}</small>}</td>
        <td><b>{row.resolution === 'PENDING' ? 'Needs review' : row.resolution === 'SKIP' ? 'Rejected / skipped' : 'Approved'}</b><div className="intake-actions"><button className="filter" aria-label={`Approve row ${row.row_number}`} disabled={busy || disabled || ['IMPORT', 'OVERWRITE'].includes(row.resolution)} onClick={() => void decide([row.id], 'APPROVE')}>Approve</button><button className="filter" aria-label={`Reject row ${row.row_number}`} disabled={busy || disabled || row.resolution === 'SKIP'} onClick={() => void decide([row.id], 'SKIP')}>Reject</button></div></td>
      </tr>)}</tbody></table></div>
    </section>}
    {!invalid.length && !duplicates.length && <p>No duplicate phone numbers or invalid rows found.</p>}
  </div>;
}
