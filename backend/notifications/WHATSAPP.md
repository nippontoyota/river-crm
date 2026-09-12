# WhatsApp SO introductions

The selected provider is **GreenAds Global (Telinfy)**. The CRM records message previews when a CE qualifies a lead and when its SO changes. It does not send WhatsApp messages. The account's Telinfy API variant and webhook contract still need confirming before its sender can be implemented; adding credentials alone will not enable delivery yet.

## Run now, without credentials

1. Apply the `notifications.0002_whatsappcontact_whatsappmessage` migration with `python manage.py migrate` against the intended database before serving the new code. The deployment build currently treats migration failure as non-fatal, so verify the migration succeeded before routing traffic.
2. Set the customer-facing business name in the backend environment. All other defaults below work without credentials.
3. Ensure each SO has a full name and a valid customer-facing phone number in their account.
4. Open a fresh lead as its assigned CE, choose Qualified and an SO, and record the customer's agreement using the checkbox.
5. Save, then reopen lead details to see the WhatsApp introduction. The save confirmation also reports whether the introduction was previewed or skipped.

```dotenv
WHATSAPP_MODE=preview
WHATSAPP_BUSINESS_NAME=Incheon Mobility
WHATSAPP_LANGUAGE=en
WHATSAPP_TEMPLATE_INTRODUCTION=so_introduction
WHATSAPP_TEMPLATE_REASSIGNMENT=so_reassignment
```

`WHATSAPP_MODE` accepts only `preview` and `disabled`. Any other value, including `live`, fails application startup. In disabled mode, new qualifying assignment events are recorded as skipped. Neither supported mode calls an external service or needs a Celery worker. Template names and language are provisional identifiers until a provider approves matching templates.

## Behavior

- Qualification uses `Lead.assigned_ps` for the SO name and phone. `assigned_so` is the CE owner despite its legacy name.
- Enrollment starts at an actual CE transition to Qualified. Existing qualified leads, imports alone, walk-in creation, SO-generated leads, and administrator-only status changes are not enrolled automatically. A fresh imported lead can enroll when its CE later qualifies it.
- The optional agreement checkbox starts unchecked when no agreement exists. Without agreement, qualification succeeds and messaging is skipped. Agreement is tied to the normalized customer number, recording actor and time.
- Assigned CEs and administrators may record agreement or withdrawal in lead details after enrollment. Permission changes are audited. Saving agreement alone never recreates or sends earlier messages.
- Changing the customer number invalidates agreement and cancels existing previews for the old number. Fresh agreement may be recorded explicitly in the same qualification request.
- Each distinct SO assignment on an enrolled, open lead creates a new record. Individual assignment, generic detail assignment, bulk assignment, bulk reassignment, and account offboarding use the same audit hook.
- Repeated saves and assignments to the same SO do not create another record. A → B → A creates separate assignment records. Removing an SO cancels previews; returning that same SO without an intervening different assignment does not create a duplicate.
- Records are previews, skipped, or cancelled. Missing consent, invalid contact details, or an inactive SO never cause messaging to block qualification. Invalid lead input still follows the existing CRM validation rules.
- Closed or deleted leads cannot create new previews. A superseded preview is retained as cancelled, with its original recipient, variables, and body for history. Preview and skipped records can never be released for live delivery.
- Local ten-digit numbers are normalized with `+91`; SO numbers with an explicit international prefix retain it. Normalization validates format, not WhatsApp registration or deliverability.
- The latest 30 message records are visible to users who already have access to the lead. SOs and managers can read history but cannot change customer agreement. No generic public message/history endpoint is exposed.

## API and persistence

`PATCH /api/leads/{id}/so-update/` accepts an optional `whatsapp_agreed` boolean. Older clients may omit it; omission never grants permission. Qualification, permission recording, and message creation share the lead transaction.

`PATCH /api/leads/{id}/whatsapp-agreement/` accepts `{"agreed": true}` or `{"agreed": false}` and returns the updated lead detail. It checks the current assigned CE/admin and active account under database locks. It does not change sales progress.

Lead-detail responses include `whatsapp`: mode, agreement state, recorded phone/user/time, enrollment time, permission to edit agreement, and message history. Message history includes template identifiers, variables, rendered body, status/reason, and timestamps. These fields are read-only.

`WhatsAppContact` stores per-lead enrollment and permission. `WhatsAppMessage.source_audit` is unique in the database; lead locks and the stored last SO prevent duplicate introductions when qualification and assignment produce separate audits. Single-save signals and the existing `LeadAudit` bulk-create hook both call `record_lead_audit`. New assignment paths must continue emitting transactional lead audits.

`notifications.whatsapp.send_whatsapp_message(message)` is the reserved sender entry point. It always rejects calls until the provider integration is implemented. There is no send/retry endpoint and no scheduled task that can release previews.

## GreenAds Global setup before live activation

