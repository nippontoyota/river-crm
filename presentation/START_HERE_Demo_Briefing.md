# Incheon Mobility CRM — meeting and demo briefing

Revised visual edition: 30 slides. Prepared 9 September 2026. Read this before presenting. The slide deck reflects the current repository, with suggested operating practices identified as suggestions. It is not a confirmation that the live deployment has passed acceptance testing.

## Open these files

- **Incheon_Mobility_Operations_Demo.pptx** — 30 editable widescreen slides with embedded presenter notes. Use PowerPoint Presenter View.
- **Incheon_Mobility_Operations_Demo.pdf** — slide-by-slide PDF for sharing or as a fallback.
- **Presenter_Notes.pdf** — printable rehearsal guide, detailed notes grouped by slide.
- **Presenter_Notes.md** — searchable text version of the notes.
- **START_HERE_Demo_Briefing.pdf** — this briefing in printable form.
- **Verification_and_Evidence.md** — review scope, test evidence and implementation watchpoints.

All names in scenarios and numbers in example charts are illustrative. No production records, passwords or real customer details appear in these materials. Creating this presentation did not change application code or customer records.

## Present this route if you have 35–45 minutes

Use slides **1–5** for the operating model and permissions. Show **6–10** for Admin controls, intake and allocation. Use **11–15** for the CRE / PS workflow, then **16–21** for the five requested scenarios. Cover **22–24** for successful sales, walk-ins and complaint handling. Finish with **25–30** for manager review, daily operations, exceptions, staff continuity and pilot decisions. The main deck has exactly 30 slides; the deeper explanations remain in speaker notes.

For a 20-minute meeting, use 1, 2, 4, 5, 10, 12, 16–21, 26 and 30. Demonstrate qualification and complaint resolution live, and narrate the other scenarios from the diagrams.

Opening words:

> Today I will follow a customer enquiry through the people who handle it: Admin, CRE and PS/SO. Then I will show how the Sales Manager reviews the branch and how the complaints team handles an issue. I want you to see the actual ownership and follow-up steps, and help confirm the operating rules your team will use.

Closing words:

> We have seen who receives the enquiry, who records each decision, and how management reviews the result. Let us confirm the allocation cadence, the owner of the next call after handoff, the retry policy, and the complaint escalation rules. We can record any product changes needed for the pilot against those decisions.

## Prepare before the meeting

1. Open the deck in presentation mode and test screen sharing. Use the PDF if the presentation application changes fonts.
2. Sign in once as Admin, CRE, PS/SO, Sales Manager and complaints department. Include Receptionist if you plan the walk-in example.
3. Use separate browser profiles for simultaneous roles. Tabs in the same profile share login cookies; signing in as another role can replace the first session.
4. Check that the chosen CRE and PS are active, the PS has the intended location, and the Sales Manager has exactly the intended branch. Use existing configured branch names rather than invented variants.
5. Check Admin Lists has the source, model and color used in the demo. Empty lists can prevent a qualification save.
6. Prepare distinct fictional customer records in a designated demo environment. Note each lead ID. Use approved test phone numbers; do not dial invented numbers. Avoid taking real customer records through loss or offboarding for demonstration.
7. Use today or tomorrow for follow-up dates. The third displayed calendar day can conflict with the server’s rolling 72-hour limit.
8. Keep the same enquiry-date filter and branch when comparing queues and reports. Set missing branch and enquiry date on walk-in captures before showing SM analytics.
9. For a scoped allocation demo, use **filtered bucket assignment**. The current global **Auto assign** button does not pass the active filters or page selection to its operation.
10. Rehearse one complete qualification, one PS follow-up and one complaint resolution. Refresh each receiving queue before declaring the handoff complete.
11. Have the PDF open locally as a fallback. Do not rely on a notification popup to demonstrate receipt; show the refreshed queue.
12. If demonstrating staff disable/reassignment, prepare a disposable CRE or PS account with a few test leads. A read-only impact preview is enough to explain the workflow if time is short.

## Demo records to prepare

| Reference | Starting condition | Intended result |
|---|---|---|
| DEMO Asha | Fresh, assigned to demo CRE | CRE Qualified and matching PS assigned |
| DEMO Binu | Fresh, assigned to demo CRE | CRE Lost, Plan Dropped, explanatory remark |
| DEMO Charu | Qualified, assigned to demo PS | Need Test Drive, Pending and open follow-up |
| DEMO Deepak | Qualified, assigned to demo PS | Lost to Competition with PS remarks |
| DEMO Farah complaint | Customer issue logged by demo CRE | In Progress, then Resolved with resolution notes |
| DEMO Retail (optional) | Qualified, assigned to demo PS | Booking Done, then Retail Done |

