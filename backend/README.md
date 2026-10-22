# Incheon Mobility CRM API

Run locally:

```bash
cp .env.example .env
source .venv/bin/activate
python manage.py migrate
python manage.py runserver
```

For local legacy Celery mode, run the worker and scheduler in separate terminals:

```bash
celery -A config worker --loglevel=INFO
celery -A config beat --loglevel=INFO
```

Open API documentation at `/api/docs/`.

The browser only calls Django REST endpoints. Django owns authentication, role checks, audit records, and lead visibility. Configure Supabase credentials through environment variables, never in source files. Production background processing uses GitHub Actions and the existing database; follow the intake cutover guide before enabling the schedule.

WhatsApp SO introduction previews are available without credentials. GreenAds Global (Telinfy) is the selected provider. See [WhatsApp setup and activation](notifications/WHATSAPP.md) for configuration, behavior, and the account API details needed to complete live delivery.

Lead Intake setup, API contracts and recovery: [intake/README.md](intake/README.md).

## Loading performance

The [22 October 2026 performance report](../performance/loading-2026-10-22.json)
contains five paired measurements for 122 role/endpoint combinations across all
10 roles. It includes sample durations, ranges, payload sizes, query counts, and
response comparisons. These are **local API timings**, using disposable SQLite
data: 200 leads, 2,000 calls, 800 follow-ups, 20 complaints, 20 service requests
with 100 history events, 40 feedback tasks, and five upload batches. They exclude
network transfer, authentication and browser rendering; production PostgreSQL
can have different query plans.

| Role | Example data request | Before median | After median |
| --- | --- | ---: | ---: |
| Admin | Analytics | 1,783.3 ms | 31.1 ms |
| Admin | Lead list | 60.0 ms | 12.1 ms |
| CEO | Overview | 71.8 ms | 72.5 ms |
| CE | Full assigned lead workspace | 38.2 ms | 38.4 ms |
| PS/SO | Full assigned lead workspace | 27.1 ms | 27.5 ms |
| Sales Manager | Branch analytics | 61.0 ms | 61.1 ms |
| Receptionist | Dashboard analytics | 3.5 ms | 3.3 ms |
| Complaints | Queue | 6.2 ms | 6.1 ms |
| Feedback | Tasks | 11.8 ms | 11.6 ms |
| Service | Requests | 9.0 ms | 4.5 ms |
| Meta Uploader | Upload summary | 2.7 ms | 2.7 ms |

The targeted gains come from counting employee calls separately from assigned
leads, calculating each lead's history summaries without multiplying calls by
follow-ups, and loading service event histories only for detail responses.
Admin analytics uses six small queries instead of four expensive queries;
service lists use three instead of five. Differences on unchanged endpoints
are within the measured ranges. All 122 response comparisons matched, excluding
the report-generation timestamp.

The frontend reuses the shell's verified session within its children and consumes
a parent route's verification once. Subsequent navigation still revalidates the
session. Admin lists display independently of staff and analytics requests, with
separate errors and retry controls. Assignment remains disabled until its data
is ready. Superseded lead searches are cancelled, polling avoids overlapping
reads, and mutations during a shared refresh schedule one follow-up refresh.
Full-list output, permissions, metric definitions, and refresh intervals remain
unchanged. No dependencies, cache lifetime changes, migrations, or infrastructure
changes are required.

Live role timings for https://river-crm-phi.vercel.app/ remain **unmeasured** because
an authenticated browser connection was unavailable. Three homepage HTML GETs
took 371, 78, and 68 ms; these do not measure role data loading. To complete live
verification, use authenticated role sessions and record five first/repeat
navigations, filter/search changes, detail opens, and refreshes per data screen.
Record the time until usable data appears, request count, bytes, errors, and the
existing `Server-Timing` application/database durations. Use read-only scenarios
on production and isolated data for mutation tests.

Run the isolated benchmark from the repository root:

```sh
backend/.venv/bin/python backend/profile_loading.py --output /tmp/loading.json
backend/.venv/bin/python backend/profile_loading.py --baseline-ref <previous-commit> --output /tmp/loading-comparison.json
```

The benchmark always uses an in-memory database, disables external analytics
caching, and forces test authentication. The comparison swaps only the three
query implementations against the same fixtures, alternating previous/current
requests. It exits unsuccessfully for unexpected HTTP responses or payload
differences. Use the baseline commit recorded in the saved report to reproduce
the original comparison.

From `frontend`, run `npm run test:loading`, `npm run typecheck`, `npm run lint`,
and `npm run build`. For browser checks, build with
`NEXT_PUBLIC_API_URL=http://localhost:8000 npm run build`, start with
`npm run start -- --hostname 127.0.0.1 --port 3100`, then run
`npm run test:browser-loading` in another terminal. Set `CHROME_EXECUTABLE` if
Chromium is installed somewhere other than `/snap/bin/chromium`. These checks use
a temporary browser profile and intercept API requests with synthetic responses.

Validation covered five frontend loading checks, eight browser scenarios, and
393 backend test cases (390 on the unchanged baseline). The three new backend
regression tests pass. The broader suite has the same 13 failure reports, two
errors, and 21 skips on both versions; it is not fully green. Frontend lint has
the same five existing errors and four warnings on both versions. Typecheck and
the production build pass. No deployment was performed.

## Follow-up and colour reporting rules

Lost and Not Interested leads are excluded from SM follow-up summaries, buckets,
exports, and active Admin/CEO follow-up workload. Historical calls/follow-ups and
sales conversion totals remain available. SM's PS/SO performance table and CSV
omit the Calls column; the API retains its field for existing consumers.

Manual lead creation requires `qualification_input.variant` to contain a configured
colour or `No Preference`. Explicit blank/not-set colours are rejected on edits;
unrelated partial updates remain valid. `No Preference` is always provided by
System Config. Spreadsheet and automated intake default missing colour to that
value, preserving an existing colour on duplicate updates.

Migration `leads.0026_normalize_lead_colors` normalizes existing missing/not-set
colours and creates missing qualification records in batches without fabricating
staff activity. Other qualification fields remain unchanged. Rollback retains the
normalized data. The existing backend build runs `manage.py migrate --noinput`;
run that command when deploying through another path. Deploy backend and frontend
together because older manual-entry clients may omit the now-required colour.

Regression checks are in `leads.test_business_rules`,
`analytics.tests.FollowupBusinessRulesTests`, and `frontend/tests/browser-loading.cjs`.
The loading benchmark above records the earlier performance-only changes; reporting
payloads intentionally change under these new business rules.

## CEO branch sales table

The CEO overview and Branch performance page show Branch, Total, Booked, Retailed,
Lost, Conv., and Last call. Counts use current sales status for enquiries received
in the selected dates, matching SM semantics. Lost includes Not Interested;
conversion is retailed / total. Last call uses calls within those dates for the
same enquiry cohort and opens the customer's history.

`GET /api/ceo/branch-sales/` and `/api/ceo/export/branch-sales/` serve this view.
Lead lists/exports accept `branch_metric=total|booked|retailed|lost` alongside the
existing branch, date and customer filters. The overview adds `branch_sales`;
existing milestone-based `branches` responses remain compatible. Latest calls
are selected with one database window query across branches. No migration is needed.
