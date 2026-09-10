# Incheon Mobility CRM — 30-slide presenter notes
Revised visual edition. Details remain in the notes; the presentation uses short labels and infographics.

## Slide 01 — From enquiry to outcome
30-slide visual operations walkthrough

Opening talk track: Today I will follow a customer enquiry through the people who handle it. We will see how Admin allocates work, how CRE records a customer decision, how PS/SO continues the sales conversation, and how the Sales Manager reviews the branch. We will also follow a complaint and a staff handover. The purpose is to agree how your team will operate the product. The descriptions reflect the current repository, rather than every item in the original requirements document. Live deployment behavior should be checked before the meeting. Use the accompanying demo briefing for that rehearsal.

Evidence: README.md; frontend/src/components/app-shell.tsx

## Slide 02 — One enquiry. A visible next owner.
Admin → CRE → PS/SO, with branch oversight from the Sales Manager.

Explain the arrows as a sequence of responsibility, not an approval hierarchy. A lead does not wait for Sales Manager approval before a PS can contact the customer, book or retail. The manager reviews the branch data and gives operational direction. Admin retains allocation and user controls. CRE ownership remains attached after the PS handoff, so the team retains both the original relationship owner and the sales owner. The manager sees records that match the branch on their account. The complaints team works through a separate ticket queue.

Start at intake, then show the three CRE decisions: qualified, pending and lost. Qualified requires the branch and sales owner in the main CRE form. Pending records the reason and next follow-up date. Lost records why the enquiry ended. At the PS stage, the customer can continue in follow-up, proceed to booking and retail, or be lost. A complaint is a separate ticket; it does not automatically close or convert the sales lead. The diagram shows the intended operating route supported by the normal screens. Detailed status handling is covered later.

Evidence: backend/leads/views.py:LeadViewSet; backend/analytics/views.py:manager_base_queryset; backend/leads/views.py; frontend/src/features/leads/sales-workspace.tsx; backend/complaints/views.py

## Slide 03 — Six roles, clear responsibilities
Each workspace follows the person’s job.

CRE means Customer Relationship Executive. PS/SO is the shared sales role label used in this build; use the company’s preferred expansion of PS during the meeting. SM means Sales Manager. The product gives each role a different navigation menu. A senior job title does not automatically grant Admin or complaint-resolution rights. For example, a Sales Manager cannot allocate leads in the current application, and an Admin can read complaints but cannot resolve them. Receptionist is an additional intake role and should be shown after the main CRE sales path.

Show the Assignment, All leads, Users, Lists and Analytics menus. Explain that the unassigned pool is a work queue that Admin must review, not proof that the team has already contacted the customer. Ordinary allocation targets active CRE users. Admin can inspect any non-deleted lead and see ownership and history. User offboarding is a distinct action with an impact preview. Complaints remain read-only for Admin. Recommended daily practice is to clear unassigned work at agreed intervals and check the separate Needs reassignment view before finishing the day.

Explain what good CRE work looks like in operational terms. A useful qualification note says which model and color the customer wants, how soon they plan to buy, how they expect to pay and what the PS should discuss next. The main form requires the model, color, branch, PS, buying plan, finance and notes. Profession is displayed but is not part of that required qualification set. CRE can still see and update owned records after handoff under the current rules. Agree internally which person should make the next customer call so both roles do not chase the customer at the same time.

PS/SO has a different outcome menu from CRE. Connected outcomes include test drive, showroom visit, booking, retail, callback, finance or discount issues, and several loss reasons. Not Connected includes RNR, switched off, line busy, call forwarding, invalid number and manual No Response loss. PS must record remarks in the screen. CRE qualification remains visible and cannot be edited through the PS workflow. Fresh for PS means a currently qualified lead that the assigned PS has not yet logged a call against; it does not mean the same thing as CRE Fresh.

The manager’s configured location determines the branch scope. A blank location gives no branch data. The manager cannot change lead status, assign, delete or reopen leads through this role. Coaching and reassignment requests take place through the company’s normal communication process; there is no implemented manager approval inbox. The operational review can identify a stale Fresh lead or an overdue follow-up and then ask the named CRE or PS to act. Flagged filters exist, but do not promise a complete escalation button-to-notification flow without a live check.

Evidence: frontend/src/components/app-shell.tsx; backend/accounts/models.py; frontend/src/features/leads/lead-desk.tsx; frontend/src/features/team/team-page.tsx; frontend/src/features/leads/sales-workspace.tsx:save; backend/leads/views.py:so_update; frontend/src/features/leads/sales-workspace.tsx; backend/leads/views.py:my_dashboard; backend/analytics/views.py:manager_base_queryset; backend/leads/views.py:manager_leads; backend/analytics/tests.py