These are preparation instructions only. No demo accounts or records were created by the presentation-generation task.

## The five requested scenario scripts

### 1. CRE → Qualified — slide 17

**Say:** “The customer has confirmed interest, so CRE records the buying context and chooses the person who will handle sales.”

**Do:** Admin Assignment → assign Asha to CRE. Switch to CRE → My queue → open the same record → Qualified. Complete model, color, preferred branch, PS/SO, buying plan, finance and qualification notes. Save Qualify Lead.

**Verify:** CRE sees Qualified. Assigned PS sees the lead in Fresh leads after refresh. Open it to show CRE qualification and the same lead ID. CRE ownership remains attached.

**If blocked:** Check required fields, active PS and branch/location match. An already-qualified lead cannot be qualified again through that CRE action. Use the prepared fresh record.

### 2. CRE → Lost — slide 18

**Say:** “The customer has dropped the plan. We record why so the enquiry does not remain in an active queue without a purpose.”

**Do:** CRE opens Binu → Lost → Plan Dropped → remarks → Mark as Lost.

**Verify:** Lost / Won-lost view contains the record; history includes the reason and CRE name. The outcome update resolves earlier open follow-ups and does not create another one.

**If asked about recovery:** The server supports Admin reopening to Qualified, but the current frontend does not expose a dedicated Reopen control. Discuss it as an Admin recovery capability requiring an interface workflow, not a button you can demonstrate today.

### 3. CRE Qualified → PS under follow-up — slide 19

**Say:** “The CRE has qualified the customer; the PS now needs to arrange the next sales discussion or test drive.”

**Do:** PS opens Charu → read CRE notes → Connected → Need Test Drive → choose today or tomorrow → detailed remark → Save follow-up.

**Verify:** Pending status, a new history entry and an open follow-up. If you chose tomorrow, use All leads or the detail history; do not expect it in Today’s follow-ups before tomorrow. A test-drive request is not a completed test drive.

### 4. CRE Qualified → PS Lost — slide 20

**Say:** “A customer can qualify and later choose a different product. We retain both the CRE context and the final sales explanation.”

**Do:** PS opens Deepak → Connected → Lost to Competition → specific remark → save.

**Verify:** PS Lost view contains the record. History retains CRE qualification and the PS loss outcome. SM can find it within the configured branch and date scope.

### 5. CRE → Complaint — slide 21

**Say:** “The CRE records the customer’s issue; the complaints team works the ticket and documents the resolution.”

**Do:** CRE Complaints → create ticket for Farah with valid phone, configured branch, category, priority, source, subject and description. Note the CMP ticket number. Switch to complaints department → open that ticket → In Progress and remarks → resolve with resolution notes.

**Verify:** Ticket status and notes are visible. The resolving user becomes the assignee on update. CRE can track their logged ticket; Admin can read the shared queue and analytics. Admin cannot resolve the ticket. PS, SM and Receptionist do not have complaint access.

**Avoid:** Saying this changes the sales lead status or automatically links the complaint to a lead. The normal complaint create form does neither.

## Questions the operations manager may ask

**Does a manager approve every lead or sale?** No. The current SM role reviews its branch. Admin allocates, CRE qualifies and PS records sales outcomes. Any approval policy needs separate agreement and implementation.

**Can CRE still see a qualified customer?** Yes. CRE ownership remains. Current update rules allow continued permitted updates after handoff. Agree that PS owns the next sales contact to avoid duplicate calling.

**Can PS rewrite the CRE qualification?** No, the dedicated PS update rejects qualification edits. PS can update supported customer details and its sales outcomes.

**Is allocation fully workload-balanced?** Filtered distribution shares the new batch in turns. Auto assign sorts CREs by total assigned load first, then cycles. Offboarding/reassignment uses the selected eligible users’ active workloads and checks PS branch matching.

**Can I auto assign just the rows I filtered?** Use the filtered bucket action for that. The current Auto assign screen action sends no filter or record-ID restriction.

**Do five unanswered calls automatically close a lead?** No. F1–F5 is a visual indicator. A user selects the loss outcome; the company needs a retry and closure policy.

**Can a callback be scheduled for an exact customer-promised time?** The normal CRE/PS UI currently selects a date and saves it at 23:59 IST. Describe it as a day-based follow-up queue. Admin has time-oriented review controls; exact-time frontline scheduling would need a change.

