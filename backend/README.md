# Incheon Mobility CRM API

Run locally:

```bash
cp .env.example .env
source .venv/bin/activate
python manage.py migrate
python manage.py runserver
```

Run the worker and scheduler in separate terminals:

```bash
celery -A config worker --loglevel=INFO
celery -A config beat --loglevel=INFO
```

Open API documentation at `/api/docs/`.

The browser only calls Django REST endpoints. Django owns authentication, role checks, audit records, and lead visibility. Configure Supabase credentials and the Render Redis URL through environment variables, never in source files.
