# Lead Intake

Admins review website and selected Meta Instant Form enquiries at `/lead-intake`. Valid submissions create fresh, unassigned leads in the existing assignment pool. Intake never assigns a CE or changes a linked lead's customer details, owners or sales progress.

## Low-cost deployment: existing river-crm + five-minute cron

`INTAKE_EXECUTION_MODE=database` uses the existing receipt and upload tables as a
queue. Meta webhooks save notifications immediately; the scheduled processor
fetches those lead details and imports valid, fresh, unassigned leads. Website
receipts and spreadsheet parsing use the same processor. No broker, dedicated
worker, or Beat scheduler is required for **intake and uploads** in this mode.

The default remains `celery` so deploying code alone does not strand existing work.
Database mode ignores eager execution for intake/upload publication, even if
`CELERY_TASK_ALWAYS_EAGER=true`. Other Celery jobs (including feedback and follow-up
reminders) retain their existing configuration and schedules. Do not delete their
infrastructure or change their eager setting as part of this cutover.

### 1. Deploy backend and preserve existing configuration

Keep the current web service, URL, database and keys. Root: `backend`; build:
`bash build.sh`; Pre-Deploy: `python manage.py migrate --noinput`; start:

```bash
gunicorn config.asgi:application -k uvicorn.workers.UvicornWorker --workers 1
```

Deploy backend before frontend. The build script also runs migrations for manually
configured services whose Pre-Deploy command is blank. Migration `intake.0002`
adds nullable processing leases and per-form fetch progress; existing leads and
connection/form identifiers are preserved. Do not switch web mode until the cron
has run successfully against the same database.

### 2. Shared secrets and Meta setup

Create a `river-runtime` environment group manually and copy existing values;
do not rotate them or commit them. `render.yaml` references this group.

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | Same existing PostgreSQL database on web and cron |
| `DJANGO_SECRET_KEY` | Existing value |
| `JWT_SIGNING_KEY`, `INTAKE_FINGERPRINT_KEY` | Existing values; if absent, preserve their current Django-key fallback |
| `DJANGO_DEBUG` | `false` |
| `INTAKE_ENABLED` | `true` after Meta/forms are verified; controls website and Meta intake, not upload processing |
| `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `SUPABASE_UPLOAD_BUCKET` | Same existing upload storage on both services |
| `INTAKE_SECRETS_JSON` | Existing credential references and tokens, including any website secrets |
| `META_APP_SECRET` | Secret of the subscribed Meta app |
| `META_VERIFY_TOKEN` | Exact token used for webhook verification |
| `META_GRAPH_VERSION` | Explicit currently supported version verified in the Meta app dashboard |

For a connection whose secret reference is `main-meta`, the corresponding JSON
entry is `"main-meta": {"access_token": "YOUR_AUTHORIZED_PAGE_ACCESS_TOKEN"}`.
Use the connection's actual existing reference and retain other entries. Never
put this token in frontend environment variables or screenshots.

Verify Meta's Page webhook callback is
`https://river-crm.onrender.com/api/integrations/meta/webhook/`, its verification
token matches, and the app is subscribed to the selected Page's `leadgen` events.
Verify Page lead access, lead-retrieval permissions, token validity, and the app's
production access/review requirements in Meta. Callback verification alone does
not prove the app can retrieve leads. The configured Page ID, Form ID and mapping
must match the advertised Instant Form. Keep the existing activation dates.

Keep web host/CORS/CSRF and analytics `CACHE_URL` settings on the web service.
Supabase storage is required for cross-service uploads: cron cannot read web-local
media files. Confirm existing pending files are in the shared bucket before cutover.

### 3. Create the scheduled processor, then switch web mode

Create **one cron job** in the web service's region, from the same repository and
commit. Manual setup avoids unintentionally recreating existing resources.

| Setting | Value |
| --- | --- |
| Name | `river-intake-processor` |
| Runtime / root | Python / `backend` |
| Compute | 0.5 CPU / 512 MB (`0.5c-512mb`); monitor actual memory |
| Build | `pip install -r requirements.txt` |
| Schedule | `*/5 * * * *` |
| Command | `python manage.py migrate --check && python manage.py intake_process_pending` |
| Environment | Link `river-runtime`; set `INTAKE_EXECUTION_MODE=database` |

