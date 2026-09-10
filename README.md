# Incheon Mobility CRM

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
and view their own tickets; the complaints department handles resolution and
admins retain oversight. Receptionist complaints default to Walk-in.

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
