# Lead Intake

Admins review website and selected Meta Instant Form enquiries at `/lead-intake`. Valid submissions create fresh, unassigned leads in the existing assignment pool. Intake never assigns a CE or changes a linked lead's customer details, owners or sales progress.

## Automatic delivery through GitHub Actions

Meta → existing importer and mappings → existing CRM database → Fresh leads.
Keep the existing webhook as a second delivery path. Normal operation needs no
Fetch click. Connections select enabled forms and credential references; Mappings
control required fields and approved values; Receipts retain reviews and history.

| Work | Target interval |
| --- | --- |
| Discover leads from enabled, unpaused Meta forms | 30 minutes |
| Process webhook receipts and spreadsheet previews | 5 minutes |
| Follow-up and feedback reminders | 5 minutes |
| Existing intake/upload retention | Hourly |

[crm-background.yml](../../.github/workflows/crm-background.yml) runs at
`2-59/5 * * * *` on a standard Ubuntu runner with Python 3.14. Only `main` can use
production secrets. The workflow has read-only repository access, one concurrency
group, no cancellation of an active run, a 10-minute job timeout and a four-minute
processor budget. It checks migrations without applying them.

Scheduling stays **disabled** until the repository variable
`CRM_BACKGROUND_ENABLED` equals `true`. A manual run defaults to read-only
`preflight`; choose `storage-check` to upload/download/delete one test file, or
`process` for a controlled import while scheduling is still disabled.

The processor calls existing Django tasks directly in database mode. It needs no
Redis queue. Keep the separate analytics `CACHE_URL` on the web service.

### Shared runtime configuration

Copy existing values from Render into GitHub Actions secrets through the repository
settings. Do not paste them into issues, public logs, commits or chat. Preserve the
complete `INTAKE_SECRETS_JSON`, including other connections.