**What if the customer plans to buy in two months?** Store the buying timeline and use the current short follow-up window for the next contact. Long-range nurture scheduling is not available through the three-day follow-up limit.

**Are reminders live?** Assignment and due-reminder logic exists. Verify deployed scheduling and user-facing delivery separately. The main shell has no visible notification bell; demonstrate the queue as the evidence of assignment.

**Are duplicate leads impossible?** Import checks and skips duplicate phones. Manual creation does not enforce phone uniqueness across the CRM. Search before creating a repeated manual enquiry.

**Are advertisements integrated automatically?** Sources classify enquiries. The verified intake paths are file import and manual/walk-in capture. Do not promise live Meta, website, CarWale or WhatsApp integrations without separate evidence.

**Does Booked create an order, invoice or inventory reservation?** No. Staff record the CRM sales outcome after the company’s sales process supports it. Payment, invoicing and inventory integration are outside the verified scope.

**What does the funnel represent?** Current lead statuses and sales outcomes in the chosen cohort. It is not an immutable history of everyone who ever qualified or booked. Do not use its stage ratios for incentives without agreeing definitions.

**Is Escalated an automatic complaint routing rule?** No. It is an available status. Agree the escalation contact, communication route and response target operationally.

**Who owns a complaint?** The complaints queue is shared. A status/priority/resolution update assigns the updater. Adding a note alone does not claim it. Agree a pickup and handover convention.

**What happens when someone leaves?** For CRE and PS, Admin previews the impact, routes actionable leads by status, keeps closed history, and reviews held reminders. Unmatched PS branch work stays in Needs reassignment.

**Does permanent delete remove historical work?** It removes credentials and scrubs contact/login fields while preserving historical name and work attribution. A deleted account cannot be re-enabled.

## Presenter-only watchpoints

These are observations from repository review, not requests to discuss source code in the meeting.

- **Different intake paths:** Receptionist capture does not submit branch or enquiry date. Correct those before showing branch/date analytics. Imported Walk-in-source rows are created through the import path and do not automatically run the receptionist Qualified shortcut.
- **Shared next-action state:** A logged outcome resolves all open follow-ups for the lead, including a follow-up created by the other role. Coordinate CRE and PS activity after handoff.
- **Two status fields:** Main PS updates keep status and sales outcome aligned for common choices. Some Admin call-update paths change status without updating sales outcome. Check the final record before comparing reports.
- **PS contact flag:** The PS screen requires Connected/Not Connected but its save payload currently omits `call_status`. Demonstrate the selected outcome and remarks; do not promise persistent connected-call reporting from that field.
- **CRE profession:** The qualification screen displays a profession choice, but the qualification save does not submit it. Intake forms can store profession. Do not present the qualification choice as a verified saved field.
- **Dashboard context:** Qualified is current status, Contacted means non-Fresh, and loss breakdowns can count historical call outcomes on currently lost records. Admin/personal/manager measures also have differences; keep the definition and filters visible.
- **Complaint timestamps:** Resolved time is set on first resolve/close and is not cleared when returning to an open status. Average resolution time is not a verified reopened-ticket SLA measure.
- **Notification delivery:** Backend reminders are scheduled at 15-minute intervals in application configuration, but the checked deployment file does not establish a running scheduler. A configured task is not proof of live delivery.
- **Flags / reopen:** Manager flagged filters and an Admin reopen operation exist; a complete frontend flagging/reopen workflow was not found. No automatic five-attempt escalation should be claimed.
- **Scope of protection:** Dedicated update/assignment/offboarding actions contain validation. A full security audit of generic edit endpoints was not part of this presentation task. Do not claim that all possible status changes are universally forced through one audited state machine.
- **Permission visibility:** The matrix describes normal supported workspaces and dedicated workflow paths. It does not certify every possible API path.

## Capture these decisions before finishing

| Topic | Decision to record | Person accountable |
|---|---|---|
| Allocation | Who checks incoming leads, and how often? | Admin / operations |
| Handoff | Who makes the next call after CRE qualification? | CRE and sales leadership |
| Retries | How many attempts before manual loss, and what evidence? | Sales Manager |
| Follow-ups | Is a day-based next contact enough, or are exact times required? | Operations |
| Branch data | Who corrects missing branch/enquiry date on intake? | Admin / front desk |
| Complaints | Priority response targets, escalation contacts, closure evidence | Complaints lead |
| Reporting | Which metric definitions are accepted for pilot review? | Operations manager |
| Product gaps | What changes are required before wider rollout? | Product owner |
