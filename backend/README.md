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