## Slide 04 — Access controls: leads & administration
“Own” means assigned records; “branch” means the manager’s configured branch.

This table describes normal supported workspaces and dedicated workflow actions, rather than a completed security audit of every generic endpoint. Receptionist sees their capture dashboard, not a general branch lead queue. CRE qualification and PS selection occur in the qualification flow; CRE also retains update access after handoff subject to transition rules. PS can edit allowed customer details, but cannot rewrite CRE qualification. Staff use Admin-maintained options. The manager’s lead workspace is read-only. Any change to the permission model should be agreed as a separate product decision.

Evidence: backend/leads/views.py:get_permissions,get_queryset,so_update; backend/accounts/permissions.py

## Slide 05 — Access controls: complaints & reporting
The complaint logger, resolver and management viewer have different rights.

Walk the manager through the complaint row first: CRE logs a ticket and can track only the tickets they logged; the complaints department sees the shared queue and can update it; Admin sees the queue and analytics but does not resolve tickets. PS, SM and Receptionist have no complaint access in this version. These restrictions are covered by existing complaint tests. The complaints dashboard can therefore support company-level resolution work, while the Sales Manager’s sales reporting remains scoped to their branch.

Evidence: backend/complaints/permissions.py; backend/complaints/tests.py; backend/analytics/views.py

## Slide 06 — Admin controls the operating setup
Set up the team, allocate work, and handle exceptions.

Show the Assignment, All leads, Users, Lists and Analytics menus. Explain that the unassigned pool is a work queue that Admin must review, not proof that the team has already contacted the customer. Ordinary allocation targets active CRE users. Admin can inspect any non-deleted lead and see ownership and history. User offboarding is a distinct action with an impact preview. Complaints remain read-only for Admin. Recommended daily practice is to clear unassigned work at agreed intervals and check the separate Needs reassignment view before finishing the day.

Demonstrate adding or reviewing an existing branch, source, model and color. Matching branch names matter because PS selection and Sales Manager visibility depend on location values. Sources reject values outside the configured list for new records. The source list preserves Walk-in. Models and colors constrain relevant forms when configured. Several reason lists, finance choices and buying timelines remain fixed in the current screens; Admin Lists is not a complete business-rule builder. Removing a list value does not rewrite historical customer records.

Evidence: frontend/src/features/leads/lead-desk.tsx; frontend/src/features/team/team-page.tsx; frontend/src/features/admin/lists-page.tsx; backend/leads/serializers.py

## Slide 07 — Three entry routes into the CRM
Sources describe origin; imports and forms bring the enquiries in.

Use the bulk route for downloaded advertising or partner lead lists. Admin manual entry can place an ordinary enquiry in the allocation pool. CRE’s visible Add lead form is designed for a directly qualified lead with branch and PS selected; the underlying non-walk-in CRE creation path also supports CRE ownership. Receptionist capture forces Walk-in source and Qualified status and can attach a PS. Walk-in capture bypasses normal CRE qualification. Do not describe configured sources as live integrations: this repository supports capture and upload, not a verified live advertising-platform feed.

Show the upload summary and distinguish the parsed row count from the imported count. The parser strips formatting from phones, removes a +91 or leading zero when appropriate, and expects a ten-digit result. It checks the configured source and, when configured, the model. It rejects a future enquiry date. Valid rows can be imported while invalid and duplicate rows are skipped. A failed upload should be corrected and retried. Missing or unrecognized date formats can fall back to today, so validate the source file dates rather than assuming the imported cohort is correct.

Show the receptionist Capture Lead page and explain that this is a different intake path. The current form captures basic customer details, profession, model, variant, buying plan and PS selection. It does not capture branch or enquiry date in its submitted payload. Consequently, the lead can reach the PS queue but be absent from branch-scoped or enquiry-date-filtered reporting until an authorized user fills those fields. The receptionist dashboard counts their own captures made today. Keep the branch/date completion step explicit; do not claim automatic branch inference from the selected PS.

Use text-formatted phone columns to avoid spreadsheet scientific notation and lost leading digits. The parser recognizes Name or Customer Name, Phone or Mobile, model or vehicle interest or model / vehicle interest, and date or enquiry date. It reads the active worksheet of XLSX files. Date parsing accepts day-month-year, ISO date and day/month/year. Native spreadsheet date serialization can differ, so confirm the parsed date in a sample before committing a large batch. The import payload does not populate the branch field; CRE qualification normally supplies the preferred branch. Imported walk-in source rows do not automatically execute the receptionist shortcut.