Confirm a successful cron run and a `processor` heartbeat in
`GET /api/intake/connections/health/`. Then set **web**
`INTAKE_EXECUTION_MODE=database` and redeploy. Resolve any service-level environment
overrides; both services must use matching intake enablement and credentials.
If existing workers/Beat remain for other features, set their
`INTAKE_EXECUTION_MODE=database` too and restart them so their old automatic Meta
scans stop. Leave unrelated Celery settings unchanged. In Lead Intake → Connections the new
mode shows Scheduled processor rather than worker/scheduler health.

Runs finish when queues are empty or after about four minutes. A database lease
prevents overlapping processors, including manual shell runs. Interrupted receipt
leases expire and retry; each scan page and cursor commit together. Larger backlogs
can take multiple runs, so five minutes is a normal scheduling delay, not an SLA.
An idle run makes **no Meta requests**. Retention runs hourly within this budget.

Render bills cron by active runtime with a **$1 monthly minimum per job**, not a
fixed unlimited $1 price. Cron jobs cannot use persistent disks. See
[Render cron documentation](https://render.com/docs/cronjobs). Check actual runtime
and billing after rollout. `render.yaml` describes the target setup; review its
preview before syncing and preserve services used by other features.

### 4. Manual fetch and recovery

Under **Lead Intake → Connections**, each eligible Meta form has **Fetch Meta
leads**. This queues a catch-up scan for the next cron run; repeated clicks coalesce.
Normal webhook enquiries continue automatically. The browser's status refresh
reads CRM data only. There is no periodic Meta form scan in database mode.

The scan starts at the last checkpoint minus the existing 30-minute overlap, or
activation for the first scan, and ends at the click time. It resumes stored page
progress across runs and preserves Meta lead-ID deduplication. The checkpoint
advances only after a complete window. If a retry first finishes an older window,
it then catches up to the new click time. No pre-activation leads are imported.

Fetch states are `idle`, `queued`, `running`, `completed`, `error`. Completed means
the scan finished; individual receipts can still be queued or need review. On a
scan error, the request stops with a redacted reason and retains progress. Correct
the issue and click Fetch again; invalid/expired cursors restart the fixed window
safely. Credential failures pause the connection: fix credentials on web and cron,
resume the connection, then retry. Individual receipt errors retain automatic
backoff and the existing ten-attempt limit. Missed webhooks are recovered only when
an administrator requests a fetch.

`POST /api/intake/forms/{id}/fetch/` is admin-only, returns `202` with the form and
fetch state, and returns `409` when database mode/intake/configuration is not ready.
Form reads add `fetch_status` and `fetch_requested_at`; health adds `execution_mode`
and the `processor` heartbeat. Internal cursors and credentials are never exposed.
Upload metadata adds `processing_mode`; both upload screens explain the wait.

For immediate processing from the cron environment, run
`python manage.py intake_process_pending`. `intake_recover` delegates to this
command in database mode; it does not initiate an unrequested Meta scan. Avoid
Render's Trigger Run while a run is active because Render cancels the active run.

### 5. Verify and monitor

- Submit a fresh Meta test lead to the configured form. Confirm webhook receipt,
  then import into Fresh leads and manual assignment within about five minutes.
- Click Fetch; verify that the test lead is not duplicated and the scan completes.
- Upload a small CSV. The request should return pending quickly and become ready
  after a cron run. Confirm Supabase download/deletion and final import.
- Check processor heartbeat (stale after ten minutes), pending receipt age, failed
  receipts, paused connections, scan errors, cron duration/cost and OOM events for
  24 hours. Investigate repeated time-budget exits or sustained backlog.
- On failure, keep the database and shared files, repair the cron environment and
  rerun the command. `INTAKE_ENABLED=false` stops integration acceptance/processing
  but upload recovery and retention continue. Pause new uploads operationally if
  the processor/storage is unavailable. Do not restore eager intake as an OOM fix.

To keep or restore Celery processing instead, provision/verify the existing broker,
worker and Beat first, then set `INTAKE_EXECUTION_MODE=celery` on all of them and web
and stop the database cron. Use one worker child (`--concurrency=1
--prefetch-multiplier=1 --max-tasks-per-child=100`). The legacy fifteen-minute Meta
reconciliation, receipt/upload sweep and retention remain available in that mode;
unrelated feedback/follow-up schedules are unchanged in either mode.

### Upload review API

`GET /api/uploads/{id}/` returns metadata/counts without rows.
`GET /api/uploads/{id}/rows/?filter=duplicates&page=1` (or `filter=invalid`, or no
filter for all rows) returns `{count, next, previous, results}` with 50 rows per page.
Rows expose `file_rows` (at most 20 examples) and `file_row_count` (whole group).
Internal duplicate metadata is omitted from customer `data`.
`POST /api/uploads/{id}/reject-pending/` with `{}` rejects all still-pending valid
duplicates in that owned batch, across pages, and returns `{rejected}`. Previously
approved rows are preserved. Existing row-level approval/rejection remains available.

Final import stays atomic and synchronous for capped batches, with fresh phone
locks/match checks. Row limits apply to both new files and commits of legacy batches.
No new database tables are required.

### Five-minute processor verification (2026-09-19)

- 88 isolated PostgreSQL intake/upload tests passed, including signed webhook
  persistence without a broker, manual-fetch permissions/idempotency, interrupted
  pages, real deadline recovery, credential failures and upload processing with
  integration intake disabled.
- Production frontend build, TypeScript and lint on the changed intake components
  passed. Desktop/mobile browser checks used an isolated database and simulated
  Graph responses: fetch, webhook import, no duplicate on retry, health/error
  displays, queued upload, review and final import all passed.
- Live Meta delivery, Render cron execution, shared Supabase storage and production
  memory/cost still require the rollout checks above. The existing schema-generator
  diagnostics remain; no new unique schema warnings/errors were introduced.

### Earlier Celery/upload verification (2026-09-19)

- 76 upload/intake tests passed against isolated PostgreSQL, including phone-lock
  concurrency, 1,000/1,001-row CSV/XLSX limits, rollback and legacy-batch handling.
- Real Redis, one Gunicorn worker, one Celery child and one scheduler passed two
  rounds of concurrent 1,000-row uploads/imports, a 1,000-row duplicate batch,
  worker restart and queue-outage recovery. Signed Meta webhooks used simulated
  Graph responses; storage was local rather than production Supabase.
- Sampled aggregate RSS peaks: web 134 MB, worker 190 MB, scheduler 94 MB, queue
  15 MB. These local synthetic results are not a guarantee of Render memory usage.
- Frontend production build/type checking and Admin/Meta Uploader browser flows
  passed, including 50-row pagination and batch-wide rejection. The original
  lead desk already has an unrelated ESLint state-update error and hook warning.

Run the backend regressions using an isolated UTF-8 PostgreSQL test database:
`backend/.venv/bin/python backend/manage.py test uploads intake --noinput`.
Set `DATABASE_URL` to that isolated database explicitly; never use production for
these checks. Browser fixture requirements are in
`frontend/scripts/bulk-upload-browser.cjs`.

## Website contract

The external website's server sends `POST /api/integrations/website/leads/` with `Authorization: Bearer <connection-secret>` and `Content-Type: application/json`.

```json
{
  "submission_id": "01J-STABLE-ID-FROM-YOUR-WEBSITE",
  "form_id": "contact-sales",
  "submitted_at": "2026-09-12T10:00:00+05:30",
  "fields": {
    "Full Name": "Customer Example",
    "Ph No:": "+91 98765 43210",
    "Email Address": "customer@example.com",
    "Interested Model": "Approved Admin Lists Model"
  },
  "attribution": {
    "utm_source": "campaign-source",
    "utm_medium": "paid",
    "utm_campaign": "launch",
    "utm_term": "",
    "utm_content": "creative-a"
  }
}
```

`submission_id` and `form_id` are nonblank strings of at most 160 characters. `fields` is an object with up to 100 original labels (each at most 160 characters) and scalar string/number/null answers. The request body limit is 64 KiB. `submitted_at` is optional; omitting it uses receipt time. Supplied timestamps must include a timezone and fall between activation time and receipt time. `attribution` is optional and accepts only the five UTM keys above, with string values up to 500 characters. URLs and nested metadata are rejected.

A committed receipt returns `202 {"receipt_id":"<uuid>","state":"RECEIVED"}`. Replays return the original receipt and its current state. Customer validation runs after acceptance; a durable receipt can enter `NEEDS_REVIEW`. Polling receipt details requires an authenticated CRM admin.

| Response | Meaning / website action |
| --- | --- |
| 202 | Receipt committed; stop delivery retries. |
| 400 | Malformed envelope, invalid timestamp, unsupported keys or more than 100 fields; fix the producer. |
| 401 | Missing or invalid Bearer credential; fix backend credentials. |
| 403 | Connection/form inactive or unknown, or submission before activation; check configuration. |
| 409 | Submission ID already exists with different content; investigate the producer. Do not replace the existing receipt. |
| 413 | Request exceeds 64 KiB; reduce the envelope. |
| 429 | More than 120 authenticated requests per minute for the connection; honor `Retry-After`. The counter is shared in PostgreSQL. |
| 5xx / network timeout | Retry with exponential backoff and jitter using the **same submission ID and payload**. A timeout may follow a committed receipt. |

The fingerprint uses server-keyed HMAC over the canonical envelope. Object ordering does not affect replays. Explicit timestamps normalize to ISO values. The absence of a timestamp stays part of the fingerprint, so retries without a timestamp remain stable. Ignored answers affect conflict detection without retaining their values.

For secret rotation, put the replacement in `active` and the previous secret in `retiring`, deploy the shared backend environment, then update the website server. Remove `retiring` after outstanding deliveries have drained. Existing receipts do not depend on either Bearer secret for replay comparison.

Server-to-server Python example (standard library):

```python
import json
import os
import random
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Save this ID and envelope in your website's own delivery queue first.
# Retry queued requests across process restarts until the CRM acknowledges them.
def deliver(envelope):
    body = json.dumps(envelope).encode()
    for attempt in range(8):
        request = Request(
            os.environ['CRM_URL'] + '/api/integrations/website/leads/',
            data=body,
            headers={'Content-Type': 'application/json',
                     'Authorization': 'Bearer ' + os.environ['CRM_INTAKE_SECRET']},
        )
        try:
            with urlopen(request, timeout=20) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code != 429 and error.code < 500:
                raise RuntimeError('CRM delivery rejected: HTTP ' + str(error.code)) from None
            delay = max(1, int(error.headers.get('Retry-After', '0')))
        except (URLError, TimeoutError):
            delay = 0
        time.sleep(max(delay, min(300, 2 ** attempt) + random.random()))
    raise RuntimeError('Keep this delivery queued for a later retry')
```

The endpoint and these instructions are the website deliverable. Wiring the external website requires its code and remains separate.

## Meta setup

Configure `META_APP_SECRET`, `META_VERIFY_TOKEN` and an explicit `META_GRAPH_VERSION`. There is no moving version default. Verify a currently supported version in the business's Meta app dashboard before setting it. Point the Page `leadgen` subscription at the HTTPS `/api/integrations/meta/webhook/` endpoint. GET verifies the token and returns the challenge. POST verifies the raw-body `X-Hub-Signature-256` HMAC before retaining configured events. Mixed event batches commit all supported lead IDs before acknowledgement; unsupported Pages, forms and events retain no customer payloads.

The worker checks the retrieved form's Page ownership, lead/form IDs and activation boundary before importing. It uses a fixed Graph host, 15-second HTTP timeout, bounded responses and cursor pagination. It does not follow API-provided next-page URLs. Campaign-name retrieval runs separately and stores a display name on the receipt; it does not rewrite an imported lead.

The scheduler scans enabled forms every 15 minutes, overlaps the previous checkpoint by 30 minutes and clamps the interval to activation. A scan advances its checkpoint only after all IDs in the interval are committed. A failed scan keeps its old checkpoint, so retries can replay IDs safely.

Before launch, verify Business Portfolio/Page/form access, authorized tokens, lead access, Page subscriptions, `leads_retrieval`, `pages_manage_metadata`, supporting advertising permissions, app mode, business verification and App Review requirements for this account. Supply the privacy-policy and data-deletion information required for the app. These checks require the business's account; mocked tests cannot confirm them.

Reference: [Meta's maintained Python SDK form model](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/leadgenform.py) exposes the form Page relation and leads edge. The [archived Meta webhook sample](https://github.com/fbsamples/lead-ads-webhook-sample) illustrates delivery/retrieval. Current [Meta lead retrieval documentation](https://developers.facebook.com/docs/marketing-api/guides/lead-ads/retrieving/) was unavailable during implementation; account access and supported Graph version remain launch checks.

## Mapping and review

The shared customer fields are `name`, `phone`, `email`, `model_interest`, `city`, `pincode`, `rto`, `profession`, `branch`, `enquiry_date`, `campaign`, `source_label`, `activity`, and `sub_activity`. Integration configuration supplies source. Excel also accepts `source` and validates it against Admin Lists.

Mapping rules use this schema:

```json
{
  "fields": {"Contact": "phone", "Given": "first_name", "Family": "last_name", "Unused": "ignore"},
  "primary": {"phone": "Contact"},
  "defaults": {"city": "Kochi"},
  "value_aliases": {"model_interest": {"Advertising label": "Approved model"}},
  "required": ["name", "phone"]
}
```

`fields` maps an entry ID or exact label to an approved field, a name component or `ignore`. JSON uses original labels as IDs; repeated labels have distinct identities. Meta uses original labels and occurrence suffixes when needed. `primary` selects an entry ID, including a blank primary that must be corrected. Full name takes precedence over explicitly mapped first/last names. Equivalent normalized values can share a field; conflicting values need a primary selection or correction.

After saved rules, aliases normalize capitalization, whitespace, punctuation and underscores. Supported phone aliases include Phone, Ph No:, Phone Number, phone_number, Mobile, Mobile No, Contact Number and Phone Nnumber. Name aliases include Full Name and Customer Name. Email, model, city, profession and enquiry-date aliases follow the shared mapping service. Column labels are not fuzzy matched; RTO values support conservative spelling correction. Integrations require explicit mappings for Location, Contact and Date. Bulk uploads use the fixed sample headings below instead of integration mappings.

Validation accepts ten-digit Indian phone numbers with separators, 12 digits beginning 91, or 11 digits beginning 0. It rejects arbitrary leading digits or letters. Name and phone are required. Optional supplied values must pass email, length, RTO, configured model/branch/activity/sub-activity and enquiry-date validation. Empty configured lists produce configuration errors for populated choice fields. Missing enquiry dates remain null; dates accept ISO and day-first formats and cannot be invalid or future. XLSX native date cells work.

Admin actions:

- **Link** attaches the receipt to an existing nondeleted lead and adds history without changing that lead's fields, owners or workflow.
- **Create separately** creates a validated unassigned lead with `duplicate_flag=true`.
- **Dismiss** resolves the receipt without a lead.
- **Correct and reprocess** applies allowed customer corrections and reruns validation and duplicate checks.
- **Retry** resets the retry budget. Fix a paused connection's credentials, then use Resume to allow its receipts to process again.

New mapping versions apply to future receipts. To update pending receipts, select them and invoke Reprocess on the chosen version. Resolved, expired, actively processing or other-form receipts are skipped. Imported leads stay unchanged. A pending same-phone receipt waits behind the earliest matching receipt. Existing CRM leads require review. PostgreSQL phone locks also cover manual creation, customer-phone changes and Excel commit; manual capture directs phones with intake enquiries to admin review.

## Uploads and retention

City and pincode use the shared lead fields. Apply migration `0019_lead_pincode`
before importing the updated sample. City permits up to 100 characters; a supplied
pincode must be six ASCII digits with a nonzero first digit. Both values may be
blank. CSV text and numeric XLSX pincodes are normalized to strings, and blank
optional values do not erase saved values during approved duplicate updates.
Admin, CE/SO, manager and CEO lead details expose the saved city and pincode.

Bulk uploads use the fixed sample headings: `name, phone, email, source, enquiry date, city, pincode`. All headings must be present once; optional values may be blank. Unknown, missing, repeated and blank headings are rejected with specific reasons. There are no mapping templates, heading aliases, reparse actions or in-app spreadsheet edits. Download the sample, correct invalid headings or row values offline, then upload again. Invalid rows block the whole import.

Phone number is the bulk import identity. Country-code and local-prefix formatting is normalized before checking duplicates within the file, existing CRM leads and pending intake. Admin can manage any upload; Meta Uploader accounts can upload, approve/reject duplicates, and commit only their own batches. Approving a CRM match updates that same lead's supplied customer details, preserving sales status, assignments, fields outside the sample and blank optional fields. Approving one repeated phone selects that row and skips its siblings. Reject skips a row. Separate leads with the same phone cannot be created through bulk upload. The importer checks matches again under the shared phone lock; changed matches return to review without a partial import. Repeated commits create nothing further. Existing database IDs and integration receipt workflows are unchanged.

Original spreadsheets are deleted after parsing (including failed parsing); failed deletions are retried by retention. Bulk uploads retain validated customer fields for review, without raw mapping answers. Resolved intake receipts and committed batches drop temporary answers; unresolved answers and bulk row input expire after 30 days. Expired input must be uploaded or supplied again. The worker does not refetch expired Meta answers. Retention runs hourly, independently of the intake enable flag.

A receipt has states `RECEIVED`, `PROCESSING`, `NEEDS_REVIEW`, `IMPORTED`, `LINKED`, `FAILED`, and `DISMISSED`. Workers use a five-minute lease and receipt ID messages. Temporary failures back off with jitter to one hour, then enter FAILED after ten attempts. Permission/token failures pause their connection. Waiting behind another enquiry does not consume retries. Broker publication after commit follows [Celery's Django transaction guidance](https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html); failed publication leaves the durable receipt for the next minute sweep. Operational messages contain fixed error codes, IDs and timestamps, not customer answers or tokens.

## Admin API schemas

The generated OpenAPI document is available at `/api/schema/`, with Swagger UI at `/api/docs/`. Python request/response serializers live in `intake/serializers.py`; matching frontend types live in `frontend/src/lib/intake.ts`.

| Endpoint | Request | Response |
| --- | --- | --- |
| `GET /api/intake/submissions/` | Filters `origin`, `form`, `state`, `reason`, `date_from`, `date_to`, `page` | Paginated `SubmissionSerializer` |
| `GET /api/intake/submissions/{uuid}/` | None | `SubmissionDetailSerializer`: mapped fields, errors, retained answers, matches and history |
| `POST .../{uuid}/resolve/` | `action`; `corrections` for correct; `lead_id` for link | Updated receipt detail |
| `GET/POST /api/intake/connections/` | Create: name, origin, source, secret_ref, activated_at, optional enabled | `ConnectionSerializer`; secret_ref is write-only |
| `PATCH /api/intake/connections/{id}/` | Editable name, source, secret_ref, enabled | Updated connection |
| `POST .../connections/{id}/resume/` | Empty object | Connection with pause cleared |
| `GET .../connections/health/` | None | `enabled`, `heartbeats`, connections with counts/backlog/forms |
| `GET/POST /api/intake/forms/` | Create: connection, name, external_id, page_id for Meta, activated_at, enabled | `FormSerializer` |
| `PATCH /api/intake/forms/{id}/` | Name or enabled | Updated form |
| `GET/POST /api/intake/mappings/` | Create: form OR template_name, rules | Immutable `MappingSerializer` version; GET supports form/template_name/excel filters |
| `POST .../mappings/preview/` | entries: list of id/label/value, rules, excel boolean | values, errors, entries with id/label/sample/destination |
| `POST .../mappings/{id}/reprocess/` | receipt_ids, maximum 500 | queued count |
| `POST /api/uploads/` | Multipart file using sample headings | UploadBatchSerializer, 202 |
| `GET .../uploads/{id}/?include_rows=true` | None | Batch, row errors and phone duplicates |
| `POST .../uploads/{id}/resolve-duplicates/` | rows: id, resolution (`APPROVE` or `SKIP`) | Updated review counts |
| `POST .../uploads/{id}/commit/` | Empty object | created, overwritten, skipped; 409 when duplicate review is needed |

All `/api/intake/` and upload endpoints enforce admin authorization on the server. Frontend intake and assignment views refresh every 30 seconds in visible tabs; receipt edits and mapping drafts remain intact while polling.

## Verification

```sh
# Set DATABASE_URL to an isolated database, never production.
python manage.py test intake uploads leads accounts notifications complaints analytics ceo --noinput
cd ../frontend
npm run typecheck
npm run lint
npm run build
```

`intake.test_concurrency` requires PostgreSQL and skips on SQLite. It covers replay, same-phone receipts, simultaneous review, batch commits, manual capture, phone edits and Excel races. Other tests exercise mapping/validation, website authentication/rotation/limits, Meta signatures/pagination/activation/access errors, retries, expiry, permissions and redaction. Run the browser smoke script against the isolated fixture server described in `frontend/scripts/intake-browser.cjs`.
