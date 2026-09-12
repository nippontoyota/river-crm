# Nippon Toyota internship: presenter notes

Eight-week draft timeline. Confirm personal details, contribution, dates and experience before presenting.

## 01. Internship at Nippon Toyota

Introduce yourself, your course and your internship dates. Explain that the mobility CRM is one project undertaken during the internship. The workspace calls it Incheon Mobility CRM and contains River scooter configuration; Nippon Toyota is the internship host supplied by the presenter. Do not imply this is Toyota’s official enterprise CRM. Personal details and the eight-week allocation remain editable until confirmed.

## 02. Presentation route

The deck has a main internship narrative followed by a technical appendix for viva questions. Week 1 and Week 2 themes come directly from your request. The later weekly allocation is a proposed reconstruction, not an attendance record. Explain that the project discussion covers the current repository and that your exact personal contribution should be confirmed with your internship diary.

## 03. Nippon Toyota: company profile

Distinguish Toyota, the vehicle brand, from Nippon Toyota, the dealership business hosting the internship. The dealer contact page identifies Nippon Motor Corporation Pvt. Ltd. The company’s own LinkedIn profile gives 27 January 2000 as its establishment date. The official dealership site lists locations across Kerala and the used-car page lists Nippon U Trust at Kalamassery. Avoid unverified employee counts, turnover or market rankings.

Evidence: https://nippon-toyota.com/contact-co01b.html; https://www.linkedin.com/company/nippon-toyota-pvt-ltd; https://www.nippon-toyota.com/about-us.html; https://www.nippon-toyota.com/used-cars.html

## 04. Customer service shapes the work

Paraphrase the published dealer mission: the company places customer satisfaction first and brings sales, service and service parts together for convenience and efficiency. The department activities are a general dealership process explanation, not a claim that this project implements workshop job cards, inventory, finance underwriting or Toyota integrations. The project focuses on customer enquiries, sales follow-ups and complaints.

Evidence: https://www.nippon-toyota.com/cms/about-us/dealer-mission-v1.txt

## 05. My workplace: Kalamassery showroom

The presenter confirmed this as the internship location. The official location page describes a showroom and service centre at this address. These public photographs show the real Kalamassery facility in 2011 and 2012. They are historical building views, not photographs of the presenter’s desk or the current office interior. If available, replace or supplement them with your own current workplace photographs.

Evidence: https://nippon-toyota.com/contact-co01b.html; https://commons.wikimedia.org/wiki/File:Kalamassery_Toyota_Office.JPG; https://www.flickr.com/photos/sreejithmsivadasan/5974734010

## 06. Company leadership and departmental hierarchy

The official company site names M. A. M. Babu Moopan as Dealer Principal and Athif Moopan and Naeem Shahul as Directors. The arrangement of branch management and functional departments is an illustrative dealership structure, because an internal organisation chart was not supplied. Do not present the connecting lines as verified reporting relationships. During rehearsal, replace the lower structure with the hierarchy explained during your induction, including your department and reporting mentor.

Evidence: https://www.nippon-toyota.com/cms/about-us/dealer-principal-v1.txt

## 07. Internship objectives

Use these as internship objectives rather than claims about activities you have already completed. Connect your academic knowledge to a business setting: customer data is useful only if employees can use it to make the next decision. Add the objectives agreed with your mentor and the specific responsibilities allocated to you. Explain how you will show evidence through code, tests, workflows and your weekly diary.

## 08. Project context: a mobility CRM

The repository’s README, API schema title and frontend package identify Incheon Mobility CRM. A migration seeds River Indie. The code does not establish a corporate relationship between Incheon Mobility, River and Nippon Toyota. Present this as a mobility CRM project worked on during the internship until the official project/client description is confirmed. Do not claim that all repository features were built by one intern or that the company has adopted the full system.

Evidence: README.md; frontend/package.json; backend/leads/migrations/0018_seed_river_indie.py

## 09. Weekly internship timeline