GreenAds Global's [official website](https://www.greenadsglobal.com/) links to the [Telinfy WhatsApp Cloud reference](https://telinfy-cloud.readme.io/reference/introduction-to-api). Its public [template variables example](https://telinfy-cloud.readme.io/reference/template-api-to-send-a-message-copy) documents `POST https://api.telinfy.net/gaca/whatsapp/templates/message/`, an `Api-Key` header, and `to`, `templateName`, `language`, and `body.parameters` fields. This is a reference for the Cloud variant, not confirmation that this account uses it.

Telinfy also publishes [hub.telinfy.com API documentation](https://www.postman.com/telinfy-89/telinfy-api-documentation-hub-telinfy-com/overview). Confirm the account's dashboard URL or obtain its own API/Postman documentation before choosing a request format. The Cloud reference does not specify a usable message-ID response or authenticated delivery-webhook contract. Its introduction says support supplies the API key and webhook registration during onboarding, and describes partner webhooks as a paid feature; confirm availability for this account.

Request these integration details from GreenAds support (credentials can follow later):

- The account's API documentation/Postman collection, template-send endpoint and authentication format.
- A sample successful send response with the provider message ID, and documented error responses.
- Delivery/read/failure and incoming-message webhook examples, registration procedure and authentication/signature verification details.
- Retry/idempotency or message-status lookup support, and whether partner webhooks are included in the subscription.
- Approved template names/IDs and language codes for both messages below. If using positional body variables, use the order: customer name, business name, SO name, SO phone.

Use the GreenAds/Telinfy inbox for customer replies and opt-outs once the account is active. Its subscription must include the template API and callback features used by the integration.

Prepare:

- A company WhatsApp sender number, business display name, and the business/number verification required by the provider and Meta.
- An approved introduction template and a separate reassignment template, with variables for customer name, business name, SO name, and SO phone. Use the language code the provider actually approves. Approval and category classification are not guaranteed.
- Provider API credentials, sender/account identifiers, API endpoint where applicable, and webhook authentication settings. Store secrets only in backend/worker environment variables.
- Billing arrangements for the provider and message charges.
- A public HTTPS callback endpoint and operational ownership of customer replies and opt-outs.

Business-initiated introductions use approved templates. A telephone call does not open WhatsApp's 24-hour customer service window. Customer permission and withdrawal must be respected. See the [WhatsApp Business Messaging Policy](https://business.whatsapp.com/policy).

Proposed introduction:

> Hello {{customer_name}}, thank you for speaking with our team at {{business_name}}. Your Sales Officer, {{so_name}}, will contact you regarding your enquiry. You can reach them on {{so_phone}}.

Proposed reassignment:

> Hello {{customer_name}}, your Sales Officer for your enquiry with {{business_name}} has changed. Your new contact is {{so_name}}, reachable on {{so_phone}}.

Both messages come from the registered company sender. The SO phone appears in the body.

## Remaining GreenAds integration work

1. Confirm the account's API variant, then implement its authenticated template request and map the stored named variables to its parameter format. Define the exact GreenAds environment settings and validate them before live mode can start. Keep preview history permanently excluded from the live queue.
2. Add live message states and provider message ID/error/attempt timestamps. Preserve acceptance, delivery, and read confirmation separately; API acceptance does not prove delivery.
3. Persist live pending records in the same lead transaction; enqueue only after commit. Use the existing Celery dependency with a real worker and a periodic recovery task for pending records whose enqueue failed. The current `render.yaml` deploys only a web process with `CELERY_TASK_ALWAYS_EAGER=true`; configure a Redis broker, worker and scheduler, and disable eager execution before activation.
4. Claim each pending record once and recheck permission, recipient, active SO, current assignment and open lead immediately before dispatch. Cancel stale assignments. Bound retries for explicit transient failures; preserve ambiguous timeouts as delivery unknown unless the provider offers safe idempotency/reconciliation.
5. Implement authenticated webhook processing, duplicate/out-of-order callback handling, and correlation to the original message. Synchronize provider opt-outs into suppression for every matching customer number; the current CRM permission store is per lead, not a global contact directory.
6. Test actual template delivery and callbacks with approved test recipients. Verify worker recovery, failure reporting and opt-out handling. Enable live mode only after those checks; never replay existing previews or skipped records.

## Verification

```bash
DATABASE_URL=sqlite:////tmp/crm-whatsapp-tests.sqlite3 .venv/bin/python manage.py test notifications leads.tests leads.test_intake leads.test_outcomes accounts.tests --noinput
```

Tests exercise qualification, legacy clients, agreement and access control, both phone-edit paths, duplicate events, database uniqueness, A → B → A reassignment, individual/bulk assignment, actual account offboarding, closed/deleted leads, transaction rollback, and rejection of live sending. SQLite tests check event uniqueness and sequential duplicates; run concurrent qualification requests on PostgreSQL before enabling a live sender.