Evidence: backend/leads/views.py:perform_create; frontend/src/features/leads/sales-workspace.tsx:saveLead; frontend/src/app/(receptionist)/capture/page.tsx; backend/uploads/views.py; backend/uploads/tasks.py; backend/uploads/serializers.py; frontend/src/app/(receptionist)/capture/page.tsx; backend/analytics/views.py:ReceptionistAnalyticsView; backend/uploads/tasks.py:read_rows,parse_date,parse_upload_batch; backend/uploads/views.py:commit

## Slide 08 — Check the data before importing
Review the upload summary, then confirm import.

Show the upload summary and distinguish the parsed row count from the imported count. The parser strips formatting from phones, removes a +91 or leading zero when appropriate, and expects a ten-digit result. It checks the configured source and, when configured, the model. It rejects a future enquiry date. Valid rows can be imported while invalid and duplicate rows are skipped. A failed upload should be corrected and retried. Missing or unrecognized date formats can fall back to today, so validate the source file dates rather than assuming the imported cohort is correct.

The current UI emphasizes automatic duplicate removal. Do not demonstrate overwrite/import-as-new options from the original PRD as though they are exposed in the normal upload screen. The server retains duplicate-resolution capabilities, but that is different from the user-facing workflow. Duplicate detection is not a universal uniqueness guarantee: manual entry does not enforce unique phone numbers across all lead records. For operations, search by phone before manually creating a second enquiry, and agree how repeat enquiries should be treated.

Use text-formatted phone columns to avoid spreadsheet scientific notation and lost leading digits. The parser recognizes Name or Customer Name, Phone or Mobile, model or vehicle interest or model / vehicle interest, and date or enquiry date. It reads the active worksheet of XLSX files. Date parsing accepts day-month-year, ISO date and day/month/year. Native spreadsheet date serialization can differ, so confirm the parsed date in a sample before committing a large batch. The import payload does not populate the branch field; CRE qualification normally supplies the preferred branch. Imported walk-in source rows do not automatically execute the receptionist shortcut.

Evidence: backend/uploads/views.py; backend/uploads/tasks.py; backend/uploads/serializers.py; backend/uploads/tasks.py:parse_upload_batch; backend/uploads/views.py:commit; frontend/src/features/leads/lead-desk.tsx; backend/uploads/tasks.py:read_rows,parse_date,parse_upload_batch; backend/uploads/views.py:commit

## Slide 09 — Choose how the batch is shared
Individual assignment, filtered buckets, or global Auto assign.

Use filtered bucket distribution in the live demo if you need scope control. The current Auto assign button calls the operation without lead IDs or the active screen filters. It therefore processes the eligible unowned pool, not just the count shown on a page or a filtered view. The eligible ordinary allocation pool excludes records already owned by CRE or PS and records waiting for offboarding reassignment. Individual assignment rejects a lead that already has a CRE. The separate offboarding recovery queue should be cleared through its dedicated workflow.

Use eleven fresh enquiries and three selected CREs as an easy explanation. The system takes eligible leads in creation order and cycles through the selected CREs: A, B, C, A, B, C, and so on. A and B receive four, C receives three. This equalizes the new batch, not necessarily everyone’s existing workload. Auto assign first sorts active CRE users by their total assigned lead count, then cycles through them; it does not repeatedly recalculate the least-loaded employee for every new lead. Offboarding redistribution uses a different active-load calculation.

Evidence: frontend/src/features/leads/lead-desk.tsx:autoAssign,assignBucket; backend/leads/views.py; backend/leads/views.py:bulk_distribute,auto_assign

## Slide 10 — Branch determines sales ownership and visibility
A responsibility map, not an extra approval chain.

This is an operational responsibility diagram, not a stored employee-manager tree. There is no separate multi-level regional-manager hierarchy in the current roles. Admin can distribute fresh enquiries across selected CRE users. During the normal CRE qualification form, selecting preferred branch populates both customer location and lead branch, and filters the PS list. The Sales Manager sees the lead through the branch field. Different CRE users may contribute to one branch’s results. Branch corrections therefore change the manager’s reporting scope and should be deliberate.

Unlike normal round-robin allocation, offboarding distribution selects the lowest active workload from the chosen eligible replacements and updates that load as each lead moves. For PS work it also requires a non-blank lead branch matching the replacement location. No eligible branch match leaves the lead pooled with a reassignment flag. Ordinary fresh allocation excludes these records, which prevents them being treated as completely new enquiries. Admin can later select pooled records and replacements in All leads → Needs reassignment. Follow-up ownership can move, but its reminder remains held until review.

Evidence: backend/leads/views.py:bulk_distribute,so_update; backend/analytics/views.py:manager_base_queryset; backend/accounts/offboarding.py:offboard_user; backend/leads/views.py:bulk_reassign

