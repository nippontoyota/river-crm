# Customer feedback calls

Feedback callers work at `/feedback`. Admins and branch managers monitor and
reassign there; the CEO has read-only reporting at `/ceo/feedback`. Sales
ownership is unchanged. CE and PS/SO users can request feedback from their own
customer detail and see approval status, but cannot read feedback answers.

## Eligibility and scheduling

| Recorded event | Type | Original due time (Asia/Kolkata) |
| --- | --- | --- |
| Explicit test-drive completion | TDF | Next calendar day, 09:00 |
| Explicit Booked transition | PBF | Next calendar day, 09:00 |
| Explicit Retailed transition | PSF | Third calendar day, 09:00 |
| Service request resolved | SVC | Next calendar day, 09:00 |
| Approved management request | GEN | Selected future time |

Weekends are included. Fresh enquiries, Meta imports, test-drive appointments,
and missed sales calls do not create feedback. An incomplete record does not
establish a booking or resolution; use a reasoned manual request instead.

Sales events retain one task per lead/type. SVC has one task per resolution
event, including vehicles with no sales lead, and uses the servicing branch.
Reopening service cancels its open call with a reason; completed calls remain.
Resolving again creates a new task. Service resolution and feedback generation
commit or roll back together.

Feedback callers are general call center staff and have no employee branch.
Allocation uses the lowest open workload among all active callers, with user ID
ties, including calls with no branch recorded. Work stays unassigned only when
no active caller is available. Staffing reconciliation and manual reassignment
retain assignment history. Callers can act only on their assigned tasks across
all branches. Customer branch changes retain the caller; managers still monitor
only their branch's tasks and can reassign them to any active feedback caller.

Unanswered/busy/switched-off attempts retry the next day at 09:00. The third
unsuccessful attempt closes as unreachable. Requested callbacks use a future
chosen time without consuming that limit. Collected/declined/invalid-number
outcomes require notes. Revisions reject stale submissions.

## Questionnaires, issues and complaints

New tasks use fixed questionnaire version 1, defined in `questionnaires.py`.
Published versions must remain immutable; add a new version for changed wording.
Collected calls require every stage answer (YES, NO, NOT_DISCUSSED), satisfaction
1–5 or null (Not provided), `further_help`, and details if help is needed. Legacy
tasks retain a null version and may still be completed with notes only.

A rating of 1–2, further help, or an unresolved service issue opens a separate
feedback issue. Completing the call does not resolve that issue. Active branch
managers receive an in-app notification immediately; admins receive one when
there is no active manager or acknowledgement is overdue by 24 hours. Each
recipient is notified once per issue. Managers/admins acknowledge or resolve
with notes; reviewer, timestamps and issue events are retained.

The caller can explicitly raise a complaint after collecting feedback, selecting
a category/subtype and confirming the description. One linked complaint per
feedback issue prevents duplicate submissions. Complaints remain owned by the
Complaints department. Resolving/closing its ticket resolves the feedback issue
in the same transaction. Feedback users see the ticket number/status and issue
history, without gaining access to the wider Complaints or Service workspaces.

## Requests and historical catch-up

Sales staff submit a reason and future preferred time for their own assigned
lead. Managers approve only their branch; admins approve across branches.
Rejection requires notes. Direct management requests are approved immediately.
A lead cannot have another pending request or open GEN task. A later request is
allowed after closure. A preferred time that elapsed while waiting for approval
must be replaced with a future time.

Admin historical preview scans only verified events in the last 30 days and
creates nothing. It shows event/original due dates, customer, branch, proposed
caller and exclusion or staffing reasons. Saving up to 200 selected events
rechecks eligibility under source/feedback locks. Repeated saves return existing
tasks. Historical event/due dates are retained; `next_call_at` is the selected
future time, origin is HISTORICAL, and on-time performance is null.

Reports use original due dates. Rating averages exclude null ratings. Service,
requested and historical totals remain separate from automatic sales-lead
coverage; origin filters and origin summaries allow separate comparisons.
Current backlog and unresolved-issue count cover all due dates. Activity uses
attempt dates. Customer counts use lead or service vehicle identity, never phone
matching. Contact history remains limited to feedback records visible to the user.

## API

Existing list/detail/options/summary/export endpoints remain available:

