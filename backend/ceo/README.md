# CEO reporting

The CEO workspace is `/ceo`. Admins create CEO accounts in Team and maintain
monthly targets and customer financial records at `/business-controls`.
CEO access permits company-wide reads and CSV exports. Business mutations remain
blocked at authentication and report permission boundaries; login, refresh and
logout keep their normal authentication behavior.

Apply migrations with `python manage.py migrate` when releasing the backend,
before serving the updated frontend. No financial amounts or targets are seeded.
The history migration is idempotent and copies existing verified records. It can
take time on large databases; run it in the normal release maintenance window.

## Definitions

- E: enquiry date. T: explicitly completed test drive. B/R: first explicit
  booking/retail transition. A cancellation and later rebooking retain one B.
  Skipping a stage never manufactures its milestone.
- Period results filter each achievement date and its recorded branch, RTO,
  campaign, CE and SO snapshots. Later reassignment does not move past results.
- Enquiry cohorts select leads by enquiry date and current dimensions, then show
  their verified achievements through today. Conversion denominators use these
  cohorts, with chronological intersections for T→B and B→R.
- Current workload and balances are independent of enquiry-period filters.
  Lead register defaults to enquiries in the period and provides an all-dates
  workload option. Milestone drilldowns use the same query as their parent total.
- Current ownership is separate from activity by the actual recorded actor.
  Receptionists receive intake attribution; SO and CE milestone results use
  milestone owners. Sales managers drill into their branch; admin is excluded
  from operational staff comparisons but remains visible as a history actor.
- Operational counts exclude archived leads. Financial records retain archived
  customers, and their lead histories remain accessible by ID.
- Old audit, call and follow-up timestamps are preserved. Missing historical
  branch/owner snapshots stay “Not recorded”; current ownership is not inferred
  into past events. Use enquiry cohorts for existing leads grouped by today's
  branch/owner. Unverified booking and retail states appear in reporting coverage.

## Financial and target controls

Amounts are INR final customer totals after discounts, including taxes/charges.
Agreed values, confirmed retail values and dated cash entries are separate.
Net collections = payments − refunds − payment reversals + refund reversals.
Balances use the current agreed value, or confirmed retail value for retailed
leads, less lifetime net collection. Unknown amounts stay unknown. Cancellation
balances and customer credits are reported separately from outstanding amounts.

Entries are immutable, require notes and an idempotency key, and can be corrected
with a new valuation or reversal. A reversal references one unreversed payment
or refund from the same lead. Refunds cannot create negative customer balances,
including on intervening dates when backdated. The lead row serializes writers.
Targets are unique per month/branch or month/branch/SO and retain revisions;
branch totals are not added to SO allocations. Allocation gaps flag under- and
overallocation. Targets only appear for matching monthly reporting scopes.

## API and verification

`/api/ceo/` exposes `options`, `overview`, `branches`, `people`, `leads`, `segments`,
`finance` and `complaints`; record details/history, finance entries and target
revisions are separate endpoints. `/api/management/targets/` and
`/api/management/finance/` are admin controls. Reports are cached for at most
60 seconds; Refresh explicitly bypasses the cache.

Common filters: repeated `branch`, `range` (`today`, `mtd`, `previous_month`,
`quarter`, `custom`, `all`), `date_from`, `date_to`, `mode` (`period`, `cohort`),
`role`, `employee`, source/RTO/campaign/activity/sub-activity/model/status/category.
Lead filters include `metric=E|T|B|R`, `scope=workload`, `ownership=handled`,
`followup`, `age` and `q`. Complaint filters are separate. Dates use Asia/Kolkata.
Lists and histories paginate at 25, maximum 100. CSV exports stream the full
filtered result, with formula-safe cells, reporting metadata and matching order.

Run `python manage.py test ceo leads analytics accounts complaints uploads` and
the frontend lint/build checks. CEO tests cover permission boundaries, totals,
drilldowns, exports, cancellation/reassignment, old histories, skipped milestones,
legacy backfill, refunds/reversals, idempotency and query-count scaling.