## Slide 11 — CRE chooses the next path
Record what the customer said, then complete the matching fields.

A qualified customer does not mean a booked vehicle or completed sale. It means the CRE has collected enough information for PS to continue the sales conversation. Pending covers contact retries and customer timing. Lost should have a specific explanation, such as low budget, wrong number or lost to competition, rather than a generic closing note. The current form requires the applicable reason and remarks. Avoid promising that status transitions are entirely locked after handoff: CRE retains ownership and permitted update access, which requires an agreed team operating rule.

Use the full choices displayed in the live form if the manager asks how their dispositions map into the product. Additional CRE loss choices include Just enquired, Service, Insurance, Internal, Used car, No Response, Mock Call, DSA Enq and BH Registration. Pending reasons also include Temporary out of Service and Incoming call facility not available. Some of these choices may need company-specific wording or a policy discussion. They are currently screen-defined choices rather than editable Admin Lists values. Remarks should make the disposition understandable without relying on an acronym.

Evidence: frontend/src/features/leads/sales-workspace.tsx:save; backend/leads/serializers.py; frontend/src/features/leads/sales-workspace.tsx:lostReasons,pendingReasons

## Slide 12 — A complete qualification makes the handoff useful
Choose an active PS/SO from the customer’s preferred branch.

Open one lead record and point to these three groups. The history preserves who made the update and what the customer said. Do not claim that the application places or records telephone calls: staff make the call through their usual process and then record the outcome here. The call count measures recorded call-log entries; it is not a verified telecom call count. Category is a staff-entered prioritization choice, not automated lead scoring. Lead detail exposes recent audit entries and complete serialized call and follow-up history.

For the live demo, complete model, variant, buying plan, finance and remarks, then select a configured preferred branch and a PS from that branch. Saving updates the lead to Qualified and stores the PS assignment. The server checks that the PS is active and the selected location matches the PS location. A record with an already-qualified status cannot simply be qualified again through the CRE form. The lead remains visible to the assigned CRE after handoff. Assignment notifications are stored, but use the refreshed PS queue as the reliable visible proof during the meeting.

Evidence: backend/leads/models.py; backend/leads/serializers.py:LeadDetailSerializer; frontend/src/features/leads/sales-workspace.tsx:save; backend/leads/views.py:so_update

## Slide 13 — PS/SO records the sales conversation
Choose Connected / Not Connected, then an outcome and remarks.

The outcome describes the customer’s situation and the status tells the team where the work stands. A test-drive request is a next action, not proof that a test drive happened. Booking Done stores the booked sales outcome and a status that some shared screens label Walk-in. Retail Done stores Retailed and Won. The current system does not create a vehicle invoice or reserve inventory from these choices. Staff should record booking or retail only after the company’s underlying sales process supports that statement.

Explain that the F1 to F5 display is a visual call-progress indicator. It does not automatically declare the lead Lost after five calls, and it does not enforce a fixed maximum number of contact attempts. Operations should agree how many attempts are appropriate and who approves closing an unreachable customer. PS No Response is available as a deliberate Lost choice under Not Connected. CRE uses its own pending reasons, and RNR or switched-off CRE updates can appear under the broader Pending status.

Evidence: frontend/src/features/leads/sales-workspace.tsx:soConnectedOutcomes,save; backend/leads/serializers.py; frontend/src/features/leads/sales-workspace.tsx:autoNextDayFollowUpOutcomes,progressState; backend/leads/tests.py:test_ps_can_manually_mark_not_connected_as_no_response_lost

## Slide 14 — Follow-up is a repeating work cycle
A new outcome resolves the previous open follow-up and records the next plan.

The normal CRE and PS screens use a date picker and save the selected day at 23:59 IST. They allow future follow-ups within the next three days, while the server enforces a rolling seventy-two-hour limit. This creates a potential edge on the last selectable calendar day; use today or tomorrow for rehearsal. Do not promise exact customer callback-time scheduling through these date-only screens. Admin has time-oriented review controls. Each outcome update resolves all open follow-ups on the lead, so a CRE update can affect a PS follow-up and vice versa. Agree one next-action owner after handoff.

Explain that the F1 to F5 display is a visual call-progress indicator. It does not automatically declare the lead Lost after five calls, and it does not enforce a fixed maximum number of contact attempts. Operations should agree how many attempts are appropriate and who approves closing an unreachable customer. PS No Response is available as a deliberate Lost choice under Not Connected. CRE uses its own pending reasons, and RNR or switched-off CRE updates can appear under the broader Pending status.

Evidence: frontend/src/features/leads/sales-workspace.tsx:followUpIso; backend/leads/serializers.py:SOLeadUpdateSerializer; backend/leads/views.py:so_update; frontend/src/features/leads/sales-workspace.tsx:autoNextDayFollowUpOutcomes,progressState; backend/leads/tests.py:test_ps_can_manually_mark_not_connected_as_no_response_lost