- `GET /api/feedback/`, `GET /api/feedback/{id}/`
- `GET /api/feedback/options/`, `GET /api/feedback/summary/`
- `GET /api/feedback/export/` (CSV, including structured answers and issue status)
- `GET /api/ceo/feedback/`, `GET /api/ceo/export/feedback/`

Filters: `kind`, `origin`, `bucket` (including `issues` and `cancelled`), `q`,
`caller` (ID or `unassigned`), repeatable `branch`, `range`, `date_from`, `date_to`.
`backlog=true` ignores date limits for the task list/export. Lists are paginated.

Writes:

- `POST /api/feedback/{id}/attempt/`: `revision`, `outcome`, `notes`, optional
  `callback_at`; collected calls add `answers`, `satisfaction`, `further_help`,
  `help_details`. The server fixes the questionnaire version per task.
- `POST /api/feedback/{id}/reassign/`: `revision`, `assigned_to`.
- `POST /api/feedback/{id}/issue/`: `revision`, `status` (ACKNOWLEDGED/RESOLVED),
  `notes`. Linked unresolved complaints must be resolved by Complaints first.
- `POST /api/feedback/{id}/complaint/`: `revision`, `category`, `subtype`,
  `description`, `confirmed=true`. Retrying returns the original ticket.
- `GET/POST /api/feedback-requests/`: creation accepts `lead`, `reason`,
  `preferred_at`; listing accepts `lead` and `status`.
- `GET /api/feedback-requests/customers/?q=…`: scoped customer search.
- `POST /api/feedback-requests/{id}/review/`: `revision`, `decision`
  (APPROVED/REJECTED), `review_notes`, optional replacement `preferred_at`.
- `GET /api/feedback/historical-preview/`: admin only.
- `POST /api/feedback/historical-import/`: admin only, `records` (preview keys),
  `next_call_at`.

## Deployment and pilot

Run the normal additive migrations, then deploy backend and frontend together.
Migration `feedback.0003` preserves existing tasks and the activation timestamp
from `feedback.0002`. Do not reset that row or automatically import history.

The existing `crm-background.yml` processor calls `process_feedback_queue`;
there is no additional scheduler. It reconciles assignments, generates due-call
alerts and checks unacknowledged issues. The legacy Celery Beat schedule also
calls the same function; use the scheduler already active in the deployment.
Verify a successful processor run after migration and deployment. The five runs
ending at 2026-09-21 10:30 UTC were successful before this upgrade; see run
35589063447 for the pre-deployment check. This is not post-deployment evidence.

Pilot customers from one branch with active call center staff. Confirm the
service task and manual approval flow,
review the first completed questionnaires and manager/admin notifications, then
select historical customers for catch-up. Calls remain unassigned only when no
active call center staff are available. Actual customer calls and
historical customer selection are management activities, not migration steps.

## Verification

```sh
DATABASE_URL=sqlite:////tmp/crm-feedback-test.sqlite3 backend/.venv/bin/python backend/manage.py test feedback servicing complaints accounts leads ceo notifications --noinput
```

Also run `manage.py test feedback servicing` against isolated PostgreSQL. The
concurrency tests cover allocation/attempt deduplication, simultaneous service
resolution, reopening during a call, duplicate manual requests, historical
imports and negative feedback racing with a sales update. They are skipped on
SQLite. Writers lock source rows before the shared
feedback lock; feedback operations do not acquire source row locks afterward.

Frontend: `npm run typecheck`, `npm run build`, and ESLint on changed feedback
files. Browser checks use only an isolated local fixture:

```sh
backend/.venv/bin/python frontend/scripts/feedback-fixture.py
backend/.venv/bin/python frontend/scripts/feedback-fixture.py serve
# In a separate frontend checkout/copy, build or run with:
NEXT_PUBLIC_API_URL=http://127.0.0.1:8039 npm run dev -- --hostname 127.0.0.1 --port 3038
node frontend/scripts/feedback-browser.cjs
```

The fixture hardcodes a temporary SQLite database and refuses a second seed.
Supply `PUPPETEER_MODULE` and `BROWSER_EXECUTABLE` when installed outside the
project. The browser script checks questionnaires, service-only calls, optional
complaints, approval and historical actions, issue acknowledgement, desktop/mobile
overflow, exports, notification filtering, branch permissions and CEO read-only
behavior. It stores screenshots under `/tmp/crm-feedback-*.png`.
