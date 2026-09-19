# Lead Intake

Admins review website and selected Meta Instant Form enquiries at `/lead-intake`. Valid submissions create fresh, unassigned leads in the existing assignment pool. Intake never assigns a CE or changes a linked lead's customer details, owners or sales progress.

## Deployment: existing river-crm

The web service currently has 512 MB RAM and uses eager Celery execution. Deploy the
upload optimizations first; change eager mode only after the queue and worker are
healthy. Keep the existing web service, URL, database and signing keys. Do not
create a second web service by blindly applying the Blueprint.

### 1. Deploy application changes

- In the existing web service, set **Pre-Deploy Command** to
  `python manage.py migrate --noinput`. The build script only installs dependencies
  and collects static files. Keep root directory `backend` and build `bash build.sh`.
- Use start command
  `gunicorn config.asgi:application -k uvicorn.workers.UvicornWorker --workers 1`.
- Deploy backend before frontend; the old `include_rows=true` endpoint remains
  available up to 1,000 rows during the transition. Do not change eager mode yet.
- The new upload maximum is 1,000 non-empty lead rows and 10 MB per file. XLSX
  archives exceeding 25 MB total expanded size are rejected. Existing oversized
  uncommitted batches must be split and reuploaded; committed history is retained.

### 2. Prepare shared configuration and services

Create the `river-runtime` environment group manually. `render.yaml` references
this existing group because Render ignores `sync: false` inside environment groups
([Blueprint documentation](https://render.com/docs/blueprint-spec#environment-groups)).
Copy existing values without rotating credentials:

- `DATABASE_URL`, `DJANGO_SECRET_KEY`, `JWT_SIGNING_KEY` (if absent, use the existing
  Django key), and `INTAKE_FINGERPRINT_KEY` (if absent, use the existing Django key).
- `SUPABASE_URL`, `SUPABASE_SECRET_KEY` (or the existing service-role key), and
  `SUPABASE_UPLOAD_BUCKET`. Local media files cannot be shared across Render services.
- `INTAKE_SECRETS_JSON`, `META_APP_SECRET`, `META_VERIFY_TOKEN`, `META_GRAPH_VERSION`,
  existing `INTAKE_ENABLED`, and all existing WhatsApp settings.
- `DJANGO_DEBUG=false`, `CELERY_TASK_ALWAYS_EAGER=false`, and the new queue's internal
  connection string as `REDIS_URL`.

Keep host/CORS/CSRF and analytics `CACHE_URL` settings on the existing web service.
Create these **paid Starter services**, in the web service's region, from the same
repository and commit. Review their current prices in Render before provisioning:

| Service | Configuration |
| --- | --- |
| `river-queue` | Key Value, `noeviction`, internal connections only |
| `river-worker` | Background Worker, root `backend`, build `pip install -r requirements.txt` |
| `river-scheduler` | Background Worker, same root/build, exactly one instance |

Worker start command:

```bash
python manage.py migrate --check && celery -A config worker --loglevel=warning --concurrency=1 --prefetch-multiplier=1 --max-tasks-per-child=100
```

Scheduler start command:

```bash
python manage.py migrate --check && celery -A config beat --loglevel=warning --schedule=/tmp/celerybeat-schedule
```

Link the group to worker and scheduler first. When linking it to web, leave the
web's service-level `CELERY_TASK_ALWAYS_EAGER=true` override until cutover. Resolve
other service-level overrides so all services use the same database, storage and
intake credentials. The dedicated queue is separate from the analytics cache.
The Blueprint describes the target state; import the existing web service into
Blueprint management first if using it, and review the preview for unintended
resources. Manual setup using this table is sufficient.

### 3. Verify and cut over

1. Confirm migrations passed and the worker and scheduler start without errors.
   Check their independent heartbeats in Lead Intake health. Restart recovery can
   process existing pending uploads/receipts, so verify shared configuration first.
2. Confirm Supabase upload, worker download, and deletion work on the same bucket.
3. Set the web's `CELERY_TASK_ALWAYS_EAGER=false` and redeploy. Never disable eager
   mode without a reachable queue and running worker.
4. Upload a small CSV: the request should return a pending batch quickly, then
   polling should change it to ready. Approve duplicates and import once.
5. Send a Meta test lead to an enabled configured form; verify receipt, imported
   lead, manual assignment, and audit history. If intake was disabled, enable it
   consistently across web, worker and scheduler after this setup, then test.
6. Run `python manage.py intake_recover` in the Render web shell to offer pending
   work to the broker. Retries must not create duplicate leads. Recovery of uploads
   remains active even when automatic Meta/website intake is disabled.

### 4. Monitor and recover

For 24 hours, watch per-service memory and OOM events, worker/scheduler heartbeats,
oldest pending receipt, backlog and reconciliation checkpoints. Exercise two
simultaneous 1,000-row uploads, duplicate review, final import, and Meta delivery.
Target peaks below 400 MB on each 512 MB instance, without a sustained upward trend.
Child recycling occurs after tasks; it does not protect against one oversized task.

On failure, temporarily stop new spreadsheet uploads operationally and set
`INTAKE_ENABLED=false` consistently while repairing infrastructure. Keep pending
records/files and the queue; do not automatically restore eager mode. Existing
30-day retention still applies. Restore the same tested app version on all services,
recheck heartbeats, run recovery, then reopen uploads/intake. Increase instance size
only if measured workload still requires it.

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

### Local verification (2026-09-19)

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