## Slide 15 — Translate screen labels into sales events
Lead status and sales outcome are separate fields.

Clarify the two fields before presenting metrics. Lead status and sales outcome are separate values. Shared lead tables may use Walk-in where the PS view uses Booked, and Won where the PS view uses Retailed. A walk-in as a source is also different from a booking status. Current outcome updates can move an active booked lead back into follow-up and reset the sales outcome to Pending. These are current-state records, so do not describe the dashboard as an immutable historical sales ledger. Review the final customer status after the demo save.

Use a sixth fictional customer or a rehearsed existing demo record. PS chooses Booking Done and a future follow-up, then the record appears under Booked. Open it again, choose Connected and Retail Done, and save final remarks. Show Retailed in the PS view and Won in shared status labels where applicable. The new retail update resolves the open booking follow-up. The application tracks the sales outcome entered by staff; it does not validate payment, finance disbursal, stock allocation, invoicing or delivery documentation. Those actions remain with the company’s existing systems and process.

Evidence: backend/leads/models.py; frontend/src/lib/crm.ts:statusNames; frontend/src/features/leads/sales-workspace.tsx:save; backend/leads/tests.py:test_full_admin_to_cre_to_ps_lead_journey_with_five_followups

## Slide 16 — Five scenarios to demonstrate
For each: starting record → staff action → saved result.

This slide matches the list in the screenshot. Use fictional demo customer names and keep a small written list of their record IDs. Demonstrate the same structure each time: starting owner and status, customer statement, staff action, record after saving, and next owner. The slide notes for the next five scenarios provide the talk track and exact validation points. No customer records were created as part of building this presentation; prepare them in your designated demo environment before the session.

Evidence: 

## Slide 17 — 01 / CRE qualifies the enquiry
DEMO ASHA: “I have decided on a model and want to discuss buying.”

Talk track: Asha has confirmed that she is interested in buying. Our CRE captures the specific model, color, buying plan, finance option and useful remarks. Show that the PS list depends on preferred branch. Save with Qualify Lead. Verify the lead appears as Qualified for CRE and appears in the assigned PS Fresh leads queue after switching to that role and refreshing. Open the same lead ID and point out the CRE qualification details. Expected ownership: CRE remains attached; PS is now the next operational contact. If no PS appears, check active status and branch spelling with Admin.

Evidence: frontend/src/features/leads/sales-workspace.tsx; backend/leads/tests.py:test_cre_must_choose_matching_ps_for_qualified_lead

## Slide 18 — 02 / CRE closes a lost enquiry
DEMO BINU: “We have dropped our purchase plan.”

Talk track: Binu confirms that there is no longer an active purchase plan. The CRE should close the enquiry with a reason that management can understand later. Select Lost, choose Plan Dropped and add a remark such as: Customer cancelled the purchase after discussing the household budget; no next purchase date agreed. Save and show the Lost record and call history. Do not add a follow-up date to this loss update. The existing open follow-up is resolved when the outcome is logged. Reopening is an Admin capability in the server, but the current frontend has no dedicated Reopen action; do not promise an on-screen reopening demo.

Evidence: frontend/src/features/leads/sales-workspace.tsx:lostReasons,save; backend/leads/views.py:reopen

## Slide 19 — 03 / PS continues the follow-up
DEMO CHARU: “I need a test drive before deciding.”

Talk track: Charu is qualified, but needs a test drive before committing. As PS, open the lead and show the CRE notes. Select Connected, then Need Test Drive. Choose tomorrow and write a remark explaining the model and the proposed visit. Save, reopen the record and show the new history entry and open follow-up. Tomorrow’s item is not necessarily in Today’s follow-ups yet; show All leads or the record’s follow-up history. If the demo needs the due-today queue, select today before 23:59 IST. The manager’s test-drive signal reflects a request or qualification indicator, not a verified completed test drive.

Evidence: frontend/src/features/leads/sales-workspace.tsx; backend/leads/tests.py:test_assigned_ps_can_schedule_next_day_follow_up

## Slide 20 — 04 / PS records a sales loss
DEMO DEEPAK: “I have chosen a competing product.”

Talk track: Qualification is an early buying signal, not a guarantee of conversion. Deepak has now chosen a competitor. Select Connected and Lost to Competition, add the specific reason and save. Show Lost in PS All leads, the earlier CRE qualification and the new PS call history. In the manager’s branch view, search the same lead and inspect the trail. Loss reasons also include Finance Rejected, Dropped and Lost to co-dealer. Do not treat the current Lost reasons chart as a deduplicated final-cause count; its implementation groups call outcomes associated with currently lost leads.