This is a proposed way to organise the project into an internship narrative. It is not a statement of actual calendar completion. Replace the week count and allocate each feature using your diary, commits and mentor feedback. If the internship was shorter, combine adjacent implementation stages; if longer, split design, testing or deployment. Week 1 remains induction and hierarchy; Week 2 remains research, requirements and follow-up.

## 10. Week 01: Introduction, hierarchy and work culture

Your requested first week focuses on the introduction to the company and the hierarchy. Explain the difference between sales, customer relations, reception, service and support teams. Add the names of the people you met and the induction activities you actually attended. A useful experience statement, if accurate, is: “I began to understand how employees coordinate around a single customer enquiry.” Do not imply participation in service work or meetings that did not occur.

## 11. Week 02: R&D, requirements and follow-up

Your requested second week focuses on R&D and follow-up. Describe what was researched, which existing process or form you reviewed, and the questions you took back to your mentor. Follow-up here means clarifying requirements as well as understanding customer follow-up operations. Suggested reflection, if accurate: “I learned to ask who performs each action and what happens when the customer does not respond.” Technology comparisons are proposed talking points unless your diary confirms you made them.

## 12. Week 03: Designing the solution

Proposed Week 3. Describe how the data model supports the workflow: a lead retains qualification, multiple calls, multiple follow-ups and audit events. The application distinguishes the customer executive from the sales employee. Discuss why sales outcome is separate from the initial contact status. Confirm whether these were design decisions you made or design elements you studied. Cite the models and routes as technical evidence, not as proof that they were completed in this exact week.

## 13. Week 04: Building intake and allocation

Proposed Week 4. Explain the three important entry patterns: admin/CE intake, receptionist walk-in capture and SO self-generated enquiries. Admins can allocate fresh leads to customer executives. Qualification then assigns the sales employee. The stored field assigned_so refers to the CE allocation, while assigned_ps refers to PS/SO ownership. This naming detail matters when explaining the implementation. Use a fictional record when demonstrating; describe only the screens or endpoints you actually implemented.

## 14. Week 05: Implementing the sales journey

Proposed Week 5. Follow one lead through qualification, pending sales discussion, booking and retail. Explain that a requested test drive is different from a completed one; the current completion action stores an audited timestamp once. Call outcomes and next follow-up rules keep queues meaningful. A booking does not automatically prove delivery or payment integration. Relate the code to the module you actually worked on and place later additions into their correct internship week.

## 15. Week 06: Adding operational support

Proposed Week 6. Explain how operational exceptions influence software design. Complaints have a separate lifecycle and permissions. Imports need a review stage because a successful upload can still contain invalid rows or duplicates. Staff departure must preserve history while moving active work to another owner or queue. Do not imply that the application deletes historical customer data when an employee account is offboarded. Match the weekly account to your actual contribution and progress.

## 16. Week 07: Analytics, testing and refinement

Proposed Week 7. Explain the tests that matter to users: can someone see another employee’s lead, can a manager see another branch, does a repeated test-drive click double count, and do configuration changes preserve historical records? The current verification run belongs to preparation of this presentation, not necessarily to your original Week 7. State that distinction. No production conversion rate or response-time improvement has been measured for the presentation.

## 17. Week 08: Delivery, documentation and review

Proposed Week 8. The repository includes a Render service definition and Vercel frontend configuration. Describe configuration and deployment work you actually performed. The checked-in Render setup enables eager Celery execution and does not define a worker or scheduler, so do not claim background reminders are live. For handover, explain the need to apply migrations, configure secrets, verify each role and document unresolved items. Add real mentor feedback rather than an invented endorsement.

## 18. Requirements translated into features

Frame the problem as project requirements. The repository does not prove the company previously lost enquiries or used a particular spreadsheet, so avoid inventing an as-is failure story. For each requirement, identify a visible behaviour or an API response that can confirm it. These acceptance examples are stronger than unsupported claims of improved sales. Link personal contribution to the requirements you actually handled.