| GitHub secret | Value |
| --- | --- |
| `DATABASE_URL` | Existing production PostgreSQL URL reachable from a GitHub runner |
| `DJANGO_SECRET_KEY` | Exact existing Render value |
| `INTAKE_SECRETS_JSON` | Complete existing JSON, including `main-meta.access_token` |
| `META_APP_SECRET`, `META_VERIFY_TOKEN` | Existing values for the current Meta app |
| `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `SUPABASE_UPLOAD_BUCKET` | Existing shared upload bucket configuration |
| `JWT_SIGNING_KEY`, `INTAKE_FINGERPRINT_KEY` | Copy if explicitly configured; leave absent otherwise to preserve Django-key fallback |

Set repository variable `META_GRAPH_VERSION` to the same supported pinned version
as Render. Copy the current `WHATSAPP_MODE`, `WHATSAPP_BUSINESS_NAME`,
`WHATSAPP_LANGUAGE`, `WHATSAPP_TEMPLATE_INTRODUCTION`, and
`WHATSAPP_TEMPLATE_REASSIGNMENT` into repository variables. The workflow defaults
match the backend defaults, but an existing override must match on both runtimes.

Use these settings on Render web and the Actions processor at cutover:

```text
INTAKE_EXECUTION_MODE=database
CELERY_TASK_ALWAYS_EAGER=false
INTAKE_ENABLED=true
DJANGO_DEBUG=false
```

Keep the existing single Gunicorn worker, database, callback URL, form IDs,
activation dates, mapping versions and signing keys. No new schema migration is
needed. Existing active leads and reviews stay in their current tables. Retention
still expires temporary intake answers after 30 days; this change adds no lead
deletion.

### Read-only credential preflight

In Render Shell, with the intended runtime settings, run:

```sh
python manage.py intake_check_credentials
```

The default credential reference is `main-meta`; `--secret-ref` supports another
existing connection. From Actions, select manual mode `preflight`, which uses
`python background.py preflight` to redact startup/database exceptions too.

The command checks configuration presence, PostgreSQL connectivity and
SELECT/INSERT/UPDATE table privileges plus sequence USAGE with read-only SQL.
It verifies configured Page/Form ownership, requests up to five lead identifiers,
fetches one available lead's answers and previews the saved mapping. It prints
field names and validation field names, without tokens, answers or mapping values.
It creates no receipts, leads, audit events or heartbeats and never pauses a
connection. Supabase presence is only a configuration check; run `storage-check`
for actual shared-storage access.

If there is no available lead within the existing import boundary, the command
reports “access succeeded; sample retrieval not yet demonstrated” and exits
unsuccessfully. Keep the activation gate closed until a real sample can be read.
A validation issue in that sample does not invalidate credentials; it will enter
normal review during import. If access fails, check token validity/expiry, Page
ownership and lead permissions in Meta's token/business tools. Keep the existing
app and credentials when valid. A configured token is not proof of access.

### Processing and recovery

The workflow runs the equivalent of:

```sh
python manage.py intake_process_pending --automatic-meta --reminders --max-seconds 240
```

Without those flags, the command still supports the previous manual-scan processor.
With them, it acquires the existing database lease, processes reminders once,
resumes uploads/eligible receipts, requests overdue Meta scans and runs due
retention. A paused Meta connection does not stop unrelated work.

Each scan keeps its original start/end window and commits each page's receipts
with its cursor. The checkpoint advances only after the whole window succeeds.
Interrupted runs resume; expired cursors restart the same window. Scans overlap
by 30 minutes and use the existing receipt identities for replay deduplication.
The first scan uses the existing activation boundary (29 August 2026, 00:00 IST
for the selected production form), rather than changing it to the deployment date.

Transient scan failures retry on the next run, at most once per form per run.
Access failures pause that connection; correct the credentials on both runtimes,
then use “Resume after credentials are corrected” in Connections. The optional
“Request recovery” button uses the existing fetch endpoint and queues work for
the next run. It cannot bypass disabled forms or paused credentials.

Public logs contain aggregates: `scanned` counts returned identifiers including
replays, `imported` counts receipts imported this run, `awaiting_review` and
`failed` are current receipt totals, and the remaining counters include paused
work. `scan_failures` counts forms deferred during this run; `upload_failures` is
the current failed-batch total. Treat validation reviews as work for an admin.

Health reuses `processor_attempt`, `processor_success` and `processor` heartbeat
rows. A clean four-minute yield counts as a successful processor run because it
preserves work for the next run; an unhandled failure does not. Form-scan success
is separate. The CRM warns after 15 minutes without processor success and after
60 minutes without a successful scan for an enabled Meta form. Visible lead and
intake lists still refresh every 30 seconds.

### Production cutover

1. Take a restorable PostgreSQL backup and verify it in an isolated database. Save
   a private baseline of active lead IDs/details/owners/statuses/flags, receipt
   identities/counts/reviews/audits, connection/form activation dates and mappings.
   Do not put backups or customer snapshots in Actions artifacts or this repository.
2. Deploy compatible code with `CRM_BACKGROUND_ENABLED` absent or `false`.
   Leave the current live runtime unchanged until preflight passes.
3. Configure the shared secrets/variables. Run manual `preflight` from `main`.
   Confirm production Meta sample retrieval and database privileges from the runner.
4. Run manual `storage-check`. Confirm pending uploads live in the same Supabase
   bucket; local files on Render are not shared with GitHub runners.
5. Stop any old scheduled processor/Beat and let active worker jobs finish. Do not
   run an old Celery importer alongside the new database processor during cutover.
6. Set Render web to the database runtime settings above, keep one Gunicorn worker,
   and deploy. `render.yaml` retains the legacy Celery topology for rollback; do not
   sync it during the Actions cutover. Preserve stopped worker/queue services
   until the observation period below is complete, then update the Blueprint
   when retiring them.
7. Run one manual `process` job. Check receipt counts, mappings, sources, Fresh
   unassigned leads, duplicate reviews and redacted error codes. Reconcile the
   private baseline; all old lead IDs and pending reviews must still exist.
8. Set `CRM_BACKGROUND_ENABLED=true`. Let the initial catch-up finish and confirm
   at least two successful Meta scan cycles. Check webhook replay, uploads/review/
   commit, reminders and normal 30-second lead-list refresh.
9. Enable workflow-failure notifications and monitor heartbeat/scan warnings for
   24 hours. Only then retire unused worker, scheduler or queue services, after
   confirming no other feature needs them. Keep the analytics cache.

If rollback is needed, set `CRM_BACKGROUND_ENABLED=false`, let the active run
finish, and restore the previously working processor configuration where available.
Keep database records and checkpoints. Avoid restoring an old database over
legitimate new CRM activity.

### Hosting limits and schedule maintenance

GitHub may delay or drop scheduled jobs. Public-repository schedules can be
suspended after 60 days without repository activity. Enable the workflow again
from Actions after inactivity, confirm the repository variable still allows
scheduling, then run diagnostics and one controlled recovery if needed. Check
both the Actions run history and the CRM warnings; persisted checkpoints let a
later run catch up within Meta's available lead history. See
[GitHub schedule behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

Standard GitHub-hosted runners are free for public repositories; storage and other
paid features have separate limits. This workflow uploads no artifacts. Review
[GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
if repository visibility or runner choice changes.

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

The importer checks the retrieved form's Page ownership, lead/form IDs and activation boundary before importing. It uses a fixed Graph host, 15-second HTTP timeout, bounded responses and cursor pagination. It does not follow API-provided next-page URLs. Campaign-name retrieval stores a display name on the receipt; it does not rewrite an imported lead.

The Actions processor requests enabled form scans about every 30 minutes, overlaps the previous checkpoint by 30 minutes and clamps the interval to activation. A scan advances its checkpoint only after all IDs in the interval are committed. A failed scan keeps its old checkpoint, so retries can replay IDs safely.

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
| `GET .../connections/health/` | None | `enabled`, `execution_mode`, heartbeats, attempt/success timestamps, interval/warning thresholds, `processor_delayed`, connections with counts/backlog/forms (`scan_delayed`) |
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

For the Actions path, run `python manage.py test intake uploads notifications feedback --noinput`
against isolated PostgreSQL. `intake.test_preflight` also exercises the public-log
entry point and signing-key fallback handling.

The automatic-import browser check uses `frontend/scripts/background-fixture.py`.
Set `DATABASE_URL` to a **local** PostgreSQL database named
`test_crm_background_browser`; the fixture refuses any other database name or
non-loopback host. From the repository root, seed it and start the API:

```sh
backend/.venv/bin/python frontend/scripts/background-fixture.py seed
backend/.venv/bin/python frontend/scripts/background-fixture.py serve
```

In a second terminal, start the frontend from `frontend` with
`NEXT_PUBLIC_API_URL=http://localhost:8064 npm run dev -- --hostname 127.0.0.1 --port 3064`.
Then run `node frontend/scripts/background-browser.cjs` from the repository root
with the same isolated `DATABASE_URL`. Set `PUPPETEER_MODULE` if puppeteer-core is
installed outside the frontend, and use local Chromium. The check resets only
its dedicated fixture database and simulates Meta responses; it does not contact
production Meta or Supabase.

Local verification on 19 September 2026: the 134-test PostgreSQL intake/upload/
reminder suite passed, followed by all six preflight tests (including the added
Actions entry-point check). Frontend build, type check, targeted lint, schema-drift
check and workflow YAML/gate checks passed. Chromium passed automatic imports
without recovery clicks, webhook replay deduplication, the real 30-second Fresh
list refresh, warnings/recovery, uploads and desktop/mobile layouts.

The wider 269-test regression run had nine errors that also occur on the unchanged
revision: seven lead call/reopen tests use PostgreSQL-incompatible locking queries,
and two reset-command tests assume configured storage credentials. These are
outside this change. Production token retrieval, runner access, shared storage,
baseline preservation and the 24-hour observation still require the cutover above.
