# Verification record

Prepared 11 September 2026 for the Nippon Toyota internship presentation.

## Application checks

**102 backend tests passed in 98.912 seconds.** Django system checks found no issues. The test database was isolated and destroyed by the runner after completion.

Command, run from the repository root:

```bash
DATABASE_URL=sqlite:////tmp/nippon-internship-check.sqlite3 \
CACHE_URL= CACHE_TTL_SECONDS=0 CELERY_TASK_ALWAYS_EAGER=true \
backend/.venv/bin/python backend/manage.py test \
leads analytics complaints uploads accounts.tests.UserOffboardingTests \
--noinput --verbosity 1
```

The run included a missing `backend/staticfiles/` directory warning and an expected cache `ConnectionError` log exercised by the cache-failure tests. Neither failed the run.

Frontend checks, run from `frontend/`, both passed:

```bash
npm run typecheck
npm run lint
```

These checks verify selected current code workflows and static frontend consistency. They do not verify a live rollout, production database configuration, scheduler execution, browser acceptance, load performance or every security boundary. No production customer data was accessed. The checks were performed during presentation preparation, not as evidence of the presenter's original weekly attendance or personal contribution.

## Presentation checks

- 46 editable widescreen PowerPoint slides, with speaker notes on each slide.
- Matching 46-page PDF exported from the PowerPoint through LibreOffice.
- Presenter notes in Markdown and printable PDF.
- Programmatic validation of slide/page counts, notes completeness, shape boundaries, retained slide text in the PDF and PDF text boundaries.
- Visual review of all slides using four contact sheets, followed by layout adjustments to timeline labels and short import cards.
- Two real, credited historical photographs of the Kalamassery showroom; no fabricated office imagery or customer records.
- Company facts linked to the official dealership site and company LinkedIn profile; technical claims traced to local implementation files.
- User details, personal experiences, exact contributions, internal hierarchy and the eight-week reconstruction remain clearly marked for confirmation/customisation.

Run the artifact checks:

```bash
/tmp/nippon-slides-venv/bin/python presentation/internship/source/verify_artifacts.py
```

Application source files were not changed. New deliverables are confined to `presentation/internship/`; generation and verification tools use temporary resources under `/tmp`.