Evidence: frontend/src/features/leads/sales-workspace.tsx:soConnectedOutcomes; backend/analytics/views.py:manager_payload

## Slide 21 — 05 / CRE hands a complaint to the resolution team
DEMO FARAH: “My delivery issue needs attention.”

Talk track: Farah needs help with an existing issue. CRE opens Complaints and enters customer name, valid phone, configured branch, category, priority, source, subject and description. Save and note the CMP ticket number. Switch to a complaints-department account, open that ticket, update to In Progress with a note, then resolve with a clear description of the action taken. Return to CRE to show the ticket status, then use Admin for reporting if time permits. The normal complaint form does not automatically link to an existing sales lead or change its status. Use the ticket number as the handoff reference.

This is not the same allocation mechanism as lead distribution. There is no normal manual assignment-to-colleague control exposed in the complaint update serializer. The updater becomes the assigned user, so two resolution staff members need a clear working arrangement. CRE sees only tickets they logged; Admin and the complaints department see the shared queue. The current complaint update does not use the same stale-edit protection as the dedicated lead update flow. The notes provide a readable history of the discussion, but there is no complete old/new audit event for every complaint status or priority change.

Categories are Service Delay, Product Defect, Delivery Issue, Billing / Finance, After-Sales, Staff Behaviour, Warranty and Other. Complaint sources are Phone, Email, Walk-in, Social Media and Other. These complaint classifications are distinct from the Admin-configured sales lead sources. Ask CRE to record facts, the customer impact and what response the customer expects. Avoid vague subjects such as Complaint or Urgent. The normal create form does not set an assignee or attach a sales lead automatically. The complaints team uses the shared queue to take the next action.

Evidence: backend/complaints/serializers.py; backend/complaints/views.py; frontend/src/features/complaints/complaint-desk.tsx; backend/complaints/views.py:update,add_note; backend/complaints/permissions.py; backend/complaints/models.py; backend/complaints/serializers.py

## Slide 22 — Complete the sales story
PS/SO records progress after the company’s sales process supports it.

Use a sixth fictional customer or a rehearsed existing demo record. PS chooses Booking Done and a future follow-up, then the record appears under Booked. Open it again, choose Connected and Retail Done, and save final remarks. Show Retailed in the PS view and Won in shared status labels where applicable. The new retail update resolves the open booking follow-up. The application tracks the sales outcome entered by staff; it does not validate payment, finance disbursal, stock allocation, invoicing or delivery documentation. Those actions remain with the company’s existing systems and process.

Evidence: backend/leads/tests.py:test_full_admin_to_cre_to_ps_lead_journey_with_five_followups

## Slide 23 — Walk-ins can go straight to PS/SO
Capture the visitor and select the sales user.

Show the receptionist Capture Lead page and explain that this is a different intake path. The current form captures basic customer details, profession, model, variant, buying plan and PS selection. It does not capture branch or enquiry date in its submitted payload. Consequently, the lead can reach the PS queue but be absent from branch-scoped or enquiry-date-filtered reporting until an authorized user fills those fields. The receptionist dashboard counts their own captures made today. Keep the branch/date completion step explicit; do not claim automatic branch inference from the selected PS.

Use the bulk route for downloaded advertising or partner lead lists. Admin manual entry can place an ordinary enquiry in the allocation pool. CRE’s visible Add lead form is designed for a directly qualified lead with branch and PS selected; the underlying non-walk-in CRE creation path also supports CRE ownership. Receptionist capture forces Walk-in source and Qualified status and can attach a PS. Walk-in capture bypasses normal CRE qualification. Do not describe configured sources as live integrations: this repository supports capture and upload, not a verified live advertising-platform feed.

Evidence: frontend/src/app/(receptionist)/capture/page.tsx; backend/analytics/views.py:ReceptionistAnalyticsView; backend/leads/views.py:perform_create; frontend/src/features/leads/sales-workspace.tsx:saveLead; frontend/src/app/(receptionist)/capture/page.tsx

## Slide 24 — Complaints: shared queue, documented resolution
Only the complaints department changes status, priority or resolution.

Open, In Progress, Escalated, Resolved and Closed are available statuses. Recommend moving a ticket to In Progress when the complaints team starts work, escalating when they need management or another department, resolving when corrective action is complete, and closing after the agreed customer confirmation step. The software does not enforce this full sequence or customer confirmation. Escalated is a status, not evidence of an automatic email or routing event. Closure and resolution require non-empty resolution remarks. Agree who will monitor escalated tickets and how they will contact the relevant department.

