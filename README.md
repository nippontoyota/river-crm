# Incheon Mobility CRM

Admins can create a **Meta Uploader** account from **Users**. This company-wide
role signs in to `/bulk-upload` and can upload CSV/XLSX files, review duplicates,
and import its own batches. It has no access to lead lists, assignments, reports,
or other users' uploads. Both upload screens use the same sample format:
`name, phone, email, source, enquiry date, city, pincode`. New leads enter the unassigned pool;
approved duplicate updates preserve ownership and sales status. Admins can disable,
enable, or delete uploader accounts while retaining upload and lead history.
Apply the accounts migration before using this role and lead migration `0019_lead_pincode`
before using the updated bulk format. All seven headings are required; city and
pincode values may be blank. City allows up to 100 characters. A supplied pincode
must contain six digits starting with 1–9. Both upload roles use the same validation
and save these fields on the shared lead record.

The uploader dashboard shows all-time imported leads, approved updates, files
awaiting import, and uploaded files for the signed-in account. Recent uploads can
be reopened after a refresh. Totals count committed rows only; uploading or
previewing a file does not add leads. Successful imports invalidate the analytics
cache so subsequent admin and CEO report requests include the new records.
New leads reach CE and branch workspaces through the existing assignment workflow.

Admin Lists manages lead sources, activities, and sub-activities grouped under an
activity. These optional fields appear in admin, CE, SO, and receptionist intake
forms. Removing an option does not alter historical leads. SO sources retain
their existing choices; receptionist enquiries remain Walk-in.

ETBR tiles show progress of enquiries within each dashboard's existing date and
permission filters: Enquired, Test Drive Completed, Booked, Retailed. Booked in
ETBR includes retailed bookings; older booking tiles retain their existing
meaning. The assigned SO or admin records a test drive through **Mark test drive
completed** in lead details. This records one audited completion per lead without
changing its status, qualification, or follow-ups. Requested drives do not count
as completed.

Complaints require a type and a matching subtype for new tickets. Existing
tickets without a subtype display "Not specified". CE and receptionists can log
and view their own tickets; complaints staff share their assigned branch's queue
and analytics, while admins retain oversight across branches. Complaints accounts
require a branch in Users; existing accounts without one have no complaint access
until an admin assigns it. Changing an employee's branch changes their access,
while existing tickets stay in their original branch. Receptionist complaints
default to Walk-in.

Receptionist enquiry capture asks for a model and omits color and purchase
timeline. The model seed adds **River Indie** without replacing existing model
entries, based on [River's current product page](https://www.rideriver.com/indie).
Complaint subtypes are an intake taxonomy informed by the systems in
[River's owner manuals](https://www.rideriver.com/care/usermanuals), not claims
about confirmed defects. Receptionist reporting covers their own Walk-in leads
captured today.

Apply backend migrations before serving the updated frontend:

```sh
backend/.venv/bin/python backend/manage.py migrate --noinput
```

The migrations add nullable/blank fields and preserve existing records. New
complaint API clients must send `subtype`; the valid options are returned as
`complaint_subtypes` by `/api/system-config/`. Lead payloads accept optional
`activity` and `sub_activity`; configuration stores the hierarchy in
`lists.subActivities`. Completion uses
`POST /api/leads/{id}/complete-test-drive/`; the timestamp is read-only in other
lead endpoints. ETBR counts are additive `etbr_*` summary fields.

Run backend checks with an isolated SQLite test database:

```sh
DATABASE_URL=sqlite:///:memory: backend/.venv/bin/python backend/manage.py test leads analytics complaints accounts uploads --noinput
```

From `frontend`, run `npm run typecheck`, `npm run lint`, and `npm run build`.
