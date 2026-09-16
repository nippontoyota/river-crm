from pathlib import Path
from html import escape

ROOT = Path(__file__).resolve().parent
pages = []

def table(headers, rows, widths=None):
    cols = '<colgroup>' + ''.join(f'<col style="width:{w}%">' for w in widths) + '</colgroup>' if widths else ''
    return '<table>'+cols+'<thead><tr>'+''.join(f'<th>{x}</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{x}</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table>'

def note(title, text, kind='note'):
    return f'<aside class="{kind}"><strong>{title}</strong><p>{text}</p></aside>'

def steps(items):
    return '<ol>'+''.join(f'<li>{x}</li>' for x in items)+'</ol>'

def page(section, title, owner, body):
    pages.append((section,title,owner,body))

page('START HERE', 'Connect Meta leads<br>to the CRM', 'Agency setup guide', '''
<p class="deck">A practical guide to account access, Meta Developers, automatic lead capture and WhatsApp setup.</p>
<div class="flow"><span>Customer submits<br><b>Meta Instant Form</b></span><i>→</i><span>Meta notifies<br><b>CRM backend</b></span><i>→</i><span>CRM retrieves<br><b>Customer enquiry</b></span></div>
<p>This guide is for the social media agency, the client’s Meta administrator and the CRM developer. It explains what each person needs to provide, where to find it, and how to complete the connection together.</p>
<h3>Use the guide in this order</h3>
'''+table(['Pages','Task','Who leads'],[
('2–3','Gather accounts, forms and access','Agency + client administrator'),
('4–5','Create the app and authorize lead access','Administrator + developer'),
('6–8','Configure the backend, webhooks and CRM forms','Developer'),
('9–10','Test, resolve issues and approve launch','All three'),
('11–12','Set up WhatsApp and agree the live workflow','Number owner + developer'),
('13–14','Complete the handover and reference checks','Agency + administrator')],[13,57,30])+note('What this connection covers','Facebook and Instagram <b>Instant Form</b> submissions. Website enquiries, Messenger/Instagram messages and click-to-WhatsApp chats need their own integrations. Show the developer one active ad for each enquiry source you use.')+'''
<h3>About the screenshots</h3>
<p>Two authentic Facebook setup screenshots appear on pages 4 and 9. They come from Meta’s published developer guide from 2022. They illustrate the relevant controls; they are <b>archival reference screens</b>, not captures of the client’s account or a guarantee of the current interface.</p>
<p class="small">Meta changes menu labels and onboarding flows. Use the named function if your menu differs. Current account permissions, app-review requirements and available onboarding options must be checked in the logged-in dashboard.</p>
<div class="byline"><b>Sajad Hussain</b><span>SWE, Nippon Toyota</span><small>16 September 2026 · Version 1.0</small></div>
''')

page('01 / PREPARATION', 'Have these ready before starting', 'Agency + client administrator', '''
<p class="deck">The most useful starting point is a setup call with the person who controls the client’s Meta assets.</p>
'''+table(['Item','What to prepare'],[
('Meta login','Your own Facebook account with access to the client’s assets. Complete developer registration and two-factor authentication if prompted.'),
('Business Portfolio','Client’s business name, numeric portfolio ID and the administrator who can assign assets. Identify any assets owned by the agency instead.'),
('Facebook Page','Page name, URL and Page ID for each branch or business generating enquiries.'),
('Advertising account','Ad account name/ID and the campaigns using the selected forms. Access to campaign information may require additional permissions.'),
('Instant Forms','Names and IDs where visible, the owning Page, questions, answer choices and a form preview. Remove real customer data from shared examples.'),
('Business website','The real website and published privacy-policy URL. The developer will confirm any app-domain or data-deletion requirements.'),
('CRM deployment','Developer confirms the CRM login URL, backend API URL and that the intake worker and scheduler are available.'),
('WhatsApp, if included','Business number, its owner, current phone app/provider, account IDs where available, billing contact and approved templates.')],[27,73])+'''
<h3>Agree responsibilities</h3>
'''+table(['Person','Responsibility'],[
('Agency','Identify campaigns/forms, explain field meanings and notify us when forms change.'),
('Client administrator','Approve asset access, confirm ownership, complete verification and billing steps.'),
('Sajad / CRM developer','Configure tokens, backend settings, webhook subscriptions, mapping and tests.')],[30,70])+note('Access invitation, not password sharing','Invite the developer’s confirmed email or business partner account. Keep the business’s ownership and recovery access with the client. Transfer API tokens and app secrets through an agreed secure channel.')+'''
<p class="small">Suggested call preparation: laptop, access to Business Settings and Meta Developers, one published form, and a person available to verify the WhatsApp number if that setup is included.</p>
''')

page('02 / BUSINESS SETTINGS', 'Give access to the correct assets', 'Client administrator', '''
<p class="path">Open <a href="https://business.facebook.com/settings">business.facebook.com/settings</a> → select the client’s business</p>
'''+steps([
'<b>Confirm the business.</b> Open <b>Business info / Business portfolio info</b>. Record its name and ID. Check the business selector before making changes.',
'<b>Find the Page.</b> Open <b>Accounts → Pages</b>, select the client’s Page and record its ID. Repeat for additional branch Pages.',
'<b>Find the ad account.</b> Open <b>Accounts → Ad accounts</b>. Record the account associated with the relevant lead campaigns.',
'<b>Invite the integration contact.</b> Under <b>Users → People</b>, choose the invite option and use the developer’s confirmed email. Assign the relevant assets and tasks. If granting access to another business, use <b>Partners</b> and that business’s ID.',
'<b>Check leads access.</b> Look for <b>Integrations → Leads access</b>. Select the Page. If the business uses customized leads access, assign the appropriate people/partner and CRM app when it is available.',
'<b>Confirm acceptance.</b> The developer accepts the invitation and checks that the intended Page and its lead data are accessible. App-dashboard access may also need a separate app-role or business-asset assignment.'
])+note('If a menu is missing','Some accounts show <b>Settings → More business settings</b>. A missing Page, System users or Leads access option can indicate that you selected the wrong portfolio or lack the required administrator permissions. Ask the asset owner to complete that step.')+'''
<h3>Record the result</h3>
'''+table(['Detail','Response'],[
('Business Portfolio name / ID','<div class="line"></div>'),
('Page name / ID / owner','<div class="line"></div>'),
('Ad account name / ID / owner','<div class="line"></div>'),
('Invitation email or partner Business ID','<div class="line"></div>'),
('Administrator handling missing access','<div class="line"></div>')],[43,57])+'''
<p class="small"><b>Checkpoint:</b> the developer can identify the selected Page and confirm permission to retrieve its leads. Managing ads or viewing the Page alone does not complete the leads-access check.</p>
''')

page('03 / META DEVELOPERS', 'Create or select the integration app', 'Administrator + developer', '''
<p class="path"><a href="https://developers.facebook.com/apps/">Meta for Developers → My Apps</a> → Create App</p>
'''+steps([
'<b>Check for an existing app first.</b> Reuse a suitable client-owned app only after checking its purpose and existing integrations.',
'<b>Choose the business/Marketing API route.</b> In a use-case flow, look for the option related to managing ads or lead data. In an older app-type flow, select <b>Business</b>. Menu wording varies; the developer should confirm that the app exposes lead-retrieval and Page-webhook capabilities.',
'<b>Name the app.</b> Use <b>Nippon Toyota CRM</b> or the client’s approved name. Enter a monitored work email and select the correct Business Portfolio when requested.',
'<b>Open App settings → Basic.</b> Record the <b>App ID</b>. The developer securely obtains the <b>App Secret</b>. Add the real privacy-policy and data-deletion information where requested. Use only the actual CRM/website domains.'
])+'''
<div class="split">
<div><h3>What success looks like</h3><p>The app appears in My Apps, the correct owner/business is associated with it, and the developer has access to its configuration.</p><p>The developer can now configure the lead permissions and Page webhook.</p>'''+note('If the business is not listed','Return to page 3 and have the administrator resolve access. Avoid choosing an unrelated portfolio just to get through the form.')+'''</div>
<figure><img src="assets/meta-app-type-reference.png" class="app-shot" alt="Authentic archived Meta app-type selection screen showing Business"><figcaption><b>Reference screenshot:</b> Business app-type selection. Meta developer guide, 2022, p. 12 [1]. Modern accounts may start with use cases instead.</figcaption></figure>
</div>
<p class="small">If Meta asks for an App Domain, enter the hostname only, without a path. A webhook callback is configured separately and uses the complete HTTPS URL on page 7.</p>
''')

page('04 / PERMISSIONS & TOKENS', 'Authorize access to the Page’s leads', 'Developer, with the administrator present', '''
<p class="deck">An access token is a credential that lets the backend read data for the assets it is authorized to access.</p>
<h3>A. Enable the needed app permissions</h3>
<p>Open the relevant use case’s <b>Customize</b> screen, or <b>App Review → Permissions and Features</b>. The developer checks the permissions needed for the chosen authorization flow.</p>
'''+table(['Permission','Why the developer checks it'],[
('<code>leads_retrieval</code>','Retrieve answers submitted through lead forms.'),
('<code>pages_manage_metadata</code>','Manage the app’s Page webhook subscription.'),
('<code>pages_show_list</code>','Identify Pages available to the authorizing account.'),
('Supporting Page / ad permissions','Check the dependencies Meta lists, including Page engagement/ad permissions and advertising access where required for form or campaign reads.')],[39,61])+'''
<h3>B. Obtain a token for initial testing</h3>
'''+steps([
'Open <a href="https://developers.facebook.com/tools/explorer/">Graph API Explorer</a>. Select the newly configured app in the <b>Meta App</b> selector and choose a currently supported Graph API version.',
'Use the token menu to authorize the account with the required permissions. The account must have access to the intended Page and its leads. Complete the asset-selection prompts.',
'Obtain the appropriate <b>Page access token</b>. If the token menu does not offer it directly, the developer can use the authorized user token to request <code>GET /me/accounts?fields=id,name,access_token</code> and select the matching Page entry.',
'Test the Page token with a Page/form read. Use Meta’s <a href="https://developers.facebook.com/tools/debug/accesstoken/">Access Token Debugger</a> to check app, type, permissions and expiry. Do not share a screenshot containing the token.'
])+'''
<h3>C. Prepare production credentials</h3>
<p>Before launch, the developer replaces temporary test credentials with a supported production arrangement: an appropriately authorized system-user flow or long-lived Page-token flow. For a system user, the administrator opens <b>Business Settings → Users → System users</b>, assigns the relevant app/assets, and generates the token with the required permissions.</p>
'''+note('Token lifetime is not a reliability guarantee','Record who owns the credential and who replaces it. Permission removal, business changes or revocation can stop access even when a token has no scheduled expiry. The agency should notify the developer before changing asset access.')+'''
<p class="small">App Review / Advanced Access may be required, especially when accessing assets owned by another business. Complete the requirements shown for the actual app and ownership arrangement before accepting live leads.</p>
''')

page('05 / CRM BACKEND', 'Prepare the receiving CRM service', 'Developer only', '''
<p class="deck">Complete this page before clicking “Verify and save” in Meta. The agency supplies access; the developer configures the CRM hosting environment.</p>
<p>The integration code defines this lead webhook path:</p>
<pre>https://YOUR-BACKEND-DOMAIN/api/integrations/meta/webhook/</pre>
<p>Replace <code>YOUR-BACKEND-DOMAIN</code> with the deployed API hostname. The CRM’s browser/login URL may be a different domain. The endpoint must be publicly reachable over HTTPS.</p>
'''+table(['Backend setting','What to configure'],[
('<code>META_APP_SECRET</code>','App Secret from the app that sends the webhook; used to verify incoming signatures.'),
('<code>META_VERIFY_TOKEN</code>','A strong random value generated by the developer. Enter the identical value in Meta’s webhook Verify token field.'),
('<code>META_GRAPH_VERSION</code>','Explicitly set a currently supported version confirmed in the app dashboard. Do not copy an old version from screenshots.'),
('<code>INTAKE_SECRETS_JSON</code>','Store the authorized access token under a stable reference, for example <code>main-meta</code>.'),
('<code>INTAKE_ENABLED</code>','Keep false during preparation. Set true when the selected connection/forms and background services are ready for testing.'),
('Worker / scheduler settings','Configure the shared Redis connection and environment, stable intake fingerprint key and <code>CELERY_TASK_ALWAYS_EAGER=false</code> in production.')],[38,62])+'''
<p class="small">Example structure only; replace the placeholder securely and preserve other existing entries:</p>
<pre>{"main-meta":{"access_token":"REPLACE_SECURELY"}}</pre>
'''+steps([
'Deploy the intake code and apply migrations. Confirm that the web service, worker and scheduler use the same required configuration.',
'Confirm webhook verification works with the configured verify token. The GET verification handshake and the processing of POST lead events are separate checks.',
'Confirm background-service health in CRM Lead Intake. The existing deployment blueprint includes a web service, queue, worker and scheduler; the operator must verify their live deployment and costs.'
])+note('Three different values','<b>App Secret:</b> Meta-issued secret for the app. <b>Access token:</b> authorization to read leads. <b>Verify token:</b> developer-generated value for webhook verification. They are not interchangeable.')+'''

''')

page('06 / WEBHOOKS', 'Connect Meta notifications to the CRM', 'Developer + administrator', '''
<p class="path">Meta app dashboard → Webhooks → Page</p>
'''+steps([
'Open <b>Webhooks</b> in the app dashboard. If it is not available, add or configure the relevant product/use case that exposes Page webhooks.',
'Select the <b>Page</b> object and open its subscription/configuration dialog.',
'Enter the backend callback URL from page 6 and the identical verify-token value configured on the server.',
'Click <b>Verify and save</b>. A verification error must be resolved before continuing.',
'Find <b>leadgen</b> in the Page field list and subscribe to it.'
])+table(['Meta field','Value for this CRM'],[
('Object','<b>Page</b>'),
('Callback URL','<code>https://YOUR-BACKEND-DOMAIN/api/integrations/meta/webhook/</code>'),
('Verify token','The exact value stored as <code>META_VERIFY_TOKEN</code>'),
('Subscribed field','<code>leadgen</code>')],[28,72])+'''
<h3>Also connect the actual Facebook Page</h3>
<p>The app-level webhook defines where events go. The developer must also subscribe each intended Page to the app. In Graph API Explorer, select the app, supported API version and the authorized <b>Page token</b>.</p>
'''+steps([
'Select <b>POST</b> and enter the following request, replacing <code>PAGE_ID</code> with the client’s numeric Page ID:',
'Click <b>Submit</b> and inspect the response. A successful subscription should return a success result.',
'Switch to <b>GET</b> and inspect the Page’s subscriptions to confirm this app and the <code>leadgen</code> field.'
])+'''<pre>POST /PAGE_ID/subscribed_apps?subscribed_fields=leadgen
GET  /PAGE_ID/subscribed_apps</pre>
<p>Repeat for every Page included in the integration. Recheck Business Settings → Leads access if the app or authorizing person cannot retrieve leads.</p>
'''+note('Verification is only one checkpoint','“Verify and save” confirms the callback handshake. It does not prove that the Page is subscribed, that the access token can retrieve answers, or that the CRM has enabled the form.')+'''
<p class="small">The Page subscription operation is documented in Meta’s maintained Page SDK [2]. A Pixel or Conversions API connection serves a different purpose and is not required just to receive these lead-form enquiries.</p>
''')

page('07 / CRM CONFIGURATION', 'Choose forms and map their answers', 'Developer, with agency input', '''
<p class="path">CRM administrator login → Lead Intake → Connections / Field mappings</p>
<h3>A. Identify the selected forms</h3>
<p>The agency opens <b>Business Suite → All tools → Instant forms</b> and provides the selected names and owning Page. If a Form ID is not visible, the developer can retrieve it using the authorized Page access:</p>
<pre>GET /PAGE_ID/leadgen_forms?fields=id,name,status</pre>
<h3>B. Add a disabled connection</h3>
'''+table(['CRM field','Example / instruction'],[
('Name','<b>Client Meta Leads</b>'),
('Origin','<b>META</b>'),
('Source','Select the agreed source from Admin Lists; add it there first if missing.'),
('Secret reference','<code>main-meta</code>, matching the key in <code>INTAKE_SECRETS_JSON</code>.'),
('Activation time','Agreed starting time for this connection. Choose carefully; identifiers and activation times cannot be edited later.')],[30,70])+'''
<h3>C. Add each selected form</h3>
<p>Choose the connection. Enter a recognizable name, the Meta Form ID as <b>external id</b>, its <b>page id</b>, and the activation time. Page ID is required for Meta even if the shared form screen does not mark it with an asterisk. Create the form disabled.</p>
<h3>D. Save and preview its mapping</h3>
'''+table(['Example form answer','CRM destination'],[
('<code>full_name</code> / Customer name','<code>name</code>'),
('<code>phone_number</code> / Mobile number','<code>phone</code>'),
('Email / interested model / city','<code>email</code> / <code>model_interest</code> / <code>city</code>'),
('Branch / campaign-specific values','Map supplied answers or set agreed defaults and value aliases.')],[48,52])+'''
<p>Open <b>Field mappings</b>, select the form, configure the exact answer labels and save a version. Preview a safe sample. Name and a valid Indian phone number are required for intake; populated model/branch values must match CRM lists.</p>
'''+note('Enable only after mapping is ready','The developer enables the intake service, connection and selected form for testing. New or duplicated Meta forms have their own IDs and must be added explicitly. Historical imports need a separate agreed plan.')+'''
<p class="small">Form listing and the form’s leads edge are exposed by Meta’s maintained SDK [2, 3].</p>
''')

page('08 / END-TO-END TEST', 'Submit a test lead and follow it through', 'Agency + developer', '''
<p class="path"><a href="https://developers.facebook.com/tools/lead-ads-testing/">developers.facebook.com/tools/lead-ads-testing/</a></p>
'''+steps([
'Select the <b>client’s Page</b> and one of the configured <b>forms</b>. Confirm that its IDs match the CRM configuration.',
'If the tool says a test lead already exists, remove that test entry using <b>Delete lead</b> before creating another. This is the tool’s test entry, not a request to delete CRM customer records.',
'Create a test lead. Where a form preview is available, enter a valid test name and phone number. Default dummy answers may fail the CRM’s phone validation.',
'Open <b>CRM → Lead Intake → Receipts</b>. Confirm receipt arrival, then inspect its state and the mapped details. Valid new enquiries should appear in the unassigned lead pool under healthy processing conditions.',
'If the receipt is <b>NEEDS_REVIEW</b>, check the phone format, required answers, choice values and duplicate matches. Correct/reprocess or resolve the duplicate through the review controls.'
])+'''
<figure class="wide-shot"><div class="test-shot"><img src="assets/meta-lead-testing-reference.png" alt="Authentic archived Facebook Lead Ads Testing Tool with Page and Form selectors, Create lead and Delete lead controls"></div><figcaption><b>Reference screenshot:</b> Meta Lead Ads Testing Tool, extracted from Meta’s developer guide, 2022, p. 16 [1]. The view shows the relevant upper portion of the published screen; current styling may differ. IDs shown belong to the source’s example.</figcaption></figure>
<h3>Acceptance checks</h3>
<p class="check">□ Name and phone arrive correctly. &nbsp; □ Model, city, branch and campaign are correct.<br>□ No unintended extra lead appears when the same event is retried.<br>□ Duplicate or incomplete enquiries enter the review workflow.<br>□ Test each selected Page/form and confirm who assigns new leads to sales staff.</p>
'''+note('A webhook test is not a complete lead test','Meta’s generic webhook sample can contain unconfigured IDs. Use the selected real form and verify that the CRM retrieves its actual test answers, not only that the callback receives an event.')+'''
<p class="small">Record the Page, Form ID, lead/test ID, submission time and CRM receipt/lead ID. Share these identifiers for troubleshooting; omit tokens and unnecessary customer information.</p>
''')

page('09 / LAUNCH & TROUBLESHOOTING', 'Complete checks before going live', 'Developer + client administrator', '''
<h3>Confirm production access</h3>
<p>Open the app’s <b>App Review / Permissions and Features / Publish</b> area, as available. Confirm the required access levels, app status and any business-verification steps for the actual assets and ownership arrangement.</p>
<p>If Meta requests a review, provide a clear description of the lead-retrieval use case, the required permissions, applicable privacy/deletion information, and a recording or test instructions demonstrating the workflow. The client administrator supplies verification documents when requested.</p>
'''+note('Do not promise launch solely from a test result','Development access can allow limited testing without proving production access to another business’s assets. Resolve the requirements shown in the app dashboard, then test the approved live flow.')+'''
<h3>Common problems and the next check</h3>
'''+table(['Symptom','What to check'],[
('Business / Page not visible','Correct portfolio selected? Invitation accepted? Does the logged-in person have asset access?'),
('Permission missing from token menu','Correct app/use case? Permission added? Required dependencies and access level available?'),
('Webhook verification fails','Public HTTPS backend URL, exact path, deployed endpoint and matching verify token. Check redirects and server errors.'),
('Webhook verifies, but no receipts','Page subscribed to this app? <code>leadgen</code> enabled? Intake enabled? Correct Page/Form IDs and activation time?'),
('Receipt fails or connection pauses','Expired/revoked token, missing lead access or unavailable form. Fix access/credentials, then use Resume/Retry in CRM.'),
('Receipt says NEEDS_REVIEW','Missing/invalid answers, unsupported configured choices or duplicate phone. Inspect the reason and resolve it in Lead Intake.'),
('Receipt remains unprocessed','Check worker/scheduler health, queue connectivity and shared settings. Do not repeatedly submit the same customer enquiry.'),
('Campaign is blank','Check attribution on the lead and permissions for campaign retrieval. Some test or organic submissions may lack ad attribution.')],[34,66])+'''
<h3>Agree ownership after launch</h3>
<p>Nominate a contact for new forms, changed campaigns, token replacement and failed imports. The CRM includes periodic reconciliation for enabled forms, but someone must monitor errors and paused connections. Do not assume all new forms are connected automatically.</p>
<p class="check">□ Production access confirmed &nbsp; □ Tests approved &nbsp; □ Activation time agreed<br>□ Monitoring contact assigned &nbsp; □ Agency knows how to report form changes</p>
''')

page('10 / WHATSAPP ONBOARDING', 'Identify the right WhatsApp route', 'Number owner + agency + developer', '''
<p class="deck">Complete this section if WhatsApp is part of the project. Lead-form integration can be configured independently.</p>
'''+table(['Current setup','What to do next'],[
('WhatsApp Business app on a phone','Confirm whether staff must keep using the app. Have the developer check available coexistence/onboarding or migration options before changing the number’s registration.'),
('Existing provider such as WATI, Interakt or AiSensy','Share provider name, account/dashboard access, API documentation, plan limits and webhook support. Decide whether to integrate through that provider or plan a migration.'),
('Existing direct Meta Cloud API','Identify the owning business, app, WABA, Phone Number ID, templates and credential owner. Review the existing configuration before adding subscriptions.'),
('No business WhatsApp setup','Agree a client-owned number, display name, verification contact, billing owner and the supported onboarding route.')],[37,63])+'''
<h3>For direct Meta Cloud API setup</h3>
'''+steps([
'In <b>Meta for Developers</b>, select the appropriate app and add/configure the <b>WhatsApp</b> product or business-messaging use case. If the existing app cannot support it, the developer should create a suitable app under the correct business.',
'Open <b>WhatsApp → API Setup / Getting Started</b>. Confirm the selected Business Portfolio. Use the provided test setup before registering or moving the customer-facing number.',
'Add a consenting test recipient as required by the setup screen and send the sample message. This tests Meta connectivity; it does not yet connect the CRM.',
'For the business number, follow the supported onboarding process, confirm the business display name and have the owner complete SMS/voice verification and registration steps. Check two-step verification requirements with the developer.'
])+'''
<h3>Record identifiers, not secrets</h3>
'''+table(['Identifier','Where to look'],[
('WABA ID','Business Settings → Accounts → WhatsApp accounts, or the app’s WhatsApp setup panel.'),
('Phone Number ID','WhatsApp API Setup / Getting Started for the selected actual business number.'),
('Business phone number','The number customers will see, including its country code.')],[34,66])+'''
<p class="small">A WABA ID, Business Portfolio ID and Phone Number ID refer to different objects. A Phone Number ID is not the actual telephone number. Meta’s official Cloud API reference explains the required assets [4]; number registration is covered separately [5].</p>
''')

page('11 / WHATSAPP PRODUCTION', 'Prepare credentials, messages and replies', 'Developer + WhatsApp administrator', '''
<h3>A. Generate a suitable production token</h3>
<p>For a direct Meta setup, open <b>Business Settings → Users → System users</b>. Create/select the integration system user, assign the relevant app and WhatsApp assets, then generate a token for the app. Confirm the necessary <code>whatsapp_business_messaging</code> and <code>whatsapp_business_management</code> permissions and record its expiry/rotation owner. The temporary setup token is for testing. [4]</p>
<h3>B. Create or review message templates</h3>
<p>Open <b>Business Suite → All tools → WhatsApp Manager → Message templates</b>. Agree the text, language, variable fields and purpose of each message, then submit templates for approval. Record exact approved names and language codes.</p>
'''+table(['Proposed message','Agency / client decision'],[
('Enquiry acknowledgement','Send immediately, after qualification, or only on staff action?'),
('Salesperson introduction','Which name, branch and contact details should the message include?'),
('Reassignment notice','Should the customer be informed when their salesperson changes?'),
('Customer replies','Who responds, and in which inbox: CRM, provider or supported phone-app workflow?')],[35,65])+'''
<p>The business must have the recipient’s opt-in and honor opt-outs. Business-initiated conversations require approved templates. Free-form replies are allowed within 24 hours of the customer’s last message; outside that window, use approved templates. A phone number in a lead form alone does not establish messaging permission. [6]</p>
<h3>C. Connect the webhook and complete the CRM work</h3>
'''+steps([
'The developer implements and supplies the <b>WhatsApp-specific callback URL</b> and verify token, then configures it in the app’s WhatsApp/Webhooks settings.',
'Subscribe to the relevant <b>messages</b> notifications and subscribe the app to the intended WABA. Verify incoming replies and delivery updates. WABA subscription is separate from configuring the callback. [7]',
'Confirm billing is ready for paid messages and check any account restrictions or verification requests. With an existing provider, use its supported token/webhook process instead.',
'Test an approved template with a consenting recipient. Check variable substitution, delivery status, reply handling and opt-out behavior before enabling the agreed automation.'
])+note('Current CRM status: live WhatsApp still needs implementation','The current CRM records WhatsApp message previews. It does not yet implement a live sender or a WhatsApp webhook. Adding Meta credentials alone will not enable live delivery. The developer must complete that integration. Do not use the Meta lead-form callback as the WhatsApp callback.')+'''
<p class="small">Existing preview records must not be sent later as a backlog. Agree fresh trigger rules and launch approval after the provider integration is ready.</p>
''')

page('12 / HANDOVER', 'Return these details to Sajad', 'Agency + client administrator', '''
<p class="deck">Complete the identifiers and status below. Use “Not set up” or name the person who can help if an item is unavailable.</p>
'''+table(['Account / detail','Response'],[
('Agency contact / email / phone','<div class="line"></div>'),
('Client administrator / contact','<div class="line"></div>'),
('Business Portfolio name / ID','<div class="line"></div>'),
('Facebook Page name / ID','<div class="line"></div>'),
('Ad account name / ID','<div class="line"></div>'),
('Meta app name / App ID / owner','<div class="line"></div>'),
('Selected forms / Form IDs','<div class="line"></div><div class="line"></div>'),
('WhatsApp number / current provider','<div class="line"></div>'),
('WABA ID / Phone Number ID','<div class="line"></div>'),
('Invitation accepted / leads access status','<div class="line"></div>'),
('Billing / credential replacement contact','<div class="line"></div>'),
('Setup call availability','<div class="line"></div>')],[45,55])+'''
<h3>Attach where available</h3>
<p class="check">□ Selected form previews and exact question labels<br>□ Vehicle-model choices and form-to-branch/campaign mapping<br>□ Approved WhatsApp templates, language codes and variable meanings<br>□ Current consent wording and reply/opt-out owner<br>□ Any error message, affected account ID and time of the failed test</p>
'''+note('Keep secret values out of this handover','Do not enter Facebook passwords, access tokens, App Secrets, verification codes or two-step PINs here. Coordinate secure credential transfer with the developer; the number owner enters verification codes during setup.')+'''
<p class="small">A screenshot of a menu or error is useful when an option is missing. Hide tokens, secrets and unrelated customer details before sending it.</p>
''')

page('13 / REFERENCES & SIGN-OFF', 'Reference links and final confirmation', 'For the agency and client administrator', '''
<p>Links in this PDF are clickable. Meta tools may require login and the appropriate account permissions.</p>
<h3>Account setup and testing tools</h3>
<div class="links">
<p><a href="https://business.facebook.com/settings">Meta Business Settings</a> — business assets, people, partners and system users.</p>
<p><a href="https://developers.facebook.com/apps/">Meta for Developers: My Apps</a> — app creation, settings and products/use cases.</p>
<p><a href="https://developers.facebook.com/tools/explorer/">Graph API Explorer</a> — authorized test requests and Page subscriptions.</p>
<p><a href="https://developers.facebook.com/tools/debug/accesstoken/">Access Token Debugger</a> — token type, app, permissions and expiry.</p>
<p><a href="https://developers.facebook.com/tools/lead-ads-testing/">Lead Ads Testing Tool</a> — selected-form test submissions.</p>
</div>
<h3>Technical references and screenshot credits</h3>
<div class="refs">
<p><b>[1]</b> Meta / fbsamples, <a href="https://github.com/fbsamples/lead-ads-webhook-sample/blob/main/docs/Lead%20Ads%20-%20Conversion%20Leads%20-%20Dev%20Guide.pdf">Lead Ads – Conversion Leads – Developer Guide</a> (2022), pages 12 and 16. The two screenshots reproduce published Meta setup screens; they are archival visual references. Repository archived in 2025. Screenshots and Meta interface remain credited to their respective owners.</p>
<p><b>[2]</b> Meta’s maintained Business SDK: <a href="https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/page.py">Page object and subscription/form operations</a>.</p>
<p><b>[3]</b> Meta’s maintained Business SDK: <a href="https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/leadgenform.py">LeadgenForm object and leads retrieval</a>.</p>
<p><b>[4]</b> Meta’s official Postman collection: <a href="https://www.postman.com/meta/whatsapp-business-platform/documentation/wlk6lh4/whatsapp-cloud-api?entity=request-13382743-28543482-3a06-47be-a10e-d94d3d7a1f4e">WhatsApp Cloud API: assets, identifiers, access tokens and permissions</a>.</p>
<p><b>[5]</b> Meta’s official Postman collection: <a href="https://www.postman.com/meta/whatsapp-business-platform/folder/zuoeksl/registration">WhatsApp business-number registration</a>.</p>
<p><b>[6]</b> <a href="https://business.whatsapp.com/policy">WhatsApp Business Messaging Policy</a>: opt-in, templates, replies and opt-outs.</p>
<p><b>[7]</b> Meta’s official Postman collection: <a href="https://www.postman.com/meta/whatsapp-business-platform/folder/ozgs3jn/webhook-subscriptions">WhatsApp webhook subscriptions</a>.</p>
</div>
<p class="small">Preparation note: direct Meta lead-retrieval/app-creation documentation returned access limits during preparation. This guide combines the project’s implemented CRM behavior, Meta’s public SDK/reference material and account-navigation guidance. Confirm current permissions, review requirements and menu choices in the logged-in dashboard; no approval or launch date is guaranteed.</p>
<div class="signature"><p>Prepared and requested by,</p><b>Sajad Hussain</b><span>SWE, Nippon Toyota</span><small>16 September 2026</small></div>
''')

CSS = '''
@font-face{font-family:Lato;src:url('file:///usr/share/fonts/truetype/lato/Lato-Regular.ttf')}
@font-face{font-family:Lato;src:url('file:///usr/share/fonts/truetype/lato/Lato-Bold.ttf');font-weight:700}
*{box-sizing:border-box}@page{size:A4;margin:0}body{margin:0;background:#e5e8ed;color:#253140;font-family:Lato,Arial,sans-serif;font-size:10.1pt;line-height:1.39}
.page{position:relative;width:210mm;height:297mm;padding:15mm 17mm 20mm;background:#fff;margin:auto;break-after:page;overflow:hidden}.page:last-child{break-after:auto}
.top{display:flex;justify-content:space-between;padding-bottom:10px;border-bottom:1px solid #dde3e8;margin-bottom:18px;font-size:8pt;font-weight:700;letter-spacing:.8px;color:#677484}.top b{color:#bd2438}
.kicker{font-size:8.3pt;letter-spacing:1.1px;font-weight:700;color:#c22036;margin:0 0 8px}h1{font-size:25pt;line-height:1.14;letter-spacing:-.5px;margin:0 0 13px;color:#182638}.page:first-child h1{font-size:34pt}h3{font-size:12pt;line-height:1.25;margin:14px 0 7px;color:#1d2e43}p{margin:0 0 8px}.deck{font-size:11.5pt;color:#526175;margin-bottom:15px}.path{padding:10px 12px;background:#f0f4f8;border:1px solid #e1e7ef;border-radius:4px;font-size:10pt}
a{color:#ab1d33;text-decoration:none;overflow-wrap:anywhere}b,strong{font-weight:700}ol{padding-left:23px;margin:10px 0 15px}li{padding-left:3px;margin:0 0 8px}li::marker{font-weight:700;color:#bb2439}
table{width:100%;table-layout:fixed;border-collapse:collapse;font-size:9.3pt;line-height:1.36;margin:11px 0 15px}th{text-align:left;background:#223249;color:white;font-size:8.8pt;padding:9px 10px}td{vertical-align:top;border:1px solid #dce3eb;padding:7px 10px;overflow-wrap:anywhere}tbody tr:nth-child(even){background:#f6f8fa}code{font-family:'DejaVu Sans Mono',monospace;font-size:8.4pt;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;border:1px solid #dce3eb;border-radius:5px;background:#f5f7fa;padding:12px;font:9pt/1.6 'DejaVu Sans Mono',monospace;margin:12px 0}
aside{background:#f3f6fa;border-left:3px solid #c42137;padding:11px 14px;margin:12px 0}aside>strong{display:block;font-size:10pt;color:#1d3049;margin-bottom:4px}aside p{font-size:9.5pt;margin:0}.small{font-size:8.7pt;color:#657184}.footer{position:absolute;bottom:10mm;left:17mm;right:17mm;border-top:1px solid #dce3eb;padding-top:8px;font-size:8pt;color:#6b7684;display:flex;justify-content:space-between}
.flow{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:25px 0;background:#edf3f8;border:1px solid #dfe7ef;padding:18px 14px;border-radius:5px}.flow span{flex:1;font-size:9.6pt}.flow b{font-size:10pt;color:#1a304b}.flow i{color:#bd2337;font-size:20pt;font-style:normal}.byline{margin-top:15px;padding-top:14px;border-top:2px solid #c42137}.byline b{font-size:17pt}.byline span,.byline small{display:block;color:#5e6a7b;margin-top:3px}.byline small{font-size:9pt}
.split{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:15px}.split h3{margin-top:0}figure{margin:0}figure img{display:block;width:100%}figcaption{font-size:8.2pt;line-height:1.4;color:#667285;margin-top:8px}.app-shot{border:1px solid #dce3eb}.wide-shot{margin:18px 0}.test-shot{height:285px;overflow:hidden;border:1px solid #dce3eb;background:#f6f8fb}.test-shot img{width:100%;height:auto}.check{line-height:1.85;font-size:9.6pt}.line{height:24px;border-bottom:1px solid #aeb9c7}.signature{width:65%;margin-top:20px;border-top:2px solid #c42137;padding-top:12px}.signature p{font-size:10pt;margin-bottom:8px}.signature b{display:block;font-size:22pt;letter-spacing:-.3px}.signature span{display:block;font-size:11pt;font-weight:700;color:#546175}.signature small{display:block;margin-top:7px;color:#6d7783}.refs{font-size:8.5pt;line-height:1.4}.refs p{margin-bottom:7px}.links p{font-size:9.5pt;margin-bottom:7px}
.page[data-page="1"] .flow{margin:18px 0;padding:14px}.page[data-page="1"] .byline{margin-top:10px;padding-top:10px}.page[data-page="1"] h1{font-size:32pt}.page[data-page="5"]{font-size:10pt}.page[data-page="8"] h3{margin-top:10px}.page[data-page="8"] table td{padding:5px 10px}.page[data-page="8"] table{margin:8px 0 10px}.page[data-page="8"] pre{padding:9px}.page[data-page="9"] li{margin-bottom:8px}.page[data-page="10"] table td{padding:8px 10px}.page[data-page="12"]{font-size:10pt}.page[data-page="13"] .line{height:19px}.page[data-page="13"] td{padding:6px 10px}.page[data-page="14"] h3{margin-top:13px}
@media print{body{background:white}*{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
'''
html = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="author" content="Sajad Hussain, SWE, Nippon Toyota"><title>Meta Developers &amp; CRM Integration — Agency Setup Guide</title><style>'+CSS+'</style></head><body>'
for i,(section,title,owner,body) in enumerate(pages,1):
    html+=f'<section class="page" data-page="{i}"><div class="top"><b>NIPPON TOYOTA · CRM INTEGRATION</b><span>SETUP GUIDE · SEPTEMBER 2026</span></div><p class="kicker">{section} · {owner}</p><h1>{title}</h1><main>{body}</main><footer class="footer"><span>Sajad Hussain · SWE, Nippon Toyota</span><span>{i:02d} / {len(pages):02d}</span></footer></section>'
html+='''<script>
window.addEventListener('load', async () => {
 await document.fonts.ready;
 document.body.dataset.layout = JSON.stringify([...document.querySelectorAll('.page')].map(p => ({page:p.dataset.page, clearance:Math.round(p.querySelector('footer').getBoundingClientRect().top-p.querySelector('main').getBoundingClientRect().bottom)})));
});
</script></body></html>'''
(ROOT/'Meta_Developers_CRM_Setup_Guide.html').write_text(html)
print(f'Created {len(pages)}-page guide source.')
