# Verification and evidence

Revised 30-slide visual edition. Prepared 9 September 2026 for the Incheon Mobility CRM operations demo.

## Scope

Reviewed the current backend models, permissions, dedicated lead actions, allocation logic, uploads, complaints, account lifecycle, reminder tasks and analytics. Cross-checked them against the frontend screens, navigation, request payloads and existing workflow tests. Read the original Revera Scooter CRM PRD as background; used current implementation when it differed.

No live customer data, account credentials or production database queries were needed. Application code was not changed. Generated files are confined to `presentation/`; temporary build tools and test resources were placed under `/tmp`.

## Automated workflow verification

The following application checks passed during the original project review. This revision changes presentation artifacts only; application tests were not rerun for the visual redesign.

Final corrected command:

```bash
DATABASE_URL=sqlite:////tmp/crm-presentation-verification.sqlite3 \
CACHE_URL= CACHE_TTL_SECONDS=0 CELERY_TASK_ALWAYS_EAGER=true \
backend/.venv/bin/python backend/manage.py test \
leads analytics complaints uploads accounts.tests.UserOffboardingTests \
--noinput --verbosity 1
```

**Result: 84 tests passed in 89.494 seconds. Django system checks reported no issues.** Django used its isolated test database and destroyed it afterward. The run reported an absent staticfiles-directory warning and the expected cache-failure log exercised by the failure-handling tests; neither failed the suite.

An earlier invocation used the incorrect class name `EmployeeOffboardingTests`, producing a test-discovery error. This was corrected to `UserOffboardingTests`, and the full selected suite was rerun successfully. No test failure was hidden or dismissed.

Coverage includes own-lead visibility; CRE-to-PS handoff; pending and loss outcomes; booking and retail journeys; branch-scoped read-only manager views; complaint create/read/resolve permissions; duplicate imports; employee disable/delete; branch-safe replacement; stale offboarding previews; and held reminder review.

This does not verify deployed scheduler operation, notification presentation, production account setup, live source integrations, all browser behavior, or every generic endpoint permission. Those limits appear in the presenter briefing.

## Artifact verification

- 30 editable PowerPoint slides, each with presenter notes and a repository reference or an explicit proposed-practice basis.
- 30-page slide PDF exported from the PowerPoint with LibreOffice.
- Presenter-notes PDF with the detailed explanations grouped under the 30 revised slide titles.
- Six-page demo briefing PDF with role switching, five scenario scripts, Q&A and current limitations.
- Programmatic checks: slide count, notes completeness, shape bounds, retained slide body text in the PDF and PDF text bounds.
- Visual review of all 30 slides, including the access matrices, lead journey, decision tree, branch hierarchy, scenario storyboards, complaint handoff and follow-up loop.
- Revised theme: plum, lavender and orange, with larger labels and shorter copy.
- 23 visual / infographic slides and 7 table slides; approximately half the original body text.
- Tables, diagrams and charts use editable PowerPoint objects. Charts contain illustrative values, not production figures.
- No screenshots of a live application are included or implied. The visuals explain verified workflow concepts.

Run the artifact checks with the temporary presentation environment:

```bash
/tmp/crm-presentation-venv/bin/python presentation/source/verify_artifacts.py
```

## Evidence map

| Subject | Main implementation evidence | Revised slides |
|---|---|---|
| Roles and permissions | `backend/accounts/models.py`, `frontend/src/components/app-shell.tsx`, complaint permissions | 2–5 |
| Admin setup / intake | Frontend team and Lists screens; `backend/uploads/tasks.py`, lead creation | 6–8 |
| Allocation / hierarchy | `backend/leads/views.py` assignment actions; frontend lead desk | 9–10 |
| CRE qualification | Sales workspace qualification form; dedicated lead update | 11–12, 17–18 |
| PS outcomes / follow-ups | Sales workspace outcome menu; lead update and follow-up validation | 13–15, 19–20, 22 |
| Five requested scenarios | Lead and complaint workflows, backed by existing tests | 16–21 |
| Receptionist capture | Receptionist capture form; creation and analytics actions | 23 |
| Complaint handling | Complaint permissions, serializers and update actions | 21, 24 |
| Manager reporting | Branch lead scope and `backend/analytics/views.py` | 25–26 |
| Daily operations | Suggested team routine; not an automated schedule | 27 |
| Exceptions / reminders | Dedicated lead validation; reminder tasks; deployment configuration | 28 |
| Employee lifecycle | `backend/accounts/offboarding.py`, lead reassignment and reminder review | 29 |
| Pilot decisions | Proposed operating agreements and acceptance checks | 30 |

## Material differences from the original PRD

- CRE and PS/SO are distinct roles in the current application; SM, complaints and receptionist workspaces also exist.
- Current import sources use Admin Lists; unknown or blank source is not simply accepted as an Unknown bucket.
- Current import UI skips duplicate phones by default rather than exposing the full original overwrite/import-as-new workflow.
- CRE/PS follow-up selection is day-based, with a three-day limit; it is not the PRD’s general exact-time scheduling UI.
- Employee offboarding routes active work and holds reminders; it does not merely leave all active leads on an inactive employee.
- The visible app shell does not include the proposed notification bell.
- Dashboard stage figures are current-state measures; they should not be represented as historical cohort conversions.
- The current frontend does not expose a dedicated Reopen button despite the server capability.

## Current operational limitations worth rehearsing

The presenter briefing gives plain-language responses for these points: global Auto assign scope; missing receptionist branch/enquiry date; no automatic lead-to-complaint link; shared lead follow-up replacement across CRE and PS; PS `call_status` omitted from the save payload; unsaved profession selection in the CRE qualification form; no automatic five-attempt loss rule; complaint updater becomes assignee; resolution timestamps persist across reopened status; and incomplete proof of live reminders.

These were documented for an accurate presentation. Fixing application behavior was outside the requested presentation task.
