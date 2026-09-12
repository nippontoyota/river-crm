# Customer feedback calls

`FEEDBACK` users work at `/feedback`. Admins and branch managers can monitor and
reassign there; the CEO has a read-only report at `/ceo/feedback`. SO/CRE users
cannot access feedback records, notes, or exports. Sales ownership is unchanged.

## Activation and deployment

Deploy the API, frontend, Celery worker, and the existing single Beat scheduler
together. Run the normal `python manage.py migrate --noinput` deployment step.
Migration `feedback.0002_activate_feedback` records the activation timestamp.
Only qualifying audits recorded after that boundary create tasks; migration does
not scan historical leads. The activation row must be retained across deployments.

Create **Feedback Caller** accounts in Admin → Users, selecting a branch. Tasks
without an eligible caller remain unassigned until staffing is available. Admins
can also change caller branches in the user directory. Open calls redistribute;
completed tasks, attempts, and assignment histories retain their original owners.

The existing Beat scheduler runs `feedback.tasks.process_feedback_queue` every
60 seconds. Check worker/Beat logs and the report's unassigned/overdue counts
after deployment. A missed scheduler run delays alerts, not stored due dates;
the next successful run catches up without duplicating notifications. This is a
manual calling workflow, with no telephony or messaging provider integration.

## Scheduling and reporting rules

- Explicit test-drive completion → TDF at 09:00 next calendar day.
- Explicit `sales_outcome=BOOKED` transition → PBF at 09:00 next calendar day.
- Explicit `sales_outcome=RETAILED` transition → PSF at 09:00 on the third day.
- All timestamps use Asia/Kolkata, including weekends. A walk-in appointment
  does not trigger PBF; retail does not invent a missing booking event.
- One task per lead/type. Lost/cancelled sales and later milestones do not
  remove earlier feedback obligations. Deleted leads are excluded from queues.
- Allocation uses the lowest open workload in the branch, with user ID ties.
  A database row lock serializes allocation, attempts, and manual reassignment.
- Unanswered/busy/switched-off attempts retry the next day at 09:00. The third
  unsuccessful attempt closes as unreachable. Customer-requested callbacks use
  a future chosen time and do not consume that limit. Completed, declined, and
  invalid-number outcomes require notes. Each write requires the current task
  revision to reject duplicate/stale submissions.
- Reports use original due date; retries never change that cohort. Completion
  rate is completed/generated tasks. On-time completion is by the end of the
  original due day. Current backlog ignores the date filter. Activity uses the
  attempt date, caller, and branch. Coverage is distinct leads with feedback
  since activation divided by all leads in the selected branch scope; caller
  workspaces show their own coverage numerator. Type totals can overlap by lead.
- Each notification links to its task. Reading alerts does not resolve work.
  Assignment changes remove old alerts; access is checked again on every read.
- Questionnaires are deferred. V1 records call outcomes and notes only.

## Interfaces

`GET /api/feedback/`, `GET /api/feedback/{id}/`,
`GET /api/feedback/summary/`, `GET /api/feedback/options/`, and
`GET /api/feedback/export/` share role/branch access rules. Lists are paginated.
Filters: `kind`, `bucket`, `q`, `caller` (ID or `unassigned`), repeatable `branch`,
and CEO date filters `range`, `date_from`, `date_to`. `backlog=true` makes the list
and export ignore date limits, matching the current-backlog buttons.

`POST /api/feedback/{id}/attempt/` accepts `revision`, `outcome`, `notes`, and
`callback_at` for a requested callback. Only the assigned active caller may submit.
`POST /api/feedback/{id}/reassign/` accepts `revision` and `assigned_to`; admin or
the current branch manager may choose an active caller in that lead's branch.

`GET /api/ceo/feedback/` and `GET /api/ceo/export/feedback/` provide report aliases.
Notifications now include `feedback_task` and `feedback_kind`. Use
`GET /api/notifications/unread_count/?feedback=true`, `feedback_kind=TDF` to
filter alerts, and `POST /api/notifications/{id}/read/` to read one alert.

## Verification

From the repository root, using isolated local data:

```sh
DATABASE_URL=sqlite:////tmp/crm-feedback-test.sqlite3 backend/.venv/bin/python backend/manage.py test feedback accounts leads ceo notifications --noinput
```

Run `manage.py test feedback` against a local PostgreSQL database as well: the
concurrency test exercises real row locks and is skipped on SQLite. It verifies
that simultaneous events balance correctly and only one duplicate call attempt
is committed. No production connection is needed for these tests.

Frontend checks: `npm run typecheck`, `npm run build`, and ESLint for the feedback
components. `frontend/scripts/feedback-browser.cjs` checks the login destination,
tiles, notification filters, successful call recording, denied lead access,
mobile overflow, CEO read-only details, CSV export, admin account creation, and
manager branch scope. Supply `PUPPETEER_MODULE`
and `BROWSER_EXECUTABLE` if Puppeteer/Chromium are installed outside the project.
It defaults to frontend port 3039 and API port 8039. The test API must allow
`http://127.0.0.1:3039` in both `CORS_ALLOWED_ORIGINS` and
`CSRF_TRUSTED_ORIGINS`; build the frontend with
`NEXT_PUBLIC_API_URL=http://127.0.0.1:8039`.

For that browser fixture, use a fresh isolated database and seed an active
`caller@feedback-browser.test` FEEDBACK user named Asha in Kochi and a
`ceo@feedback-browser.test` CEO user. Also seed `admin@feedback-browser.test` as
ADMIN and `manager@feedback-browser.test` as SALES_MANAGER in Kochi. All four
use password `FeedbackBrowser123!`; configure Kochi in `SystemConfig.lists.branches`.
Set the isolated activation timestamp before the test event. Create a Kochi lead
named Anjali Menon and audit an explicit test-drive completion two days ago so
its TDF is already due; run `process_feedback_queue()` to create its alerts.
Additional PBF/PSF leads are optional. Never seed these fixtures in production.