This is not the same allocation mechanism as lead distribution. There is no normal manual assignment-to-colleague control exposed in the complaint update serializer. The updater becomes the assigned user, so two resolution staff members need a clear working arrangement. CRE sees only tickets they logged; Admin and the complaints department see the shared queue. The current complaint update does not use the same stale-edit protection as the dedicated lead update flow. The notes provide a readable history of the discussion, but there is no complete old/new audit event for every complaint status or priority change.

These descriptions are proposed operating guidance, not company policy or enforced service-level clocks. Ask the manager to define response targets, escalation contacts and closure evidence for each priority. The product reports complaint status totals, priority and category breakdowns, average resolution hours and trends; Admin additionally sees resolution-team performance. Average resolution uses the recorded resolved timestamp. If a ticket is reopened or its status changes again, the existing timestamp is not cleared automatically, so do not treat that number as an audited SLA compliance score.

Evidence: backend/complaints/models.py; backend/complaints/serializers.py:ComplaintUpdateSerializer; backend/complaints/views.py:update,add_note; backend/complaints/permissions.py; backend/complaints/views.py:ComplaintAnalyticsView,_resolution_team_performance

## Slide 25 — Sales Manager: inspect, understand, direct
Read-only oversight of the configured branch.

The manager’s configured location determines the branch scope. A blank location gives no branch data. The manager cannot change lead status, assign, delete or reopen leads through this role. Coaching and reassignment requests take place through the company’s normal communication process; there is no implemented manager approval inbox. The operational review can identify a stale Fresh lead or an overdue follow-up and then ask the named CRE or PS to act. Flagged filters exist, but do not promise a complete escalation button-to-notification flow without a live check.

Show manager Analytics first, then a person drilldown into Branch leads. The available analyses include source/model results, CRE/PS performance, current status/category splits, monthly views, follow-up information and stale leads. Stale means currently Fresh with a creation date on or before today minus three days; it is not a configurable service target or a measure of every kind of inactivity. Overdue is based on an unresolved scheduled timestamp. Follow-up and call reporting may use activity dates, while lead-period counts typically use enquiry date. Keep filters visible when discussing numbers.

A good review moves from a dashboard count to a specific customer and back. Show who updated the lead, the selected outcome and the next follow-up. Lead audit detail exposes the latest thirty audit entries; do not call the visible panel an unlimited audit export. CSV exports exist for personal and manager reporting. The Admin analytics screen provides company and team review; do not promise a CSV control on that screen. Report values can briefly lag due to analytics caching, so refresh and allow the configured refresh interval after a demo change. Complaint notes are separate from the lead audit history.

Evidence: backend/analytics/views.py:manager_base_queryset; backend/leads/views.py:manager_leads; backend/analytics/tests.py; backend/analytics/views.py:manager_payload,role_rows; frontend/src/features/analytics/sales-manager-analytics-page.tsx; backend/leads/serializers.py:LeadDetailSerializer; backend/analytics/views.py; frontend/src/features/analytics/analytics-page.tsx

## Slide 26 — Read dashboard numbers in context
Current-state counts support daily review; agree definitions before using targets.

Use this slide when the manager asks about numbers or performance measurement. The current funnel draws from status and sales-outcome snapshots. A lead that moved from Qualified to Pending or Won no longer contributes to the current Qualified count, so qualified-to-booked and booked-to-retail ratios are not historical stage conversion probabilities and may be counterintuitive. The company should use this for operational visibility while agreeing the reporting definitions needed for target or incentive calculations. Do not present invented conversion improvements or revenue impact.

Ask what this difference would mean operationally. Eight follow-ups can reflect more active customers, older overdue work or a need for assistance; it does not automatically mean poor performance. Drill into the records, look at promised dates, booking status and latest remarks, then decide whether the owner needs help or Admin should redistribute eligible work. This example demonstrates how to use a workload chart without inventing real company performance data. The chart is intentionally labeled illustrative and should never be presented as a snapshot from the live system.

Evidence: backend/analytics/views.py:summary_for,manager_payload,metrics

## Slide 27 — Make the queues part of the working day
Suggested rhythm; agree timings with the manager.

Position this as a suggested operating routine that the manager can adapt to existing shift timings. The product provides queues, dates, histories and reporting; people still need to review them. A short midday check can focus on leads that remain Fresh, booked customers needing further action and overdue follow-ups. End-of-day review should distinguish work that has a next date from work that lacks an active owner. Admin handles allocation corrections; SM directs branch execution. Complaints need their own queue owner because SM does not have complaint access in this build.

Evidence: 

## Slide 28 — Exceptions: what staff should do next
Keep the customer record and next owner clear.

