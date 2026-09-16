# Services

CE saves incoming requests and forwards them to a configured branch. Service Department users work from a shared branch queue. Admin can correct vehicle records and transfer active requests. CEO reads the all-branch overview. Sales officers see service history for their accessible leads.

Chassis numbers are normalized to uppercase without whitespace and are unique. **Vehicle & service history** appears only on booked or retailed sales, never on new enquiries. CRM links and new service requests for linked vehicles require a booked or retailed sale. Register scooters on those sales or from service intake. New retail transitions require a linked vehicle; historical sales can be backfilled without changing their outcomes. Unlinked scooters store their own customer details. Linked scooters display current CRM contact details, while every request retains its intake snapshots.

**Add service** is available throughout the CE workspace and in the Service Department workspace. It opens the shared intake form. Admin and CEO retain their existing management/read permissions; they cannot create service requests.

## API

- `GET /api/vehicles/?chassis=...` — exact lookup. `?lead=...` lists visible vehicles belonging to a sale.
- `POST /api/vehicles/` — chassis, model, optional registration and related lead; customer name and ten-digit phone required without a lead.
- `GET /api/vehicles/{id}/?chassis=...` — vehicle and service history. Service staff can access other branches' history through exact chassis lookup. CE history is limited to their own requests.
- `PATCH /api/vehicles/{id}/` — Admin correction; `reason` required. Corrections never rewrite prior request snapshots.
- `GET/POST /api/service-requests/` — scoped queue or new request. Filters: status, branch, q, date_from, date_to, page. POST takes vehicle, issue, branch, source, priority, optional odometer and preferred appointment. `acknowledge_active=true` explicitly confirms a separate issue when another active request exists.
- `GET/PATCH /api/service-requests/{id}/` — details; CE may edit intake before forwarding. PATCH requires the latest `revision`.
- `POST /api/service-requests/{id}/{action}/` — forward, progress, note, resolve, reopen, cancel, transfer. All require the current `revision`. Progress takes `status` (`IN_PROGRESS` or `WAITING`); transfer takes `branch`. Notes, waiting, resolution, reopening, cancellation and transfers require `note`. Stale requests return 409. Invalid transitions do not write history or notifications.
- `GET /api/notifications/?service=true` — notifications filtered by current request visibility.

Queues refresh every 30 seconds while visible and on focus. Explicitly refresh an open request after a conflict so unsaved notes are not replaced. Appointments record customer preferences; no workshop capacity booking is implied. Inventory, billing, job cards, external messages, and automatic sales-contact overwrites are outside this version.

## Release

Run `python manage.py migrate --noinput` before deploying the updated frontend. The migrations only add tables/fields and role choices. In Admin Lists, configure branches; create Service Department accounts with one of those branches. Add known chassis numbers to existing sales. Requests forwarded to an unstaffed branch remain visible to CE/Admin with a warning. Disabling or deleting a Service account keeps its branch queue and audit history.

## Checks

Run `python manage.py test servicing leads accounts notifications complaints feedback --noinput` and the frontend production build. Run the servicing tests against PostgreSQL to exercise concurrent chassis registration; SQLite skips that test.

For the browser scenario, use an isolated database (the seed command refuses any other database):

```sh
DATABASE_URL=sqlite:////tmp/crm-service-browser.sqlite3 backend/.venv/bin/python backend/manage.py migrate --noinput
DATABASE_URL=sqlite:////tmp/crm-service-browser.sqlite3 backend/.venv/bin/python backend/manage.py seed_service_browser
DATABASE_URL=sqlite:////tmp/crm-service-browser.sqlite3 backend/.venv/bin/python backend/manage.py runserver 127.0.0.1:8040 --noreload
```

Start the frontend with `NEXT_PUBLIC_API_URL=http://127.0.0.1:8040 npm run dev -- --hostname 127.0.0.1 --port 3040`, then run `node frontend/scripts/service-browser.cjs`. Set `PUPPETEER_MODULE` and `BROWSER_EXECUTABLE` to available local installations. Screenshots are saved under `/tmp/crm-service-*.png`. Run against a fresh isolated database each time.