Evidence: backend/leads/views.py; backend/accounts/offboarding.py; backend/uploads/tasks.py; backend/analytics/test_etbr.py

## 19. End-to-end customer enquiry workflow

Read the main path from left to right. Admin or CE capture and bulk imports feed the enquiry pool. A CE contacts the customer and qualifies an interested enquiry, retaining the original CE relationship while handing sales work to a PS/SO. The PS/SO records follow-up, booking and retail. Receptionist walk-ins and SO-generated enquiries can enter the sales route directly. A complaint is a separate ticket and is not an automatic transition from a lost lead.

Evidence: backend/leads/views.py; backend/leads/serializers.py; frontend/src/features/leads/sales-workspace.tsx

## 20. Roles and access boundaries

Do not confuse the company organisation chart with the application permission matrix. The browser chooses the workspace, while the backend enforces authorisation. CE is the display label for the legacy CRE role. Lead queries use assigned_so for CE ownership and assigned_ps for PS/SO. A sales manager without a configured location receives no branch leads. The complaint permission class gives admins list/retrieve access, CE and receptionists create/read access, and the complaints department update and notes access.

Evidence: backend/accounts/models.py; backend/leads/views.py; backend/complaints/permissions.py

## 21. Technology stack and responsibilities

The frontend manifest uses latest for Next.js, React and TypeScript, so this slide does not invent pinned versions. The backend requirements constrain Django to the 5.2 series and include Django REST Framework, SimpleJWT, Celery, Redis integration, openpyxl, psycopg and Supabase. SQLite is the default local database; DATABASE_URL chooses the deployed database. PostgreSQL is supported by the installed driver, but the live database provider was not inspected. External integrations shown as lead sources are labels, not proof of automatic ingestion.

Evidence: frontend/package.json; backend/requirements.txt; backend/config/settings.py

## 22. System architecture

The frontend communicates with Django rather than calling the database directly. Django owns authentication, request validation, record visibility and business transactions. File uploads use Supabase storage when credentials are configured, with a local storage fallback. Analytics can use Redis or local memory. Celery tasks exist, but deployment mode determines whether they run inline or on a worker. Dashed connections identify optional infrastructure, not verified live services.

Evidence: frontend/src/lib/crm.ts; backend/config/settings.py; backend/uploads/storage.py; render.yaml

## 23. Frontend structure and API communication

The frontend uses route groups for admin, sales, manager and receptionist screens. Feature directories contain the lead desk, sales workspace, complaints, analytics and team pages. src/lib/crm.ts defines request types and response mappings. The api helper includes credentials, adds CSRF headers for unsafe methods and retries once after a successful refresh response. sessionStorage holds cached user metadata, not the JWT. Backend checks remain necessary even if a link or button is absent from a user’s workspace.

Evidence: frontend/src/lib/crm.ts; frontend/src/components/app-shell.tsx; frontend/src/app; frontend/src/features

## 24. Backend modules and request processing

Django REST Framework viewsets provide resource endpoints and dedicated actions for behaviours such as qualification, assignment and test-drive completion. Serializers validate configured choices and outcome-specific fields. The action then checks ownership and performs related changes in a transaction. Not every model operation has the same rules, so prefer the dedicated workflow endpoints when explaining business behaviour. drf-spectacular publishes the OpenAPI schema and Swagger UI at /api/schema/ and /api/docs/.

Evidence: backend/config/urls.py; backend/leads/urls.py; backend/leads/serializers.py; backend/leads/views.py

## 25. Core database relationships

User has two lead ownership relationships: assigned_so is the CE and assigned_ps is the sales employee. LeadQualification is optional one-to-one with Lead. A lead can have many call logs, follow-ups and audit events. Complaints can optionally reference a lead and have their own notes. This slide simplifies fields and omits additional actor foreign keys for readability. The appendix lists the other operational entities. Protected references preserve history when an account or lead is involved in audit-related records.

