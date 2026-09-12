# Nippon Toyota internship presentation

Open **Nippon_Toyota_Internship_Presentation.pptx** for 46 editable slides with embedded speaker notes. The matching PDF is the presentation fallback. Use **Presenter_Notes.pdf** or **Presenter_Notes.md** to rehearse.

## Personalise before presenting

- Replace the cover fields with your name, register number, course, college, internship dates and mentor.
- Confirm the internship duration. The eight-week timeline is a proposed allocation, not a verified record of attendance or completion. Week 1 follows your company introduction and hierarchy theme; Week 2 follows your R&D and follow-up theme. The remaining stages group the codebase into a coherent project narrative.
- Map each week to your diary and actual contributions. The code proves that a feature exists; it does not prove you personally developed it or completed it in that week.
- Confirm the project name and client context. The repository calls it **Incheon Mobility CRM** and includes River scooter configuration. The presentation identifies **Nippon Toyota** as your internship host and does not assert an unverified corporate relationship between these businesses.
- Replace the illustrative department structure on slide 6 with your internal reporting hierarchy. The three published leadership names come from the official dealer site; the lower reporting lines are not verified.
- Personalise slide 39 with a real observation, a technical contribution and a feedback example. The speaker notes contain suggested first-person phrasing clearly marked for use only if accurate.
- Add current office/interior/desk photographs if you have them. The two included public photographs show the Kalamassery building in 2011 and 2012. They are not presented as current office views or your own photographs.

## Presentation routes

For a **20–25 minute internship presentation**, use slides 1, 3, 5–9, 10–17 (briefly), 19, 22, 25, 33, 37–42. Keep the other technical slides ready for questions.

For a **35–45 minute technical presentation**, cover slides 1–42 and use slides 43–46 as the appendix. Adjust the time to your college's allotted slot.

Slide groups:

| Slides | Content |
|---|---|
| 1–8 | Introduction, company, workplace, leadership, objectives and project context |
| 9–17 | Eight-week timeline and individual weekly activities, technical work and outputs |
| 18–21 | Requirements, customer workflow, roles and technology stack |
| 22–30 | Architecture, frontend/backend, data model, sales, follow-ups and security |
| 31–36 | Imports, complaints, ETBR, performance, offboarding and deployment |
| 37–42 | Verification, challenges, personal reflection, outcomes, demo and closing |
| 43–46 | APIs, supporting entities, viva questions and references |

## Company sources

Accessed 11 September 2026. Official website content supports the company's published profile, not independent confirmation of all internal operations.

- [Official About Us](https://www.nippon-toyota.com/about-us.html)
- [Published dealer mission](https://www.nippon-toyota.com/cms/about-us/dealer-mission-v1.txt): customer satisfaction and integration of sales, service and service parts. The deck paraphrases the mission.
- [Published leadership](https://www.nippon-toyota.com/cms/about-us/dealer-principal-v1.txt): M. A. M. Babu Moopan, Dealer Principal; Athif Moopan, Director; Naeem Shahul, Director. This content is loaded by the official About Us page.
- [Official Kalamassery location](https://nippon-toyota.com/contact-co01b.html): Nippon Motor Corporation Pvt. Ltd., Nippon Towers, NH 47, HMT Junction, Kalamassery, Cochin 683104; showroom and service centre.
- [Company LinkedIn profile](https://www.linkedin.com/company/nippon-toyota-pvt-ltd): establishment date reported as 27 January 2000. No employee-count or market-rank claims have been copied into the deck.
- [Nippon U Trust locations](https://www.nippon-toyota.com/used-cars.html): used-car location at Kalamassery.

## Photo credits

**Kalamassery Toyota Office.JPG** — Ranjithsiji, photographed 13 March 2012. [Source and licence information](https://commons.wikimedia.org/wiki/File:Kalamassery_Toyota_Office.JPG). Licensed [Creative Commons Attribution-ShareAlike 3.0 Unported](https://creativecommons.org/licenses/by-sa/3.0/). Included unmodified and scaled proportionally on slides 1 and 5. The photo remains under its own licence; attribution and licence links accompany the presentation. If adapting the photo, retain the required attribution and share-alike terms for the adaptation.

**Nippon Toyota showroom at South Kalamassery** — Sreejith Sivadasan, photographed 22 July 2011. [Flickr source](https://www.flickr.com/photos/sreejithmsivadasan/5974734010). The source marks this image **All rights reserved**. Included with attribution for the requested educational presentation; attribution does not grant a licence. Obtain permission or replace it with a photo you own or a licensed image before public redistribution. The image is unmodified and scaled proportionally on slide 5.

## Technical evidence

The local repository is the primary source for implementation details. Relevant file paths appear in the embedded speaker notes and presenter guide. Principal sources include:

- `README.md`, `frontend/package.json`, `backend/requirements.txt`
- `backend/config/settings.py`, `backend/config/urls.py`, `render.yaml`
- `frontend/src/lib/crm.ts`, role routes, feature screens and shared components
- `backend/accounts/models.py`, `authentication.py`, `permissions.py`, `views.py`, `offboarding.py`
- `backend/leads/models.py`, `serializers.py`, `views.py`, `metrics.py`
- `backend/uploads/models.py`, `tasks.py`, `views.py`, `storage.py`
- `backend/complaints/models.py`, `permissions.py`, `serializers.py`
- `backend/analytics/cache.py`, `views.py`, `test_etbr.py`
- `backend/notifications/tasks.py`

The presentation does not claim a verified live rollout, scheduler execution, production database provider, measured business improvement, or complete security audit. No customer records or credentials were read for the deck. Application files were not changed.

## Editing and regeneration

Edit the `.pptx` in PowerPoint or LibreOffice. Diagrams, labels and tables use editable slide objects. To change the generated edition, edit `source/build_internship.py` and run it in a Python environment with `python-pptx`, `reportlab` and `Pillow`. The current temporary environment is `/tmp/nippon-slides-venv`.

The builder writes the PowerPoint, structured slide content and presenter notes. Export the PowerPoint to PDF after regeneration. `source/verify_artifacts.py` checks slide counts, embedded notes, slide boundaries and retained text in the PDF.