The dedicated lead update checks changes that occur during its processing and verifies current ownership and active accounts. However, the screen does not send a version token from the moment the modal was opened, so do not claim complete stale-form protection for all edit situations. A normal save error should lead to refresh and review, not repeated blind clicking. Reassignment work created by offboarding has a distinct queue; ordinary assignment buttons are not a general transfer-any-lead control. For manager visibility issues, check the data and filters before assuming the lead was lost.

Keep the discussion operational. Automatic lead feeds, WhatsApp or SMS messaging, integrated calling, payment processing and stock management are not verified capabilities in this build. Assignment and due-reminder records exist in the backend; the current main shell does not display a notification bell, and the deployment configuration does not demonstrate a scheduled worker service. Use queue refreshes for the live presentation and validate reminder delivery separately. The full presenter briefing includes implementation-specific watchpoints so the manager-facing discussion can stay focused.

Evidence: backend/leads/views.py:so_update,assign,auto_assign; backend/analytics/views.py:manager_base_queryset; frontend/src/components/app-shell.tsx; backend/notifications/tasks.py; render.yaml

## Slide 29 — Staff changes need two handovers
Dedicated lifecycle flow for CRE and PS/SO.

In Users, open the lifecycle action for a demo CRE or PS account. The preview shows active work grouped by status, closed records, follow-ups and eligible replacement users. For each actionable status choose a pool or selected replacement users. A changed preview is rejected so Admin must review fresh counts rather than moving work based on an old preview. Closed leads preserve the historical employee association. This dedicated preview-and-route workflow is limited to CRE and PS/SO; do not promise the same lifecycle screen for Sales Manager, Receptionist or complaints staff.

Unlike normal round-robin allocation, offboarding distribution selects the lowest active workload from the chosen eligible replacements and updates that load as each lead moves. For PS work it also requires a non-blank lead branch matching the replacement location. No eligible branch match leaves the lead pooled with a reassignment flag. Ordinary fresh allocation excludes these records, which prevents them being treated as completely new enquiries. Admin can later select pooled records and replacements in All leads → Needs reassignment. Follow-up ownership can move, but its reminder remains held until review.

Explain why this extra step exists: a replacement should not inherit an old reminder without anyone checking whether the customer commitment still makes sense. After offboarding, open follow-ups are held. Admin can approve them, optionally choose a new future time, or resolve the item if it is no longer relevant. Approval requires an active current follow-up owner. A record that changes owner or is resolved during review can reject the stale action. This review is separate from the work allocation step, so end-of-day controls should check both reassignment and held reminders.

Use Disable as the reversible option in a live demo, and use only a disposable employee with prepared work. Permanent Delete removes login capability and scrubs email and phone while retaining history and the display name marked Deleted; it is not a deletion of all historical employee data. A deleted email can be reused for a new account. Re-enabling a disabled user does not pull leads back from replacement staff. The preview route and lifecycle event summary provide the record of who performed the action and the counts moved.

Evidence: backend/accounts/offboarding.py:offboarding_impact,offboard_user; frontend/src/features/team/team-page.tsx; backend/accounts/offboarding.py:offboard_user; backend/leads/views.py:bulk_reassign; backend/leads/views.py:FollowUpViewSet.review; backend/notifications/tasks.py; backend/accounts/offboarding.py; backend/accounts/serializers.py:TeamMemberSerializer

## Slide 30 — Agree the rules for the pilot
Leave the meeting with named owners and a short decision list.

Closing talk track: We have followed the lead from Admin through CRE and PS, shown how the manager reviews the branch, and traced a complaint and a staff handover. The next step is to agree the rules in this table and use them in the pilot. Ask the manager which steps differ from the company’s current practice. Capture a named owner for each change or policy. Avoid promising a go-live date or scope that has not been agreed. The detailed appendix and presenter guide are available for follow-up questions.

Complete this checklist in the environment used for the meeting or pilot. Existing automated workflow tests provide useful evidence for the repository behavior, but they do not confirm deployed configuration, account setup, imported data quality or all browser interactions. Read the companion verification report for what was actually run when building this presentation. In the live rehearsal, use separate browser profiles for different roles because account cookies are shared across tabs in the same browser profile.

This is a proposed timing plan. For a shorter session, narrate the CRE loss and PS loss slides without repeating every field, and focus live clicking on one qualification handoff, one PS follow-up and one complaint resolution. Keep staff offboarding as a prepared preview unless the manager wants to see a full disposable-account exercise. Use the PDF as a fallback if the application or network is slow. Presenter notes provide the detailed explanations even when you skip a reference slide. Finish by recording decisions rather than trying to demonstrate every optional menu.

Evidence: backend/leads/tests.py; backend/analytics/tests.py; backend/complaints/tests.py; backend/accounts/tests.py