Evidence: backend/accounts/models.py; backend/leads/models.py; backend/complaints/models.py

## 26. Lead fields and business meaning

The Lead model has a numeric primary key and a public UUID. Phone is indexed but not unique, so do not claim database-level duplicate prevention for manual intake. Qualification is a linked entity; historical activity labels remain stored on leads when configurable choices are retired. Indexes combine CE or PS ownership with status, and include source with creation time. The current data model stores timestamps and status snapshots, but does not implement a full event-sourced analytics warehouse.

Evidence: backend/leads/models.py; backend/leads/serializers.py

## 27. CE qualification and sales-state workflow

A fresh lead may move through response-related states such as RNR, switched off, callback or pending. For the normal CE route, qualification captures the buying context and assigns the PS/SO. Lost is a reasoned outcome with remarks. The PS/SO has separate sales outcomes: pending, booked, retailed and lost. This diagram shows the main business path rather than every server transition. A completed test drive is a parallel timestamp and does not change lead status, qualification or the open follow-up.

Evidence: backend/leads/views.py; backend/leads/serializers.py; backend/leads/metrics.py

## 28. Follow-up loop and reminder conditions

For the CE update path, the serializer rejects appointments in the past and more than three days ahead. Pending, callback and walk-in outcomes require a next appointment. Other paths have their own validations; do not claim identical validation across every endpoint. When processing due reminders, the task excludes resolved, already notified, held, deleted-lead and inactive-owner items. It records a notification and marks notified_at. A periodic schedule exists in settings, but delivery still needs a running scheduler or equivalent trigger.

Evidence: backend/leads/serializers.py; backend/leads/views.py; backend/notifications/tasks.py; backend/config/settings.py

## 29. Authentication request sequence

The login endpoint validates credentials and returns user metadata while setting HttpOnly access and refresh cookies. The access lifetime is 15 minutes and refresh lifetime is 7 days. In non-debug mode cookies are Secure and SameSite=None. For cookie-authenticated unsafe requests, CookieJWTAuthentication invokes a CSRF check. Refresh blacklists the old refresh token and issues a new one. These controls do not constitute a full security audit; login and refresh are custom endpoints and should be considered separately during hardening.

Evidence: backend/accounts/authentication.py; backend/accounts/views.py; backend/config/settings.py; frontend/src/lib/crm.ts

## 30. Security and data integrity controls

Explain transaction atomicity using a lead update: the business status and its related history should either save together or fail together. Row locking helps concurrent operations coordinate where the action uses it. The API config sets anonymous and authenticated throttle rates, but this is not a guarantee against every abuse scenario. CORS is broad for Vercel preview origins in the current configuration, and process-local throttling and live settings deserve deployment review. Never show .env contents or production credentials in the presentation.

Evidence: backend/config/settings.py; backend/leads/views.py; backend/accounts/offboarding.py

## 31. CSV / XLSX import pipeline

An admin uploads a CSV or XLSX file through a multipart request. The API checks extension and a 10 MB size limit, stores the file and calls the parsing task. The parser normalises Indian phone numbers and validates name, phone, source, model and dates. It skips matching phone numbers already in the CRM and repeated within the same file by default. UploadRow stores normalised data and validation errors; the admin reviews the summary and commits valid rows in a transaction. The server also contains duplicate-resolution actions beyond the current UI defaults.

Evidence: backend/uploads/views.py; backend/uploads/tasks.py; backend/uploads/models.py

## 32. Complaint management workflow

New complaints require a category and a matching subtype, alongside customer and issue details. CE and receptionist users can create and view their own tickets; reception complaints default to walk-in. The complaints department handles updates and notes. Admin can review tickets and complaint analytics. Open, in progress, escalated, resolved and closed are model states; this diagram describes the typical workflow rather than a fully enforced transition graph. The subtype list is an intake taxonomy and must not be represented as evidence of actual vehicle defects.

Evidence: backend/complaints/models.py; backend/complaints/serializers.py; backend/complaints/permissions.py; backend/complaints/test_subtypes.py

## 33. ETBR: define the numbers before comparing them

ETBR counts distinct enquiries within the caller’s authorised and date-filtered cohort. Enquired counts leads. Test Drive Completed counts non-null completion timestamps. Booked includes both BOOKED and RETAILED sales outcomes. Retailed counts only RETAILED. A booked lead can lack a recorded test drive, so do not assume a strictly decreasing funnel across all four values. These are stage counts within an enquiry cohort, not a historical event-timing funnel or measured company performance.

Evidence: backend/leads/metrics.py; backend/analytics/test_etbr.py; frontend/src/components/etbr-tiles.tsx

## 34. Reporting, performance and caching

analytics/cache.py builds a SHA-256 key from endpoint, user identity, role, location and normalised query parameters. This avoids sharing one user’s cached report with another. Only successful responses are cached. CACHE_TTL_SECONDS controls caching; the Render definition sets 50 seconds, while the application default is zero. Cache exceptions produce X-Cache: ERROR and compute the report. The implementation has performance-conscious choices, but no load test or measured speedup is claimed.

Evidence: backend/analytics/cache.py; backend/analytics/views.py; backend/leads/views.py; render.yaml

## 35. Employee offboarding without losing work

CE and PS/SO offboarding is a business workflow rather than a simple user delete. The impact preview includes actionable leads, closed work, follow-ups and relevant complaints. A snapshot version detects stale previews and returns a conflict. Within the transaction, active work is routed to eligible recipients or a reassignment queue; the implementation preserves historical attribution and records lifecycle events. Reminders can be held for admin review. The UI label Permanent Delete corresponds to an application lifecycle action, not physical erasure of every related row.

Evidence: backend/accounts/offboarding.py; backend/accounts/views.py; backend/accounts/models.py

## 36. Deployment topology and configuration

The frontend uses NEXT_PUBLIC_API_URL and the project has Vercel deployment metadata. render.yaml defines the Python API service, build script, Gunicorn with Uvicorn worker and /api/schema/ health check. DATABASE_URL and Supabase credentials are configured externally. The current service sets CELERY_TASK_ALWAYS_EAGER=true and does not define a separate worker or beat service. Therefore imports can run inline and automatic due reminders need independent scheduling. No production system or database was queried for this presentation.

Evidence: render.yaml; backend/build.sh; backend/config/settings.py; frontend/src/lib/crm.ts

## 37. Testing and current verification

The current run passed 102 backend tests in 98.912 seconds with no Django system-check issues. The tests ran against an isolated test database with eager tasks and caching disabled. They test workflow and permission behaviour, including recent intake and ETBR additions. These checks were run for presentation preparation on 11 September 2026 and should not be described as your original internship-week test execution. Frontend static checks confirm type and lint consistency but do not prove that every browser flow or live infrastructure service is working.

Evidence: backend/leads/tests.py; backend/leads/test_intake.py; backend/analytics/test_etbr.py; backend/complaints/test_subtypes.py; backend/accounts/tests.py; Verification.md

## 38. Technical challenges and responses

These challenges are supported by implementation choices, but the code cannot establish which difficulties you personally experienced. Replace one or two rows with real examples: the trigger, what you saw, how you diagnosed it, what you changed and how you verified the result. Avoid claiming you independently solved a team problem unless that is accurate. Useful evidence includes the commit, test case and mentor review associated with the change.

Evidence: backend/leads/views.py; backend/uploads/tasks.py; backend/accounts/offboarding.py; backend/analytics/cache.py

## 39. My internship experience and learning

Suggested first-person wording, use only if accurate: “At the beginning, I focused on the screens. As I understood the workflow, I started asking who owns each enquiry and what action should happen next.” Another option: “R&D helped me turn a general request into specific fields, permissions and validation rules.” Add a real event, the people involved by role and the resulting lesson. The presenter has not supplied personal anecdotes, so this slide intentionally uses prompts rather than invented experiences.

## 40. Project outcomes and remaining work

The defensible outcome is a working implementation represented by code and tests, not a claimed percentage improvement in company sales or employee productivity. Identify the portion you personally delivered. Remaining work includes live acceptance across roles, deployment verification, reminder scheduling and measurement of actual operational outcomes. Other potential extensions include narrower production origins, export and reporting improvements, validated source integrations and accessibility/browser review. Present them as future work, not completed features.

## 41. Demonstration plan

Prepare a fictional customer record and use separate browser profiles for different roles because login cookies are shared between tabs in one profile. Start with configured branch names, active staff, model and source values. After each handoff, refresh the receiving queue and show the same lead identifier. Do not read real customer details aloud. If a live environment is unavailable, use the editable workflow diagrams and narrate the expected action and evidence rather than claiming a live demonstration occurred.

## 42. Thank you

Close by connecting the internship to your learning: understanding dealership operations, translating responsibilities into software rules, and checking those rules with evidence. Thank your actual company mentor, college guide and colleagues by name only after confirming the details. Invite questions about the workflow, architecture, database and the specific modules you contributed to. The following appendix supports a more detailed technical viva.

## 43. API reference for the viva

Resource routes are registered through Django REST Framework routers, while auth and analytics include explicit paths. Endpoint naming retains earlier terminology: so-update handles the dedicated business update route even though CE and PS/SO are separate user roles. Explain request validation, authentication and scope before discussing the result. Status codes include 400 for validation errors, 401 for missing/invalid authentication, 403 for forbidden actions, 404 for objects outside a filtered queryset and 409 for stale offboarding snapshots.

Evidence: backend/config/urls.py; backend/leads/urls.py; backend/accounts/urls.py; backend/uploads/urls.py; backend/analytics/urls.py

## 44. Additional entities and persistence choices

Django migrations evolve the schema. Optional or nullable fields support existing records while newer serializers enforce requirements for new submissions. UserLifecycleEvent protects the target user relation; several author references use PROTECT so historical records retain their identity. Other optional relationships use SET_NULL. Distinguish a historical audit record from a backup: audits do not replace database backup, recovery and retention procedures. Those operational procedures were not verified.

Evidence: backend/uploads/models.py; backend/complaints/models.py; backend/notifications/models.py; backend/accounts/models.py; backend/leads/models.py

## 45. Technical viva: likely questions

Use these as starting points and answer in your own words. When asked about framework choice, connect the choice to forms, APIs, authorisation and relational data rather than generic popularity. When asked about security, explain the exact controls and acknowledge review limits. When asked what you built, state only your verified contribution. When asked about database deployment, distinguish SQLite defaults, PostgreSQL support and the actual provider, which has not been inspected.

Evidence: backend/config/settings.py; backend/leads/views.py; backend/uploads/tasks.py; render.yaml

## 46. References and photo credits

Full URLs and photo licensing details are supplied in Sources_and_Customisation.md and embedded in the notes. The Wikimedia photograph is licensed CC BY-SA 3.0: credit Ranjithsiji, link the source and licence, and retain the licence for any adapted version. It is placed unmodified in this presentation. The Flickr photograph retains its photographer’s copyright; public availability is not an open licence. Seek the owner’s permission or replace it with a personal/licensed image before public redistribution. Neither photograph is a current office-interior record.

Evidence: https://www.nippon-toyota.com/about-us.html; https://www.nippon-toyota.com/cms/about-us/dealer-principal-v1.txt; https://www.nippon-toyota.com/cms/about-us/dealer-mission-v1.txt; https://nippon-toyota.com/contact-co01b.html; https://www.linkedin.com/company/nippon-toyota-pvt-ltd; https://www.nippon-toyota.com/used-cars.html; https://commons.wikimedia.org/wiki/File:Kalamassery_Toyota_Office.JPG; https://www.flickr.com/photos/sreejithmsivadasan/5974734010
